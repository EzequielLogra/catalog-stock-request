from odoo import models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _get_stock_request_source_location(self):
        """Return the location holding the stock set aside for this
        destination location, if any. Stock requests for a destination that
        has one are supplied only from it and never purchased."""
        self.ensure_one()
        return self.env["stock.location"]
