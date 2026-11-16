from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    delivery_supervisor_id = fields.Many2one(
        "res.partner",
        string="Supervisor que recibe",
        readonly=True,
    )

    def _get_new_picking_values(self):
        values = super()._get_new_picking_values()
        supervisor = self.delivery_supervisor_id[:1]
        if supervisor:
            values["supervisor_id"] = supervisor.id
        return values

    def _prepare_procurement_values(self):
        """El supervisor sigue en los traslados encadenados (pre-obra -> obra)."""
        values = super()._prepare_procurement_values()
        if self.delivery_supervisor_id:
            values["delivery_supervisor_id"] = self.delivery_supervisor_id.id
        return values
