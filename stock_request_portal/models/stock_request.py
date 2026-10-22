from odoo import models


class StockRequest(models.Model):
    _inherit = "stock.request"

    def _get_supply_procurement(self, qty, from_set_aside=True):
        """The transfers to the obra carry its contact (e.g. for the delivery
        slip). Only the transfers: on the purchase of the missing quantity
        the partner would become the dropship address of the RFQ."""
        procurement = super()._get_supply_procurement(
            qty, from_set_aside=from_set_aside
        )
        partner = self.location_id._get_stock_request_partner()
        if partner:
            procurement.values["partner_id"] = partner.id
        return procurement
