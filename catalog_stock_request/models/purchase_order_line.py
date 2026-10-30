from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    stock_request_source_location_id = fields.Many2one(
        "stock.location",
        string="Set Aside Location",
        copy=False,
        readonly=True,
        help="Location holding the stock set aside for the destination of "
        "the stock requests behind this line. The products are received "
        "there and leave with the rest of the request.",
    )

    @api.model
    def _prepare_purchase_order_line_from_procurement(
        self,
        product_id,
        product_qty,
        product_uom,
        location_dest_id,
        name,
        origin,
        company_id,
        values,
        po,
    ):
        vals = super()._prepare_purchase_order_line_from_procurement(
            product_id,
            product_qty,
            product_uom,
            location_dest_id,
            name,
            origin,
            company_id,
            values,
            po,
        )
        if values.get("stock_request_source_location_id"):
            vals["stock_request_source_location_id"] = values[
                "stock_request_source_location_id"
            ]
        return vals

    def _find_candidate(
        self,
        product_id,
        product_qty,
        product_uom,
        location_id,
        name,
        origin,
        company_id,
        values,
    ):
        """Only merge purchases that are received in the same location."""
        source_location_id = values.get("stock_request_source_location_id") or False
        lines = self.filtered(
            lambda line: line.stock_request_source_location_id.id
            == source_location_id
        )
        return super(PurchaseOrderLine, lines)._find_candidate(
            product_id,
            product_qty,
            product_uom,
            location_id,
            name,
            origin,
            company_id,
            values,
        )

    def _prepare_stock_move_vals(
        self, picking, price_unit, product_uom_qty, product_uom
    ):
        vals = super()._prepare_stock_move_vals(
            picking, price_unit, product_uom_qty, product_uom
        )
        if self.stock_request_source_location_id:
            vals["location_dest_id"] = self.stock_request_source_location_id.id
            vals["location_final_id"] = self.stock_request_source_location_id.id
        return vals

    def _prepare_stock_moves(self, picking):
        """The stock requests are fulfilled by the transfer that leaves the
        set aside location; allocating the receipt to them as well would
        offset the quantity done."""
        res = super()._prepare_stock_moves(picking)
        if self.stock_request_source_location_id:
            for vals in res:
                vals.pop("allocation_ids", None)
            return res
        # Purchases of what is set aside without stock are received in the
        # warehouse stock, but the requests behind them are fulfilled from
        # the set aside location as well.
        set_aside_requests = self.stock_request_ids.filtered(
            lambda request: request._get_source_location()
        )
        if set_aside_requests:
            for vals in res:
                vals["allocation_ids"] = [
                    command
                    for command in vals.get("allocation_ids", [])
                    if command[2].get("stock_request_id")
                    not in set_aside_requests.ids
                ]
        return res
