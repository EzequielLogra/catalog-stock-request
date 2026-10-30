from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestObraAnalytic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.obras = cls.env["stock.location"].create(
            {"name": "Obras", "usage": "view"}
        )
        route = cls.env["stock.route"].create(
            {
                "name": "Abastecimiento a obras",
                "product_categ_selectable": False,
                "product_selectable": False,
                "warehouse_selectable": True,
                "warehouse_ids": [(4, cls.warehouse.id)],
            }
        )
        cls.env["stock.rule"].create(
            {
                "name": "WH Stock to Obras",
                "route_id": route.id,
                "location_src_id": cls.warehouse.lot_stock_id.id,
                "location_dest_id": cls.obras.id,
                "action": "pull",
                "picking_type_id": cls.warehouse.int_type_id.id,
                "procure_method": "make_to_stock",
                "warehouse_id": cls.warehouse.id,
            }
        )
        cls.warehouse.buy_to_resupply = True
        plan = cls.env["account.analytic.plan"].create({"name": "Obras"})
        cls.client = cls.env["res.partner"].create({"name": "Terminal"})
        cls.obra_1, cls.account_1 = cls._create_obra("Obra 1", plan)
        cls.obra_2, cls.account_2 = cls._create_obra("Obra 2", plan)
        cls.obra_3, __ = cls._create_obra("Obra 3", False)
        # All the RFQs of the vendor in the same purchase order
        cls.vendor = cls.env["res.partner"].create(
            {"name": "Vendor", "group_rfq": "all"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Caño",
                "type": "consu",
                "is_storable": True,
                "seller_ids": [
                    (0, 0, {"partner_id": cls.vendor.id, "price": 10})
                ],
            }
        )

    @classmethod
    def _create_obra(cls, name, plan):
        location = cls.env["stock.location"].create(
            {"name": name, "usage": "internal", "location_id": cls.obras.id}
        )
        partner = cls.env["res.partner"].create(
            {
                "name": name,
                "type": "delivery",
                "parent_id": cls.client.id,
                "stock_request_location_id": location.id,
            }
        )
        account = cls.env["account.analytic.account"]
        if plan:
            account = account.create({"name": name, "plan_id": plan.id})
            cls.env["account.analytic.distribution.model"].create(
                {
                    "partner_id": partner.id,
                    "analytic_distribution": {str(account.id): 100},
                }
            )
        return location, account

    def _create_order(self, location, qty):
        return self.env["stock.request.order"].create(
            {
                "warehouse_id": self.warehouse.id,
                "location_id": location.id,
                "expected_date": fields.Datetime.now(),
                "split_purchase": True,
                "stock_request_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_id": self.product.uom_id.id,
                            "product_uom_qty": qty,
                            "warehouse_id": self.warehouse.id,
                            "location_id": location.id,
                            "expected_date": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )

    def _purchase_lines(self, *orders):
        return self.env["stock.request.order"].concat(
            *orders
        ).stock_request_ids.purchase_line_ids

    def test_purchase_line_charged_to_obra(self):
        order = self._create_order(self.obra_1, 2)
        order.action_confirm()
        line = self._purchase_lines(order)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.analytic_distribution, {str(self.account_1.id): 100})

    def test_one_line_per_obra_in_same_purchase(self):
        order_1 = self._create_order(self.obra_1, 1)
        order_2 = self._create_order(self.obra_2, 1)
        order_1.action_confirm()
        order_2.action_confirm()
        lines = self._purchase_lines(order_1, order_2)
        self.assertEqual(len(lines.order_id), 1)
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            {
                (line.product_qty, next(iter(line.analytic_distribution)))
                for line in lines
            },
            {(1, str(self.account_1.id)), (1, str(self.account_2.id))},
        )

    def _set_pre_obra(self, obra):
        pre_obra = self.env["stock.location"].create(
            {
                "name": f"Pre-obra {obra.name}",
                "usage": "internal",
                "location_id": self.warehouse.view_location_id.id,
            }
        )
        obra._get_stock_request_partner().property_stock_customer = pre_obra
        return pre_obra

    def _send_to_pre_obra(self, pre_obra):
        """Pending transfer of the warehouse stock to the pre-obra, as the
        delivery of a sale to the obra with no stock to send it."""
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": pre_obra.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "product_uom": self.product.uom_id.id,
                            "location_id": self.warehouse.lot_stock_id.id,
                            "location_dest_id": pre_obra.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        return picking

    def test_grouped_purchase_supplies_each_obra(self):
        """A purchase mixing obras: each one is charged its line and gets its
        units, whichever transfer is older."""
        delivery_1 = self._send_to_pre_obra(self._set_pre_obra(self.obra_1))
        delivery_2 = self._send_to_pre_obra(self._set_pre_obra(self.obra_2))
        order_2 = self._create_order(self.obra_2, 1)
        order_1 = self._create_order(self.obra_1, 1)
        order_2.action_confirm()
        order_1.action_confirm()
        lines = self._purchase_lines(order_1, order_2)
        purchase = lines.order_id
        self.assertEqual(len(purchase), 1)
        self.assertEqual(len(lines), 2)
        purchase.button_confirm()
        receipt = purchase.picking_ids
        self.assertEqual(sum(receipt.move_ids.mapped("product_uom_qty")), 2)
        # Only the unit of obra 2 arrives: obra 1, older, does not take it.
        line_2 = self._purchase_lines(order_2)
        for move in receipt.move_ids:
            move.quantity = 1 if move.purchase_line_id == line_2 else 0
        receipt.move_ids.filtered("quantity").picked = True
        receipt.with_context(skip_backorder=True).button_validate()
        self.assertEqual(delivery_2.state, "assigned")
        self.assertEqual(delivery_1.move_ids.quantity, 0)
        self.assertEqual(
            line_2.analytic_distribution, {str(self.account_2.id): 100}
        )
        # The unit of obra 1 arrives on the backorder.
        backorder = receipt.backorder_ids
        backorder.move_ids.picked = True
        backorder.button_validate()
        self.assertEqual(delivery_1.state, "assigned")

    def test_same_obra_merged_in_one_line(self):
        order_1 = self._create_order(self.obra_1, 1)
        order_2 = self._create_order(self.obra_1, 1)
        order_1.action_confirm()
        order_2.action_confirm()
        line = self._purchase_lines(order_1, order_2)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_qty, 2)
        self.assertEqual(line.analytic_distribution, {str(self.account_1.id): 100})

    def test_obra_without_model_not_merged_with_charged_line(self):
        order_1 = self._create_order(self.obra_1, 1)
        order_3 = self._create_order(self.obra_3, 1)
        order_1.action_confirm()
        order_3.action_confirm()
        lines = self._purchase_lines(order_1, order_3)
        self.assertEqual(len(lines), 2)
        line_3 = self._purchase_lines(order_3)
        self.assertFalse(line_3.analytic_distribution)

    def test_procurements_of_different_obras_not_merged(self):
        """Run in a single batch, the procurements are merged before looking
        for a purchase line."""
        order_1 = self._create_order(self.obra_1, 1)
        order_2 = self._create_order(self.obra_2, 1)
        purchase_route = order_1.stock_request_ids._get_purchase_route()
        procurements = [
            request._get_purchase_procurement(1, purchase_route)
            for request in (order_1 | order_2).stock_request_ids
        ]
        self.env["stock.rule"].run(procurements)
        lines = self.env["purchase.order.line"].search(
            [("product_id", "=", self.product.id)]
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            {next(iter(line.analytic_distribution)) for line in lines},
            {str(self.account_1.id), str(self.account_2.id)},
        )
