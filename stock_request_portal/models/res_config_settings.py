from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_request_portal_show_available = fields.Boolean(
        string="Show Available Quantity in Portal",
        config_parameter="stock_request_portal.show_available",
    )
