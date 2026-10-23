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

    def _get_purchase_procurement(self, qty, purchase_route):
        """The purchase of the missing quantity is charged to the obra, with
        the analytic distribution its sales get."""
        procurement = super()._get_purchase_procurement(qty, purchase_route)
        distribution = self._get_obra_analytic_distribution()
        if distribution:
            procurement.values["stock_request_analytic_distribution"] = (
                distribution
            )
        return procurement

    def _get_obra_analytic_distribution(self):
        """Distribution of the analytic models of the contact of the obra,
        matched as on a sale order to that contact."""
        self.ensure_one()
        partner = self.location_id._get_stock_request_partner()
        if not partner:
            return {}
        return (
            self.env["account.analytic.distribution.model"]
            .sudo()
            ._get_distribution(
                {
                    "product_id": self.product_id.id,
                    "product_categ_id": self.product_id.categ_id.id,
                    "partner_id": partner.id,
                    "partner_category_id": partner.category_id.ids,
                    "company_id": self.company_id.id,
                }
            )
        )
