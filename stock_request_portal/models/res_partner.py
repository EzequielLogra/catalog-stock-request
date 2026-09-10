from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    stock_request_location_id = fields.Many2one(
        "stock.location",
        string="Stock Request Destination Location",
        domain=[("usage", "in", ["internal", "transit"])],
        help="Destination location for the stock request orders this client "
        "creates from the portal. Configure it once per client contact.",
    )
