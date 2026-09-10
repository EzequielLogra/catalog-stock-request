from odoo import Command, fields
from odoo.exceptions import UserError

from odoo.addons.stock_request_purchase.tests.test_stock_request_purchase import (
    TestStockRequestPurchase,
)


class TestSplitPurchase(TestStockRequestPurchase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ward_location = cls.env["stock.location"].create(
            {
                "name": "Ward A",
                "location_id": cls.warehouse.view_location_id.id,
                "usage": "internal",
                "company_id": cls.main_company.id,
            }
        )
        cls.route_supply = cls.env["stock.route"].create(
            {
                "name": "Supply Ward A",
                "product_categ_selectable": False,
                "product_selectable": False,
                "warehouse_selectable": True,
                "warehouse_ids": [(4, cls.warehouse.id)],
                "company_id": cls.main_company.id,
            }
        )
        cls.env["stock.rule"].create(
            {
                "name": "WH Stock to Ward A",
                "route_id": cls.route_supply.id,
                "location_src_id": cls.warehouse.lot_stock_id.id,
                "location_dest_id": cls.ward_location.id,
                "action": "pull",
                "picking_type_id": cls.warehouse.int_type_id.id,
                "procure_method": "make_to_stock",
                "location_dest_from_rule": True,
                "warehouse_id": cls.warehouse.id,
                "company_id": cls.main_company.id,
            }
        )
        cls.supplier_ranked = cls.env["res.partner"].create(
            {"name": "Ranked Supplier", "supplier_rank": 1}
        )
        cls.product.write(
            {
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.supplier_ranked.id,
                            "min_qty": 1,
                            "price": 10,
                        },
                    )
                ],
            }
        )
        cls.product_no_supplier = cls.env["product.product"].create(
            {
                "name": "No Supplier Product",
                "default_code": "NSP",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "company_id": cls.main_company.id,
                "type": "consu",
                "is_storable": True,
            }
        )

    @classmethod
    def _create_order(cls, line_vals, **order_vals):
        expected_date = fields.Datetime.now()
        vals = {
            "company_id": cls.main_company.id,
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.ward_location.id,
            "expected_date": expected_date,
            "split_purchase": True,
            "stock_request_ids": [
                (
                    0,
                    0,
                    dict(
                        {
                            "product_uom_id": cls.product.uom_id.id,
                            "product_uom_qty": 20.0,
                            "company_id": cls.main_company.id,
                            "warehouse_id": cls.warehouse.id,
                            "location_id": cls.ward_location.id,
                            "expected_date": expected_date,
                            "route_id": cls.route_supply.id,
                        },
                        **line_vals,
                    ),
                )
            ],
        }
        vals.update(order_vals)
        return cls.env["stock.request.order"].create(vals)

    def _set_stock(self, product, qty):
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "inventory_quantity": qty,
            }
        )
        quant.action_apply_inventory()

    def test_split_partial(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(order.state, "open")
        self.assertEqual(request.qty_from_stock, 12.0)
        self.assertEqual(request.qty_purchased, 8.0)
        self.assertEqual(request.qty_to_purchase, 8.0)
        pickings = order.picking_ids
        self.assertEqual(len(pickings), 1)
        move = pickings.move_ids
        self.assertEqual(move.product_uom_qty, 12.0)
        self.assertEqual(move.location_dest_id, self.ward_location)
        self.assertEqual(request.qty_reserved, 12.0)
        purchases = request.sudo().purchase_ids
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases.order_line.product_qty, 8.0)
        self.assertEqual(
            purchases.order_line.stock_request_ids, request
        )

    def test_split_all_stock(self):
        self._set_stock(self.product, 20.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 20.0)
        self.assertEqual(request.qty_purchased, 0.0)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 20.0)
        self.assertEqual(len(request.sudo().purchase_ids), 0)

    def test_split_no_stock_ranked_supplier(self):
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 0.0)
        self.assertEqual(request.qty_purchased, 20.0)
        self.assertEqual(len(order.picking_ids), 0)
        purchases = request.sudo().purchase_ids
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases.partner_id, self.supplier_ranked)
        self.assertEqual(purchases.order_line.product_qty, 20.0)

    def test_cancel_with_draft_purchase(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(purchase.state, "draft")
        order.action_cancel()
        self.assertEqual(order.state, "cancel")
        self.assertEqual(purchase.state, "cancel")

    def test_cancel_with_confirmed_purchase(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        purchase.button_confirm()
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_missing_supplier(self):
        self._set_stock(self.product_no_supplier, 5.0)
        order = self._create_order(
            {
                "product_id": self.product_no_supplier.id,
                "product_uom_qty": 10.0,
            }
        )
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_purchase_obra_internal_requester(self):
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(len(purchase), 1)
        self.assertIn(order.name, purchase.origin)
        self.assertIn(self.ward_location.complete_name, purchase.origin)
        self.assertNotIn("(", purchase.origin)
        self.assertEqual(purchase.obra_location_id, self.ward_location)

    def test_purchase_obra_portal_client(self):
        client = self.env["res.partner"].create(
            {"name": "Hospital Sur SA", "is_company": True}
        )
        portal_user = self.env["res.users"].create(
            {
                "name": "Portal Obra User",
                "login": "portal_obra_user",
                "email": "obra@example.com",
                "partner_id": client.id,
                "group_ids": [
                    Command.set([self.env.ref("base.group_portal").id])
                ],
            }
        )
        order = self._create_order(
            {"product_id": self.product.id, "requested_by": portal_user.id},
            requested_by=portal_user.id,
        )
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(len(purchase), 1)
        self.assertIn(order.name, purchase.origin)
        self.assertIn(self.ward_location.complete_name, purchase.origin)
        self.assertIn(f"({client.name})", purchase.origin)
        self.assertEqual(purchase.obra_location_id, self.ward_location)

    def test_no_split_standard_behavior(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order(
            {"product_id": self.product.id}, split_purchase=False
        )
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 0.0)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 20.0)
        self.assertEqual(len(request.sudo().purchase_ids), 0)
