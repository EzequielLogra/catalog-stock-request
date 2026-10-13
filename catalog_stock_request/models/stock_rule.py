from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_stock_move_values(
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
        """Take the products from the stock set aside for the destination of
        the stock request, instead of the source location of the rule."""
        result = super()._get_stock_move_values(
            product_id,
            product_qty,
            product_uom,
            location_id,
            name,
            origin,
            company_id,
            values,
        )
        if values.get("stock_request_source_location_id"):
            result["location_id"] = values["stock_request_source_location_id"]
        return result

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
