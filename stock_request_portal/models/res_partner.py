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
    stock_request_supervisor_ids = fields.Many2many(
        "res.partner",
        "res_partner_stock_request_supervisor_rel",
        "partner_id",
        "supervisor_id",
        string="Stock Request Supervisors",
        help="Contacts allowed to create stock request orders from the "
        "portal for the destination location of this contact.",
    )
