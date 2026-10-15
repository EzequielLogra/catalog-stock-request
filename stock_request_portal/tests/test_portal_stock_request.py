import html
import json
import re

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestStockRequestPortal(HttpCase):
    @classmethod
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
        cls.client_location_b = cls.env["stock.location"].create(
            {
                "name": "Client Stock Location B",
                "usage": "internal",
                "location_id": cls.warehouse.lot_stock_id.id,
            }
        )
        cls.child_partner = cls.env["res.partner"].create(
            {
                "name": "Hospital Client - Delivery",
                "type": "delivery",
                "parent_id": cls.client_partner.id,
                "stock_request_location_id": cls.client_location_b.id,
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
        (cls.client_partner | cls.child_partner).write(
            {
                "stock_request_supervisor_ids": [
                    Command.link(cls.portal_user.partner_id.id)
                ]
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

    def _submit_order(
        self, lines, expected_date="2030-01-31T12:00", location=None
    ):
        data = [("expected_date", expected_date)]
        if location:
            data.append(("location_id", str(location.id)))
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
        # destination location selector lists both allowed locations
        self.assertIn('name="location_id"', response.text)
        self.assertIn("Client Stock Location", response.text)
        self.assertIn("Client Stock Location B", response.text)
        self.assertIn("o_sr_categories", response.text)
        self.assertIn("data-category-id", response.text)
        # product columns carry the class used by the client-side filter
        self.assertIn("o_sr_product_col", response.text)
        # each card has an integer quantity stepper
        self.assertIn("o_sr_qty_stepper", response.text)
        self.assertIn("o_sr_card_qty", response.text)
        self.assertIn("o_sr_qty_plus", response.text)
        self.assertIn("o_sr_qty_minus", response.text)
        self.assertIn('min="1"', response.text)
        self.assertIn('step="1"', response.text)

    def test_portal_catalog_renders_all_products_and_category_chips(self):
        category = self.env["product.category"].create(
            {"name": "Insumos Category"}
        )
        self.product_b.categ_id = category
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        # locations without stock set aside get the whole catalog, filtered
        # client side
        self.assertIn("Product A", response.text)
        self.assertIn("Product B", response.text)
        # category chip with its display name is rendered
        self.assertIn("Insumos Category", response.text)

    def test_portal_catalog_card_shows_name_and_reference_apart(self):
        self.product_a.default_code = "REF-A"
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-product-name="Product A"', response.text)
        self.assertIn('data-product-ref="REF-A"', response.text)
        self.assertNotIn("[REF-A] Product A", response.text)
        self.assertIn('data-per-page="20"', response.text)
        # client-side search box
        self.assertIn('id="o_sr_search"', response.text)

    def test_portal_catalog_colors_come_from_system_parameters(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("stock_request_portal.color_primary", "#0e2b48")
        params.set_param(
            "stock_request_portal.color_accent", "red; background: url(x)"
        )
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("--o-sr-primary: #0e2b48", response.text)
        # invalid values are ignored instead of reaching the style attribute
        self.assertNotIn("--o-sr-accent", response.text)

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
        # no location posted: falls back to an allowed location
        self.assertIn(
            order.location_id, self.client_location | self.client_location_b
        )
        self.assertEqual(order.warehouse_id, self.warehouse)
        self.assertEqual(len(order.stock_request_ids), 2)
        self.assertEqual(
            sorted(order.stock_request_ids.mapped("product_id").ids),
            sorted([self.product_a.id, self.product_b.id]),
        )
        for request in order.stock_request_ids:
            self.assertEqual(request.state, "draft")
            self.assertEqual(
                request.product_uom_id, request.product_id.uom_id
            )
            self.assertEqual(request.location_id, order.location_id)
        # Submission logged in the chatter
        self.assertTrue(
            self.env["mail.message"].search_count(
                [("model", "=", "stock.request.order"), ("res_id", "=", order.id)]
            )
        )

    def test_portal_expected_date_uses_user_timezone(self):
        self.portal_user.tz = "America/Argentina/Buenos_Aires"
        self.authenticate("portal_client", "P0rtalClient1!")
        self._get_csrf_token("/my/stock-request-orders/new")
        response = self._submit_order(
            [(self.product_a, 1)], expected_date="2030-01-31T12:00"
        )
        self.assertEqual(response.status_code, 200)
        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        # 12:00 in Buenos Aires (UTC-3) is stored as 15:00 UTC
        self.assertEqual(
            order.expected_date, fields.Datetime.to_datetime("2030-01-31 15:00:00")
        )
        for request in order.stock_request_ids:
            self.assertEqual(request.expected_date, order.expected_date)

    def test_portal_user_can_choose_child_destination_location(self):
        self.authenticate("portal_client", "P0rtalClient1!")
        self._get_csrf_token("/my/stock-request-orders/new")
        response = self._submit_order(
            [(self.product_a, 2)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/stock-request-orders/", response.url)

        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertTrue(order)
        self.assertEqual(order.location_id, self.client_location_b)
        for request in order.stock_request_ids:
            self.assertEqual(request.location_id, self.client_location_b)

    def test_portal_location_of_other_contact_is_ignored(self):
        other_location = self.env["stock.location"].create(
            {
                "name": "Other Client Location",
                "usage": "internal",
                "location_id": self.warehouse.lot_stock_id.id,
            }
        )
        self.env["res.partner"].create(
            {
                "name": "Other Client",
                "email": "other-client@example.com",
                "stock_request_location_id": other_location.id,
            }
        )
        self.authenticate("portal_client", "P0rtalClient1!")
        self._get_csrf_token("/my/stock-request-orders/new")
        response = self._submit_order(
            [(self.product_a, 1)], location=other_location
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/stock-request-orders/", response.url)

        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertTrue(order)
        self.assertNotEqual(order.location_id, other_location)
        self.assertIn(
            order.location_id, self.client_location | self.client_location_b
        )

    def test_portal_location_without_supervisor_not_selectable(self):
        self.child_partner.stock_request_supervisor_ids = False
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        # delivery point the user does not supervise is not offered
        self.assertNotIn("Client Stock Location B", response.text)
        # posting it anyway falls back to the supervised location
        response = self._submit_order(
            [(self.product_a, 1)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/stock-request-orders/", response.url)

        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertTrue(order)
        self.assertEqual(order.location_id, self.client_location)

    def test_portal_archived_child_location_not_selectable(self):
        self.child_partner.active = False
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        # archived delivery point is not offered in the selector
        self.assertNotIn("Client Stock Location B", response.text)
        # posting it anyway falls back to the allowed location
        response = self._submit_order(
            [(self.product_a, 1)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/stock-request-orders/", response.url)

        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertTrue(order)
        self.assertEqual(order.location_id, self.client_location)

    def test_portal_order_page_hides_supply_split_from_portal_users(self):
        self.authenticate("portal_client", "P0rtalClient1!")
        self._get_csrf_token("/my/stock-request-orders/new")
        response = self._submit_order([(self.product_a, 2)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("Requested Quantity", response.text)
        self.assertNotIn("From Stock", response.text)
        self.assertNotIn("To Purchase", response.text)

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
        self.child_partner.stock_request_location_id = False
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

    def _set_aside_stock(self, partner, product, qty):
        """Give the contact an internal customer location (where its sales
        are delivered) holding the given quantity."""
        source_location = self.env["stock.location"].create(
            {
                "name": f"{partner.name} set aside",
                "usage": "internal",
                "location_id": self.warehouse.view_location_id.id,
            }
        )
        partner.property_stock_customer = source_location
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": source_location.id,
                "inventory_quantity": qty,
            }
        )
        quant.action_apply_inventory()
        return source_location

    def test_portal_order_within_set_aside_stock(self):
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        source_location = self._set_aside_stock(self.child_partner, product, 4)
        self.assertEqual(
            self.client_location_b._get_stock_request_source_location(),
            source_location,
        )
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order(
            [(product, 4)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertEqual(order.location_id, self.client_location_b)
        self.assertEqual(order.stock_request_ids.free_qty, 4)

    def test_portal_order_over_set_aside_stock_is_allowed(self):
        """Asking for more than the stock set aside is allowed: the missing
        quantity is purchased when the order is confirmed."""
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        self._set_aside_stock(self.child_partner, product, 4)
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order(
            [(product, 5)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        order = self.env["stock.request.order"].search(
            [("requested_by", "=", self.portal_user.id)], limit=1
        )
        self.assertEqual(order.stock_request_ids.product_uom_qty, 5)
        self.assertEqual(order.stock_request_ids.qty_to_purchase, 1)

    def test_portal_order_of_product_not_set_aside_fails(self):
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        self._set_aside_stock(self.child_partner, product, 4)
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order(
            [(self.product_a, 1)], location=self.client_location_b
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("is not assigned to", response.text)
        self.assertFalse(
            self.env["stock.request.order"].search_count(
                [("requested_by", "=", self.portal_user.id)]
            )
        )

    def test_portal_catalog_keeps_set_aside_products_without_stock(self):
        """A product whose set aside stock ran out is still offered, with
        zero available, so the supervisor can ask for more."""
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        source_location = self._set_aside_stock(self.child_partner, product, 4)
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "=", source_location.id),
            ]
        )
        quant.inventory_quantity = 0
        quant.action_apply_inventory()
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        match = re.search(r'data-set-aside="([^"]*)"', response.text)
        set_aside = json.loads(html.unescape(match.group(1)))
        self.assertEqual(
            set_aside, {str(self.client_location_b.id): {str(product.id): 0.0}}
        )

    def test_portal_location_without_set_aside_stock_is_not_limited(self):
        self.assertFalse(
            self.client_location._get_stock_request_source_location()
        )
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self._submit_order(
            [(self.product_a, 500)], location=self.client_location
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.env["stock.request.order"].search_count(
                [("requested_by", "=", self.portal_user.id)]
            )
        )

    def test_portal_catalog_carries_set_aside_quantities(self):
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        self._set_aside_stock(self.child_partner, product, 4)
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        match = re.search(r'data-set-aside="([^"]*)"', response.text)
        self.assertTrue(match, "Set aside quantities not found in page")
        set_aside = json.loads(html.unescape(match.group(1)))
        # only the location with stock set aside is limited
        self.assertEqual(
            set_aside, {str(self.client_location_b.id): {str(product.id): 4.0}}
        )

    def test_portal_catalog_only_renders_set_aside_products(self):
        """A user whose locations all have stock set aside never receives
        the rest of the catalog."""
        product = self.env["product.product"].create(
            {"name": "Storable Product", "type": "consu", "is_storable": True}
        )
        self._set_aside_stock(self.child_partner, product, 4)
        self.client_partner.stock_request_supervisor_ids = [Command.clear()]
        self.authenticate("portal_client", "P0rtalClient1!")
        response = self.url_open("/my/stock-request-orders/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-product-name="Storable Product"', response.text)
        self.assertNotIn('data-product-name="Product A"', response.text)
        self.assertNotIn('data-product-name="Product B"', response.text)
