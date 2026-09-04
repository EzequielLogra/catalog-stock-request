from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    supplier_rank = fields.Integer(
        string="Supplier Ranking",
        default=0,
        help="Manual supplier ranking used to suggest purchase suppliers for "
        "stock requests. Lower values have priority (0 = no priority).",
    )
