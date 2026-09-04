from odoo import fields

from odoo.addons.catalog_stock_request.tests.test_catalog_stock_request import (
    TestSplitPurchase,
)


class TestCatalog(TestSplitPurchase):
    @classmethod
    def _create_empty_order(cls):
        return cls.env["stock.request.order"].create(
            {
                "company_id": cls.main_company.id,
                "warehouse_id": cls.warehouse.id,
                "location_id": cls.ward_location.id,
                "expected_date": fields.Datetime.now(),
                "route_id": cls.route_supply.id,
                "split_purchase": True,
            }
        )

    def test_action_add_from_catalog(self):
        order = self._create_empty_order()
        action = order.action_add_from_catalog()
        self.assertEqual(action["res_model"], "product.product")
        self.assertEqual(
            action["context"]["product_catalog_order_model"],
            "stock.request.order",
        )
        self.assertEqual(
            action["context"]["product_catalog_order_id"], order.id
        )
        self.assertEqual(action["context"]["order_id"], order.id)

    def test_action_add_from_catalog_from_empty_lines(self):
        order = self._create_empty_order()
        action = (
            self.env["stock.request"]
            .with_context(order_id=order.id)
            .action_add_from_catalog()
        )
        self.assertEqual(action["res_model"], "product.product")
        self.assertEqual(
            action["context"]["product_catalog_order_id"], order.id
        )

    def test_catalog_order_line_info(self):
        order = self._create_order({"product_id": self.product.id})
        info = order._get_product_catalog_order_line_info(
            [self.product.id, self.product_no_supplier.id]
        )
        self.assertEqual(info[self.product.id]["quantity"], 20.0)
        self.assertFalse(info[self.product.id]["readOnly"])
        self.assertEqual(info[self.product_no_supplier.id]["quantity"], 0)
        self.assertIn("price", info[self.product_no_supplier.id])
        self.assertIsInstance(
            info[self.product_no_supplier.id]["price"], float
        )
        self.assertFalse(info[self.product_no_supplier.id]["readOnly"])

    def test_catalog_line_info_readonly(self):
        self._set_stock(self.product, 20.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        info = order._get_product_catalog_order_line_info([self.product.id])
        self.assertTrue(info[self.product.id]["readOnly"])

    def test_update_order_line_info_create_update_delete(self):
        order = self._create_empty_order()
        order._update_order_line_info(self.product.id, 5.0)
        request = order.stock_request_ids
        self.assertEqual(len(request), 1)
        self.assertEqual(request.product_id, self.product)
        self.assertEqual(request.product_uom_id, self.product.uom_id)
        self.assertEqual(request.product_uom_qty, 5.0)
        self.assertEqual(request.warehouse_id, order.warehouse_id)
        self.assertEqual(request.location_id, order.location_id)
        self.assertEqual(request.requested_by, order.requested_by)
        self.assertEqual(request.expected_date, order.expected_date)
        self.assertEqual(request.route_id, order.route_id)
        order._update_order_line_info(self.product.id, 9.0)
        self.assertEqual(len(order.stock_request_ids), 1)
        self.assertEqual(order.stock_request_ids.product_uom_qty, 9.0)
        order._update_order_line_info(self.product.id, 0)
        self.assertEqual(len(order.stock_request_ids), 0)

    def test_update_order_line_info_readonly(self):
        self._set_stock(self.product, 20.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        order._update_order_line_info(self.product_no_supplier.id, 3.0)
        self.assertNotIn(
            self.product_no_supplier.id,
            order.stock_request_ids.mapped("product_id").ids,
        )

    def test_full_flow_from_catalog(self):
        self._set_stock(self.product, 12.0)
        order = self._create_empty_order()
        order._update_order_line_info(self.product.id, 20.0)
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 12.0)
        self.assertEqual(request.qty_purchased, 8.0)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(
            order.picking_ids.move_ids.location_dest_id, self.ward_location
        )
        purchases = request.sudo().purchase_ids
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases.order_line.product_qty, 8.0)
