from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    supervisor_id = fields.Many2one(
        "res.partner",
        string="Entregar a (supervisor)",
        domain="[('id', 'in', allowed_supervisor_ids)]",
        index="btree_not_null",
        tracking=True,
        help="Supervisor de la obra que recibe el material y firma el remito. "
        "Se elige entre los supervisores cargados en el contacto de la obra.",
    )
    allowed_supervisor_ids = fields.Many2many(
        "res.partner",
        compute="_compute_allowed_supervisor_ids",
    )

    @api.depends("partner_id.stock_request_supervisor_ids")
    def _compute_allowed_supervisor_ids(self):
        for picking in self:
            picking.allowed_supervisor_ids = (
                picking.partner_id._get_delivery_supervisors()
            )

    @api.onchange("partner_id")
    def _onchange_partner_id_supervisor(self):
        if self.supervisor_id not in self.allowed_supervisor_ids:
            self.supervisor_id = False
