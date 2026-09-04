from odoo import api, fields, models
from odoo.fields import Domain


class StockRequestOrder(models.Model):
    _name = "stock.request.order"
    _inherit = ["stock.request.order", "product.catalog.mixin"]

    split_purchase = fields.Boolean(
        string="Split Stock / Purchase",
        default=False,
        copy=False,
        help="If enabled, confirming this order reserves the free stock "
        "available in the warehouse and creates RFQs only for the missing "
        "quantities.",
    )
    purchase_route_id = fields.Many2one(
        "stock.route",
        string="Purchase Route",
        compute="_compute_purchase_route_id",
        store=True,
        readonly=False,
        check_company=True,
        domain=[("rule_ids.action", "=", "buy")],
        help="Route used to purchase the missing quantity of the request "
        "lines when confirming this order.",
    )

    @api.depends("warehouse_id")
    def _compute_purchase_route_id(self):
        for order in self:
            if not order.purchase_route_id and order.warehouse_id:
                order.purchase_route_id = (
                    order.warehouse_id.buy_pull_id.route_id
                )

    def _default_order_line_values(self, child_field=False):
        default_data = super()._default_order_line_values(child_field)
        new_default_data = (
            self.env["stock.request"]._get_product_catalog_lines_data()
        )
        return {**default_data, **new_default_data}

    def _get_action_add_from_catalog_extra_context(self):
        return {
            **super()._get_action_add_from_catalog_extra_context(),
            "order_id": self.id,
        }

    def _get_product_catalog_domain(self):
        return super()._get_product_catalog_domain() & Domain(
            "type", "!=", "service"
        )

    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        grouped_requests = {}
        requests = self.stock_request_ids.filtered(
            lambda r: r.state != "cancel" and r.product_id.id in product_ids
        )
        for request in requests:
            product = request.product_id
            if product not in grouped_requests:
                grouped_requests[product] = self.env["stock.request"]
            grouped_requests[product] |= request
        return grouped_requests

    def _is_readonly(self):
        self.ensure_one()
        return self.state != "draft"

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        self.ensure_one()
        if self.state != "draft":
            return 0.0
        requests = self.stock_request_ids.filtered(
            lambda r: r.state == "draft" and r.product_id.id == product_id
        )
        if not quantity:
            requests.unlink()
            return 0.0
        if requests:
            requests[:1].product_uom_qty = quantity
            return 0.0
        self.env["stock.request"].create(
            {
                "order_id": self.id,
                "product_id": product_id,
                "product_uom_id": self.env["product.product"]
                .browse(product_id)
                .uom_id.id,
                "product_uom_qty": quantity,
                "requested_by": self.requested_by.id,
                "expected_date": self.expected_date,
                "picking_policy": self.picking_policy,
                "warehouse_id": self.warehouse_id.id,
                "location_id": self.location_id.id,
                "company_id": self.company_id.id,
                "reference_ids": [(6, 0, self.reference_ids.ids)],
                "route_id": self.route_id.id,
            }
        )
        return 0.0
