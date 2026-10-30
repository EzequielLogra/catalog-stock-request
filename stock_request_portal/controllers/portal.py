import json
import re

import pytz

from odoo import fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Command
from odoo.http import request

from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)


class CustomerPortal(CustomerPortal):

    _stock_request_items_per_page = 20
    _stock_request_products_per_page = 20
    # CSS variable -> system parameter holding its color
    _stock_request_color_params = {
        "--o-sr-primary": "stock_request_portal.color_primary",
        "--o-sr-accent": "stock_request_portal.color_accent",
    }
    _stock_request_color_re = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}")

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _prepare_stock_request_orders_domain(self):
        partner = request.env.user.partner_id
        return [
            (
                "requested_by.partner_id.commercial_partner_id",
                "=",
                partner.commercial_partner_id.id,
            )
        ]

    def _get_stock_request_order_sudo(self, order_id):
        """Return the order (sudoed) if it belongs to the current portal
        user's commercial partner, raise otherwise."""
        order = (
            request.env["stock.request.order"]
            .sudo()
            .browse(order_id)
            .exists()
        )
        if not order:
            raise MissingError(
                request.env._("This document does not exist.")
            )
        user_partner = request.env.user.partner_id
        if (
            order.requested_by.partner_id.commercial_partner_id
            != user_partner.commercial_partner_id
        ):
            raise AccessError(
                request.env._(
                    "You are not allowed to access this document."
                )
            )
        return order

    def _get_stock_request_destination_locations(self):
        """Return the destination locations the portal user may select:
        those of the active contacts (one contact per delivery point) the
        user is assigned to as supervisor."""
        partner = request.env.user.partner_id
        return (
            request.env["res.partner"]
            .sudo()
            .search(
                [
                    ("stock_request_supervisor_ids", "in", partner.ids),
                    ("active", "=", True),
                ]
            )
            .mapped("stock_request_location_id")
        )

    def _get_stock_request_warehouse(self):
        company = request.website.company_id
        return (
            request.env["stock.warehouse"]
            .sudo()
            .search([("company_id", "=", company.id)], limit=1)
        )

    def _get_stock_request_categories(self, products, offered_products):
        """Return [{"category": record, "count": int}, ...] for the catalog
        chips, alphabetically by category. Every category of the catalog
        gets a chip; the count is over the products offered to the
        location selected by default."""
        counts = {}
        for product in offered_products:
            counts[product.categ_id.id] = counts.get(product.categ_id.id, 0) + 1
        category_ids = {product.categ_id.id for product in products}
        categories = request.env["product.category"].sudo().search(
            [("id", "in", list(category_ids))],
            order="complete_name asc",
        )
        return [
            {"category": category, "count": counts.get(category.id, 0)}
            for category in categories
        ]

    def _get_stock_request_products(self, locations, set_aside):
        """Products of the catalog. A user whose locations all have stock
        set aside only gets the products set aside for them."""
        domain = [("type", "in", ["product", "consu"])]
        if locations and all(location.id in set_aside for location in locations):
            product_ids = set()
            for location in locations:
                product_ids.update(set_aside[location.id])
            domain.append(("id", "in", list(product_ids)))
        products = request.env["product.product"].sudo().search(domain)
        # Dotted order terms like "categ_id.complete_name" are not
        # supported by the ORM here, so sort in Python (small catalogs).
        return sorted(
            products,
            key=lambda product: (
                product.categ_id.complete_name or "",
                product.name or "",
            ),
        )

    def _get_stock_request_set_aside_quantities(self, locations):
        """Return {location id: {product id: free quantity}} for the
        destination locations that have stock set aside. The catalog only
        offers them the products assigned to their set aside location (in
        stock there or on their way to it), with the free quantity as a
        reference: asking for more is purchased. Other locations are not
        limited."""
        result = {}
        Quant = request.env["stock.quant"].sudo()
        Move = request.env["stock.move"].sudo()
        for location in locations:
            source_location = location._get_stock_request_source_location()
            if not source_location:
                continue
            groups = Quant._read_group(
                [("location_id", "=", source_location.id)],
                groupby=["product_id"],
                aggregates=["quantity:sum", "reserved_quantity:sum"],
            )
            quantities = {
                product.id: max(0.0, quantity - reserved)
                for product, quantity, reserved in groups
            }
            incoming = Move._read_group(
                [
                    ("location_dest_id", "=", source_location.id),
                    ("state", "!=", "cancel"),
                ],
                groupby=["product_id"],
            )
            for (product,) in incoming:
                quantities.setdefault(product.id, 0.0)
            result[location.id] = quantities
        return result

    def _get_stock_request_show_available(self):
        """Whether the catalog shows the free quantity of the set aside
        stock (Settings > Stock Request)."""
        return bool(
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("stock_request_portal.show_available")
        )

    def _get_stock_request_tz(self):
        """Timezone in which the portal user reads and types dates."""
        return pytz.timezone(
            request.env.user.tz or request.env.context.get("tz") or "UTC"
        )

    def _get_stock_request_portal_style(self):
        """Return the inline CSS variables that theme the catalog, read
        from the system parameters. Missing or invalid colors are skipped
        so the stylesheet falls back to the website theme."""
        get_param = request.env["ir.config_parameter"].sudo().get_param
        declarations = []
        for variable, key in self._stock_request_color_params.items():
            color = (get_param(key) or "").strip()
            if self._stock_request_color_re.fullmatch(color):
                declarations.append(f"{variable}: {color}")
        return "; ".join(declarations) or None

    def _prepare_stock_request_form_values(self, error=None):
        values = self._prepare_portal_layout_values()
        locations = self._get_stock_request_destination_locations()
        set_aside = self._get_stock_request_set_aside_quantities(locations)
        products = self._get_stock_request_products(locations, set_aside)
        # What the location selected by default (the first one) may
        # request; None when it is not limited. The page is rendered for
        # it and the client takes over when another location is chosen.
        default_available = set_aside.get(locations[:1].id)
        offered_products = [
            product
            for product in products
            if default_available is None or product.id in default_available
        ]
        per_page = self._stock_request_products_per_page
        show_available = self._get_stock_request_show_available()
        # The client only needs the assigned products to filter the catalog,
        # so the quantities do not reach the page unless they are shown.
        if not show_available:
            set_aside = {
                location_id: dict.fromkeys(quantities)
                for location_id, quantities in set_aside.items()
            }
        values.update(
            {
                "show_available": show_available,
                "page_name": "stock_request_order_new",
                "error": error,
                "products": products,
                "categories": self._get_stock_request_categories(
                    products, offered_products
                ),
                "offered_count": len(offered_products),
                "first_page_product_ids": {
                    product.id for product in offered_products[:per_page]
                },
                "default_available": default_available,
                "products_per_page": per_page,
                "sr_style": self._get_stock_request_portal_style(),
                "warehouse": self._get_stock_request_warehouse(),
                "locations": locations,
                "set_aside_json": json.dumps(set_aside),
                "default_expected_date": pytz.utc.localize(
                    fields.Datetime.now()
                )
                .astimezone(self._get_stock_request_tz())
                .strftime("%Y-%m-%dT%H:%M"),
            }
        )
        return values

    def _parse_stock_request_lines(self, form):
        """Return (lines, error) from the posted form data."""
        lines = []
        product_ids = form.getlist("product_id")
        quantities = form.getlist("product_uom_qty")
        Product = request.env["product.product"].sudo()
        for str_product_id, str_qty in zip(product_ids, quantities):
            str_product_id = (str_product_id or "").strip()
            str_qty = (str_qty or "").strip()
            if not str_product_id:
                continue
            try:
                qty = float(str_qty)
            except ValueError:
                return [], request.env._("Invalid quantity %s.", str_qty)
            if qty <= 0:
                return [], request.env._(
                    "Quantities must be greater than zero."
                )
            product = Product.browse(int(str_product_id)).exists()
            if not product or product.type not in ("product", "consu"):
                return [], request.env._("Invalid product selected.")
            lines.append({"product": product, "qty": qty})
        if not lines:
            return [], request.env._(
                "Add at least one product line to submit a request."
            )
        return lines, None

    def _check_stock_request_set_aside_products(self, location, lines):
        """Return an error when the lines ask for a product that is not
        assigned to the stock set aside for the destination location. The
        quantities are not limited: what is missing is purchased. Locations
        without stock set aside are not limited."""
        assigned = self._get_stock_request_set_aside_quantities(location).get(
            location.id
        )
        if assigned is None:
            return None
        for line in lines:
            if line["product"].id not in assigned:
                return request.env._(
                    "%(product)s is not assigned to %(location)s.",
                    product=line["product"].display_name,
                    location=location.name,
                )
        return None

    # ------------------------------------------------------------------
    # /my home counter
    # ------------------------------------------------------------------

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "stock_request_order_count" in counters:
            StockRequestOrder = request.env["stock.request.order"]
            values["stock_request_order_count"] = StockRequestOrder.sudo(
            ).search_count(self._prepare_stock_request_orders_domain())
        return values

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @http.route(
        [
            "/my/stock-request-orders",
            "/my/stock-request-orders/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_stock_request_orders(self, page=1, sortby=None, **kwargs):
        StockRequestOrder = request.env["stock.request.order"]
        values = self._prepare_portal_layout_values()
        domain = self._prepare_stock_request_orders_domain()

        searchbar_sortings = {
            "date": {
                "label": request.env._("Newest"),
                "order": "create_date desc, id desc",
            },
            "name": {
                "label": request.env._("Reference"),
                "order": "name desc",
            },
            "expected_date": {
                "label": request.env._("Expected Date"),
                "order": "expected_date asc, id asc",
            },
        }
        if not sortby:
            sortby = "date"
        sort_order = searchbar_sortings[sortby]["order"]

        pager_values = portal_pager(
            url="/my/stock-request-orders",
            total=StockRequestOrder.sudo().search_count(domain),
            page=page,
            step=self._stock_request_items_per_page,
            url_args={"sortby": sortby},
        )
        orders = StockRequestOrder.sudo().search(
            domain,
            order=sort_order,
            limit=self._stock_request_items_per_page,
            offset=pager_values["offset"],
        )

        values.update(
            {
                "orders": orders,
                "page_name": "stock_request_order",
                "pager": pager_values,
                "default_url": "/my/stock-request-orders",
                "sortby": sortby,
                "searchbar_sortings": searchbar_sortings,
            }
        )
        return request.render(
            "stock_request_portal.portal_my_stock_request_orders", values
        )

    # ------------------------------------------------------------------
    # New order form
    # ------------------------------------------------------------------

    @http.route(
        ["/my/stock-request-orders/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def portal_stock_request_order_new(self, error=None, **kwargs):
        values = self._prepare_stock_request_form_values(error=error)
        return request.render(
            "stock_request_portal.portal_stock_request_order_new", values
        )

    @http.route(
        ["/my/stock-request-orders/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        sitemap=False,
    )
    def portal_stock_request_order_create(self, **post):
        form = request.httprequest.form
        error = None

        locations = self._get_stock_request_destination_locations()
        if not locations:
            error = request.env._(
                "Your contact has no stock request destination "
                "locations configured yet. Please contact us."
            )

        # Fall back to the first allowed location when the posted one is
        # missing or does not belong to the contact.
        location = locations[:1]
        str_location_id = (form.get("location_id") or "").strip()
        if str_location_id:
            try:
                chosen = (
                    request.env["stock.location"]
                    .sudo()
                    .browse(int(str_location_id))
                    .exists()
                )
            except ValueError:
                chosen = request.env["stock.location"]
            if chosen in locations:
                location = chosen

        expected_date = None
        raw_expected_date = (form.get("expected_date") or "").strip()
        if not error:
            if not raw_expected_date:
                error = request.env._("Expected date is required.")
            else:
                try:
                    expected_date = fields.Datetime.to_datetime(
                        raw_expected_date.replace("T", " ")
                    )
                except ValueError:
                    expected_date = None
                if not expected_date:
                    error = request.env._("Invalid expected date.")
                else:
                    # The form sends the user's local time; store UTC.
                    expected_date = (
                        self._get_stock_request_tz()
                        .localize(expected_date)
                        .astimezone(pytz.utc)
                        .replace(tzinfo=None)
                    )

        lines = []
        if not error:
            lines, error = self._parse_stock_request_lines(form)
        if not error:
            error = self._check_stock_request_set_aside_products(location, lines)

        warehouse = self._get_stock_request_warehouse()
        if not error and not warehouse:
            error = request.env._(
                "No warehouse is configured for the current company."
            )

        if error:
            values = self._prepare_stock_request_form_values(error=error)
            return request.render(
                "stock_request_portal.portal_stock_request_order_new", values
            )

        company = request.website.company_id
        order = request.env["stock.request.order"].sudo().create(
            {
                "company_id": company.id,
                "warehouse_id": warehouse.id,
                "location_id": location.id,
                "expected_date": expected_date,
                "requested_by": request.env.user.id,
                "split_purchase": True,
                "stock_request_ids": [
                    Command.create(
                        {
                            "product_id": line["product"].id,
                            "product_uom_id": line["product"].uom_id.id,
                            "product_uom_qty": line["qty"],
                            "company_id": company.id,
                            "warehouse_id": warehouse.id,
                            "location_id": location.id,
                            "expected_date": expected_date,
                            "requested_by": request.env.user.id,
                        }
                    )
                    for line in lines
                ],
            }
        )
        order._notify_portal_submission()
        return request.redirect(
            f"/my/stock-request-orders/{order.id}?message=submitted"
        )

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    @http.route(
        ["/my/stock-request-orders/<int:order_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_stock_request_order_page(
        self, order_id, message=None, **kwargs
    ):
        try:
            order_sudo = self._get_stock_request_order_sudo(order_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "stock_request_order",
                "order": order_sudo,
                "message": message,
                "show_supply_split": request.env.user._is_internal(),
            }
        )
        return request.render(
            "stock_request_portal.portal_stock_request_order_page", values
        )
