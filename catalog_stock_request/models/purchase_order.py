from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    obra_location_id = fields.Many2one(
        "stock.location",
        string="Obra",
        compute="_compute_obra_location_id",
        store=True,
        help="Destination location of the stock request order that "
        "generated this purchase. Empty for manual purchases.",
    )

    @api.depends("order_line.stock_request_ids")
    def _compute_obra_location_id(self):
        for order in self:
            requests = order.order_line.stock_request_ids.filtered("order_id")
            order.obra_location_id = (
                requests[:1].order_id.location_id if requests else False
            )
