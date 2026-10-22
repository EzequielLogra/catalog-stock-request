from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockRequestPartner(TransactionCase):
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
        cls.obra_location = cls.env["stock.location"].create(
            {
                "name": "Obra 1",
                "usage": "internal",
                "location_id": cls.obras.id,
            }
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
        cls.client = cls.env["res.partner"].create({"name": "Terminal"})
        cls.obra_partner = cls.env["res.partner"].create(
            {
                "name": "Obra 1",
                "type": "delivery",
                "parent_id": cls.client.id,
                "stock_request_location_id": cls.obra_location.id,
            }
        )
        vendor = cls.env["res.partner"].create({"name": "Vendor"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Caño",
                "type": "consu",
                "is_storable": True,
                "seller_ids": [(0, 0, {"partner_id": vendor.id, "price": 10})],
            }
        )

    def _set_stock(self, location, qty):
        self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": location.id,
                "inventory_quantity": qty,
            }
        ).action_apply_inventory()

    def _confirm_order(self, qty):
        order = self.env["stock.request.order"].create(
            {
                "warehouse_id": self.warehouse.id,
                "location_id": self.obra_location.id,
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
                            "location_id": self.obra_location.id,
                            "expected_date": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        return order

    def test_transfer_carries_obra_contact_not_purchase(self):
        self._set_stock(self.warehouse.lot_stock_id, 3)
        order = self._confirm_order(5)
        self.assertEqual(order.picking_ids.partner_id, self.obra_partner)
        purchase = order.stock_request_ids.purchase_line_ids.order_id
        self.assertTrue(purchase)
        self.assertFalse(purchase.dest_address_id)

    def test_transfer_from_pre_obra_carries_obra_contact(self):
        pre_obra = self.env["stock.location"].create(
            {
                "name": "Pre-obra 1",
                "usage": "internal",
                "location_id": self.warehouse.view_location_id.id,
            }
        )
        self.obra_partner.property_stock_customer = pre_obra
        self._set_stock(pre_obra, 2)
        order = self._confirm_order(2)
        picking = order.picking_ids
        self.assertEqual(picking.location_id, pre_obra)
        self.assertEqual(picking.partner_id, self.obra_partner)
