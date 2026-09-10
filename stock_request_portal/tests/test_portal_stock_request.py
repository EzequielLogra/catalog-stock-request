import re

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestStockRequestPortal(HttpCase):
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.client_location = cls.env["stock.location"].create(
            {
                "name": "Client Stock Location",
                "usage": "internal",
                "location_id": cls.warehouse.lot_stock_id.id,
            }
        )
        cls.client_partner = cls.env["res.partner"].create(
            {
                "name": "Hospital Client",
                "email": "client@example.com",
                "stock_request_location_id": cls.client_location.id,
            }
        )
        cls.portal_user = cls.env["res.users"].create(
            {
                "name": "Portal Client User",
                "login": "portal_client",
                "email": "client@example.com",
                "password": "P0rtalClient1!",
                "partner_id": cls.client_partner.id,
                "group_ids": [
                    Command.set([cls.env.ref("base.group_portal").id])
                ],
            }
        )
        cls.product_a = cls.env["product.product"].create(
            {"name": "Product A", "type": "consu"}
        )
        cls.product_b = cls.env["product.product"].create(
            {"name": "Product B", "type": "consu"}
        )

    def _get_csrf_token(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        text = response.text
        match = re.search(
            r'name="csrf_token"[^>]*value="([^"]*)"', text
        ) or re.search(r'value="([^"]*)"[^>]*name="csrf_token"', text)
        self.assertTrue(match, "CSRF token not found in page")
        return match.group(1)

    def _submit_order(self, lines, expected_date="2030-01-31T12:00"):
        data = [("expected_date", expected_date)]
        for product, qty in lines:
            data.append(("product_id", str(product.id)))
            data.append(("product_uom_qty", str(qty)))
        data.append(
            ("csrf_token", self._get_csrf_token("/my/stock-request-orders/new"))
        )
        return self.url_open(
            "/my/stock-request-orders/new", data=data, timeout=60
        )

    def test_portal_list_page_shows_new_button_and_catalog(self):
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders")
        self.assertEqual(response.status_code, 200)
        self.assertIn("New Stock Request", response.text)
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_sr_product_card", response.text)
        self.assertIn("Product A", response.text)
        # search narrows the catalog
        response = self.url_open(
            "/my/stock-request-orders/new?search=Product+B"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Product B", response.text)
        self.assertNotIn("Product A", response.text)

    def test_portal_catalog_category_filter(self):
        category = self.env["product.category"].create(
            {"name": "Insumos Category"}
        )
        self.product_b.categ_id = category
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open(
            f"/my/stock-request-orders/new?category_id={category.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Product B", response.text)
        self.assertNotIn("Product A", response.text)

    def test_portal_user_can_create_order(self):
        self.authenticate("portal_client", "P0rtalClient1!")
        self._get_csrf_token("/my/stock-request-orders/new")
        response = self._submit_order(
            [(self.product_a, 5), (self.product_b, 3)]
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/stock-request-orders/", response.url)

        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertTrue(order)
        self.assertEqual(order.state, "draft")
        self.assertTrue(order.split_purchase)
        self.assertEqual(order.location_id, self.client_location)
        self.assertEqual(order.warehouse_id, self.warehouse)
        self.assertEqual(len(order.stock_request_ids), 2)
        self.assertEqual(
            sorted(order.stock_request_ids.mapped("product_id").ids),
            sorted([self.product_a.id, self.product_b.id]),
        )
        for request in order.stock_request_ids:
            self.assertEqual(request.state, "draft")
            self.assertEqual(request.product_uom_id, request.product_id.uom_id)
        # Submission logged in the chatter
        self.assertTrue(
            self.env["mail.message"].search_count(
                [("model", "=", "stock.request.order"), ("res_id", "=", order.id)]
            )
        )

    def test_portal_cannot_access_other_partners_order(self):
        other_user = self.env["res.users"].create(
            {
                "name": "Other Portal User",
                "login": "portal_other",
                "email": "other@example.com",
                "password": "P0rtal0ther1!",
                "group_ids": [
                    Command.set([self.env.ref("base.group_portal").id])
                ],
            }
        )
        other_order = self.env["stock.request.order"].sudo().create(
            {
                "company_id": self.company.id,
                "warehouse_id": self.warehouse.id,
                "location_id": other_user.partner_id.stock_request_location_id.id
                or self.warehouse.lot_stock_id.id,
                "expected_date": fields.Datetime.now(),
                "requested_by": other_user.id,
                "stock_request_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "product_uom_id": self.product_a.uom_id.id,
                            "product_uom_qty": 1,
                            "company_id": self.company.id,
                            "warehouse_id": self.warehouse.id,
                            "location_id": self.warehouse.lot_stock_id.id,
                            "expected_date": fields.Datetime.now(),
                            "requested_by": other_user.id,
                        }
                    )
                ],
            }
        )
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open(f"/my/stock-request-orders/{other_order.id}")
        self.assertTrue(response.url.rstrip("/").endswith("/my"))

    def test_portal_create_order_without_location_fails(self):
        self.client_partner.stock_request_location_id = False
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order([(self.product_a, 2)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("destination location", response.text)
        self.assertFalse(
            self.env["stock.request.order"].search_count(
                [("requested_by", "=", self.portal_user.id)]
            )
        )

    def test_portal_create_order_invalid_qty_fails(self):
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order([(self.product_a, 0)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("greater than zero", response.text)
        self.assertFalse(
            self.env["stock.request.order"].search_count(
                [("requested_by", "=", self.portal_user.id)]
            )
        )
