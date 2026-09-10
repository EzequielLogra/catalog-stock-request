from odoo import models


class StockRequestOrder(models.Model):
    _inherit = "stock.request.order"

    def _notify_portal_submission(self):
        """Log the portal submission in the chatter and notify managers."""
        self.ensure_one()
        body = self.env._(
            "Stock request order %(name)s was submitted from the portal by "
            "%(user)s and is pending review.",
            name=self.name,
            user=self.requested_by.name,
        )
        self.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        managers = (
            self.env.ref("stock_request.group_stock_request_manager")
            .user_ids.filtered("active")
        )
        partners = managers.mapped("partner_id")
        if partners:
            self.message_notify(
                partner_ids=partners.ids,
                subject=self.env._(
                    "New portal stock request %(name)s", name=self.name
                ),
                body=body,
            )
