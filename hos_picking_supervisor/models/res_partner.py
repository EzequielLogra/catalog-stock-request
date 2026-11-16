from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_delivery_supervisors(self):
        """Supervisores que pueden recibir el material de esta obra: los
        cargados en el subcontacto de la obra."""
        return self.stock_request_supervisor_ids
