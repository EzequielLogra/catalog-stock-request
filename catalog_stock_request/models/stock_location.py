from odoo import api, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _get_stock_request_source_location(self):
        """Return the location holding the stock set aside for this
        destination location, if any. Stock requests for a destination that
        has one are supplied from it first, then from the warehouse stock;
        the missing quantity is purchased and received there."""
        self.ensure_one()
        return self.env["stock.location"]

    @api.model
    def _get_stock_request_set_aside_locations(self):
        """Return every location holding stock set aside for a destination.
        That stock is not free for other destinations."""
        return self.env["stock.location"]
