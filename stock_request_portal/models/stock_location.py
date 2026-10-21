from odoo import api, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _get_stock_request_source_location(self):
        """The stock set aside for a destination location is the internal
        customer location of the contact that owns it: sales delivered to
        that contact move the products there."""
        self.ensure_one()
        partners = (
            self.env["res.partner"]
            .sudo()
            .with_company(self.company_id or self.env.company)
            .search([("stock_request_location_id", "=", self.id)])
        )
        for partner in partners:
            source_location = partner._get_stock_request_set_aside_location()
            if source_location:
                return source_location
        return super()._get_stock_request_source_location()

    @api.model
    def _get_stock_request_set_aside_locations(self):
        partners = (
            self.env["res.partner"]
            .sudo()
            .with_company(self.env.company)
            .search([("stock_request_location_id", "!=", False)])
        )
        set_aside = self.env["stock.location"]
        for partner in partners:
            set_aside |= partner._get_stock_request_set_aside_location()
        return set_aside | super()._get_stock_request_set_aside_locations()
