from odoo import models


class StockRequest(models.Model):
    _inherit = "stock.request"

    def _prepare_procurement_values(self, reference_ids=False):
        """Un pedido de obra hecho desde el portal por un supervisor de la obra
        deja a ese supervisor en el traslado. Si lo carga otro (por ejemplo el
        pañolero), queda vacío para elegirlo a mano."""
        values = super()._prepare_procurement_values(reference_ids=reference_ids)
        supervisor = self._get_delivery_supervisor()
        if supervisor:
            values["delivery_supervisor_id"] = supervisor.id
        return values

    def _get_delivery_supervisor(self):
        self.ensure_one()
        requester = self.requested_by.partner_id
        obra = self.location_id._get_stock_request_partner()
        if requester and requester in obra._get_delivery_supervisors():
            return requester
        return self.env["res.partner"]
