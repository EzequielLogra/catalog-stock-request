from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _prepare_purchase_order(self, company_id, origins, values):
        """Enrich the purchase order origin with the obra (destination
        location) and client of the stock request orders behind it."""
        vals = super()._prepare_purchase_order(company_id, origins, values)
        orders = (
            self.env["stock.request.order"]
            .sudo()
            .search([("name", "in", list(origins))], order="id asc")
        )
        if not orders:
            return vals
        labels = [order._get_purchase_origin_label() for order in orders]
        matched_names = set(orders.mapped("name"))
        labels += sorted(origin for origin in origins if origin not in matched_names)
        vals["origin"] = ", ".join(labels)
        return vals
