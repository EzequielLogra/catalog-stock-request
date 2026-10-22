from odoo import api, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _get_stock_request_partners(self):
        """Contacts whose stock request destination is this location."""
        self.ensure_one()
        return (
            self.env["res.partner"]
            .sudo()
            .with_company(self.company_id or self.env.company)
            .search([("stock_request_location_id", "=", self.id)])
        )

    def _get_stock_request_partner(self):
        """The contact of the obra, set on the transfers to it: the one
        holding its pre-obra if any, otherwise the first one."""
        self.ensure_one()
        partners = self._get_stock_request_partners()
        return (
            partners.filtered(
                lambda partner: partner._get_stock_request_set_aside_location()
            )[:1]
            or partners[:1]
        )

    def _get_stock_request_source_location(self):
        """The stock set aside for a destination location is the internal
        customer location of the contact that owns it: sales delivered to
        that contact move the products there."""
        self.ensure_one()
        partners = self._get_stock_request_partners()
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
