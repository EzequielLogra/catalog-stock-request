from odoo import api, models


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def _get_procurements_to_merge_groupby(self, procurement):
        """Purchases of different obras are not merged in the same line."""
        distribution = (
            procurement.values.get("stock_request_analytic_distribution") or {}
        )
        return super()._get_procurements_to_merge_groupby(procurement) + (
            tuple(sorted(distribution.items())),
        )
