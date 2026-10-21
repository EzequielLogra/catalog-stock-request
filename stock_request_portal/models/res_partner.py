from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    stock_request_location_id = fields.Many2one(
        "stock.location",
        string="Stock Request Destination Location",
        domain=[("usage", "in", ["internal", "transit"])],
        help="Destination location for the stock request orders this client "
        "creates from the portal. Configure it once per client contact.",
    )
    stock_request_supervisor_ids = fields.Many2many(
        "res.partner",
        "res_partner_stock_request_supervisor_rel",
        "partner_id",
        "supervisor_id",
        string="Stock Request Supervisors",
        help="Contacts allowed to create stock request orders from the "
        "portal for the destination location of this contact.",
    )

    def _get_stock_request_set_aside_location(self):
        """Return the pre-obra of the contact: its customer location when it
        is internal (sales delivered to the contact are set aside there)."""
        self.ensure_one()
        location = self.property_stock_customer
        if (
            location.usage == "internal"
            and location != self.stock_request_location_id
        ):
            return location
        return self.env["stock.location"]

    @api.constrains("parent_id", "property_stock_customer")
    def _check_stock_request_set_aside_location(self):
        """The pre-obra belongs to the contact of the obra (a child contact
        of the client), never to the client itself: a client can have many
        obras, each one with its own pre-obra."""
        for partner in self:
            if (
                not partner.parent_id
                and partner._get_stock_request_set_aside_location()
            ):
                raise ValidationError(
                    self.env._(
                        "%(contact)s cannot have an internal customer "
                        "location (pre-obra). Create a delivery address for "
                        "each obra under %(contact)s and set its pre-obra "
                        "there.",
                        contact=partner.display_name,
                    )
                )
