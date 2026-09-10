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
    _stock_request_catalog_page_size = 30

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
            raise MissingError
        user_partner = request.env.user.partner_id
        if (
            order.requested_by.partner_id.commercial_partner_id
            != user_partner.commercial_partner_id
        ):
            raise AccessError
        return order

    def _get_stock_request_destination_location(self):
        partner = request.env.user.partner_id
        return (
            partner.commercial_partner_id.stock_request_location_id
            or partner.stock_request_location_id
        )

    def _get_stock_request_warehouse(self):
        company = request.website.company_id
        return (
            request.env["stock.warehouse"]
            .sudo()
            .search([("company_id", "=", company.id)], limit=1)
        )

    def _get_stock_request_categories(self):
        groups = request.env["product.product"].sudo()._read_group(
            [("type", "in", ["product", "consu"])],
            groupby=["categ_id"],
            aggregates=["__count"],
        )
        categ_ids = [categ.id for categ, count in groups if categ]
        return request.env["product.category"].sudo().search(
            [("id", "in", categ_ids)],
            order="complete_name asc",
        )

    def _get_stock_request_catalog_domain(self, category=None):
        domain = [("type", "in", ["product", "consu"])]
        if category:
            domain.append(("categ_id", "child_of", category.id))
        return domain

    def _prepare_stock_request_form_values(
        self, error=None, category_id=None, page=1
    ):
        values = self._prepare_portal_layout_values()
        warehouse = self._get_stock_request_warehouse()
        Product = request.env["product.product"].sudo()
        category = request.env["product.category"]
        if category_id:
            try:
                category = (
                    request.env["product.category"]
                    .sudo()
                    .browse(int(category_id))
                    .exists()
                )
            except (TypeError, ValueError):
                category = request.env["product.category"]
        domain = self._get_stock_request_catalog_domain(category)
        url_args = {}
        if category:
            url_args["category_id"] = category.id
        pager_values = portal_pager(
            url="/my/stock-request-orders/new",
            total=Product.search_count(domain),
            page=page,
            step=self._stock_request_catalog_page_size,
            url_args=url_args,
        )
        products = Product.search(
            domain,
            order="name asc",
            limit=self._stock_request_catalog_page_size,
            offset=pager_values["offset"],
        )
        values.update(
            {
                "page_name": "stock_request_order_new",
                "error": error,
                "products": products,
                "categories": self._get_stock_request_categories(),
                "category": category,
                "category_id": category.id or None,
                "pager": pager_values,
                "default_url": "/my/stock-request-orders/new",
                "warehouse": warehouse,
                "location": self._get_stock_request_destination_location(),
                "default_expected_date": fields.Datetime.now()
                .replace(microsecond=0)
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
    def portal_stock_request_order_new(
        self, error=None, category_id=None, page=1, **kwargs
    ):
        values = self._prepare_stock_request_form_values(
            error=error, category_id=category_id, page=page
        )
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

        location = self._get_stock_request_destination_location()
        if not location:
            error = request.env._(
                "Your contact has no stock request destination location "
                "configured yet. Please contact us."
            )

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

        lines = []
        if not error:
            lines, error = self._parse_stock_request_lines(form)

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
            }
        )
        return request.render(
            "stock_request_portal.portal_stock_request_order_page", values
        )
