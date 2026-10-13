from odoo import models


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
        source_locations = partners.mapped("property_stock_customer").filtered(
            lambda location: location.usage == "internal" and location != self
        )
        return source_locations[:1] or super()._get_stock_request_source_location()
