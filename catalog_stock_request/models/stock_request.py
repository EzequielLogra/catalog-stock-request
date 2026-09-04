from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockRequest(models.Model):
    _inherit = "stock.request"

    free_qty = fields.Float(
        string="Free To Use",
        compute="_compute_free_qty",
        digits="Product Unit of Measure",
        help="Free quantity in the warehouse stock location.",
    )
    qty_reserved = fields.Float(
        string="Reserved Quantity",
        compute="_compute_qty_reserved",
        digits="Product Unit of Measure",
        help="Quantity reserved by the internal transfer of this request.",
    )
    qty_to_purchase = fields.Float(
        string="Quantity To Purchase",
        compute="_compute_qty_to_purchase",
        digits="Product Unit of Measure",
        help="Missing quantity that will be purchased (estimated in draft, "
        "real once confirmed).",
    )
    qty_from_stock = fields.Float(
        string="Quantity From Stock",
        readonly=True,
        copy=False,
        digits="Product Unit of Measure",
    )
    qty_purchased = fields.Float(
        string="Purchased Quantity",
        readonly=True,
        copy=False,
        digits="Product Unit of Measure",
    )
    suggested_supplier_id = fields.Many2one(
        "res.partner",
        string="Suggested Supplier",
        compute="_compute_suggested_supplier_id",
        help="Supplier suggested according to the manual partner ranking and "
        "the vendor pricelists of the product.",
    )

    @api.depends("product_id", "warehouse_id", "product_uom_id")
    def _compute_free_qty(self):
        for request in self:
            request.free_qty = request._get_free_qty()

    @api.depends(
        "allocation_ids",
        "allocation_ids.stock_move_id",
        "allocation_ids.stock_move_id.state",
        "allocation_ids.stock_move_id.quantity",
    )
    def _compute_qty_reserved(self):
        for request in self:
            moves = request.allocation_ids.stock_move_id.filtered(
                lambda m: m.picking_code in ("internal", "outgoing")
                and m.state not in ("cancel", "done")
            )
            qty = 0.0
            for move in moves:
                qty += request.product_id.uom_id._compute_quantity(
                    move.quantity,
                    request.product_uom_id,
                    rounding_method="HALF-UP",
                )
            request.qty_reserved = qty

    @api.depends(
        "product_uom_qty",
        "free_qty",
        "state",
        "qty_purchased",
    )
    def _compute_qty_to_purchase(self):
        for request in self:
            if request.state == "draft":
                request.qty_to_purchase = max(
                    0.0,
                    request.product_uom_qty
                    - min(request.product_uom_qty, request.free_qty),
                )
            else:
                request.qty_to_purchase = request.qty_purchased

    @api.depends("product_id", "product_uom_qty", "company_id")
    def _compute_suggested_supplier_id(self):
        for request in self:
            seller = request._get_seller(request.product_uom_qty)
            request.suggested_supplier_id = seller.partner_id

    def _get_free_qty(self):
        self.ensure_one()
        if not self.product_id or not self.warehouse_id:
            return 0.0
        product = self.product_id.with_context(
            location=self.warehouse_id.lot_stock_id.id
        )
        return self.product_id.uom_id._compute_quantity(
            product.free_qty, self.product_uom_id, rounding_method="HALF-UP"
        )

    def _get_seller(self, qty):
        self.ensure_one()
        if not self.product_id:
            return self.env["product.supplierinfo"]
        sellers = self.product_id.with_company(
            self.company_id.id
        )._prepare_sellers(False)
        valid = sellers.filtered(lambda s: s.min_qty <= qty)
        candidates = valid or sellers
        if not candidates:
            return self.env["product.supplierinfo"]
        return min(
            candidates,
            key=lambda s: (
                s.partner_id.supplier_rank
                if s.partner_id.supplier_rank
                else 99999,
                s.sequence,
            ),
        )

    def _get_purchase_route(self):
        self.ensure_one()
        if self.order_id and self.order_id.purchase_route_id:
            return self.order_id.purchase_route_id
        return self.route_ids.filtered(
            lambda r: r.rule_ids.filtered(lambda rr: rr.action == "buy")
        )[:1]

    def _get_supply_route(self):
        self.ensure_one()
        if self.route_id and self.route_id.rule_ids.filtered(
            lambda r: r.action in ("pull", "pull_push")
        ):
            return self.route_id
        return self.route_ids.filtered(
            lambda r: r.rule_ids.filtered(
                lambda rr: rr.action in ("pull", "pull_push")
            )
        )[:1]

    def _get_buy_rule(self, purchase_route):
        self.ensure_one()
        return purchase_route.rule_ids.filtered(
            lambda r: r.action == "buy"
            and (
                not r.warehouse_id
                or r.warehouse_id == self.warehouse_id
            )
        )[:1]

    def _launch_split_procurement(self, purchase_route):
        self.ensure_one()
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        free_qty = self._get_free_qty()
        qty_from_stock = min(self.product_uom_qty, max(0.0, free_qty))
        if float_compare(qty_from_stock, 0.0, precision_digits=precision) <= 0:
            qty_from_stock = 0.0
        qty_to_purchase = self.product_uom_qty - qty_from_stock
        if float_compare(qty_to_purchase, 0.0, precision_digits=precision) <= 0:
            qty_to_purchase = 0.0
        procurements = []
        if float_compare(qty_from_stock, 0.0, precision_digits=precision) > 0:
            supply_route = self._get_supply_route()
            if not supply_route:
                raise UserError(
                    self.env._(
                        "No internal supply route found for product "
                        "%(product)s to location %(location)s.",
                        product=self.product_id.display_name,
                        location=self.location_id.display_name,
                    )
                )
            values = self._prepare_procurement_values()
            values["route_ids"] = supply_route
            procurements.append(
                self.env["stock.rule"].Procurement(
                    self.product_id,
                    qty_from_stock,
                    self.product_uom_id,
                    self.location_id,
                    self.name,
                    self.name,
                    self.company_id,
                    values,
                )
            )
        if float_compare(qty_to_purchase, 0.0, precision_digits=precision) > 0:
            seller = self._get_seller(qty_to_purchase)
            if not seller:
                raise UserError(
                    self.env._(
                        "No supplier found for product %(product)s, but "
                        "%(qty)s %(uom)s still need to be purchased.",
                        product=self.product_id.display_name,
                        qty=qty_to_purchase,
                        uom=self.product_uom_id.name,
                    )
                )
            buy_rule = self._get_buy_rule(purchase_route)
            if not buy_rule:
                raise UserError(
                    self.env._(
                        "Route %(route)s has no buy rule for warehouse "
                        "%(warehouse)s.",
                        route=purchase_route.name,
                        warehouse=self.warehouse_id.display_name,
                    )
                )
            values = self._prepare_procurement_values()
            values["route_ids"] = purchase_route
            values["supplierinfo_id"] = seller
            procurements.append(
                self.env["stock.rule"].Procurement(
                    self.product_id,
                    qty_to_purchase,
                    self.product_uom_id,
                    buy_rule.location_dest_id,
                    self.name,
                    self.name,
                    self.company_id,
                    values,
                )
            )
        self.env["stock.rule"].run(procurements)
        self.write(
            {
                "qty_from_stock": qty_from_stock,
                "qty_purchased": qty_to_purchase,
            }
        )

    def _action_launch_procurement_rule(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        split_requests = self.env["stock.request"]
        standard_requests = self.env["stock.request"]
        errors = []
        for request in self:
            if request._skip_procurement():
                continue
            qty = 0.0
            for move in request.move_ids.filtered(lambda r: r.state != "cancel"):
                qty += move.product_qty
            if (
                float_compare(qty, request.product_qty, precision_digits=precision)
                >= 0
            ):
                continue
            if (
                request.order_id
                and request.order_id.split_purchase
                and request._get_purchase_route()
            ):
                split_requests |= request
            else:
                standard_requests |= request
        for request in split_requests:
            try:
                request._launch_split_procurement(
                    request._get_purchase_route()
                )
            except UserError as error:
                errors.append(str(error))
        if standard_requests:
            try:
                super(
                    StockRequest, standard_requests
                )._action_launch_procurement_rule()
            except UserError as error:
                errors.append(str(error))
        if errors:
            raise UserError("\n".join(errors))
        return True

    def action_cancel(self):
        for request in self:
            confirmed = (
                request.sudo()
                .purchase_ids.filtered(
                    lambda p: p.state in ("purchase", "done")
                )
            )
            if confirmed:
                raise UserError(
                    self.env._(
                        "You cannot cancel this request because the following "
                        "purchase orders are already confirmed: %(orders)s. "
                        "Cancel them first.",
                        orders=", ".join(confirmed.mapped("name")),
                    )
                )
        return super().action_cancel()

    @api.readonly
    def action_add_from_catalog(self):
        order = self.env["stock.request.order"].browse(
            self.env.context.get("order_id")
        )
        return order.action_add_from_catalog()

    def _get_product_catalog_lines_data(self, parent_record=False, **kwargs):
        return {
            "quantity": sum(self.mapped("product_uom_qty")),
            "price": 0.0,
            "uomDisplayName": self[:1].product_uom_id.display_name or "",
            "readOnly": bool(
                (parent_record and parent_record.state != "draft")
                or self.filtered(lambda r: r.state != "draft")
            ),
        }
