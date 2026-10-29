from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockRequest(models.Model):
    _inherit = "stock.request"

    free_qty = fields.Float(
        string="Free To Use",
        compute="_compute_free_qty",
        digits="Product Unit of Measure",
        help="Free quantity in the location holding the stock set aside for "
        "the destination, if any, plus the free quantity in the warehouse "
        "stock location (stock set aside for other destinations excluded).",
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

    @api.depends("product_id", "warehouse_id", "product_uom_id", "location_id")
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
        "location_id",
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

    def _get_source_location(self):
        """Location holding the stock set aside for the destination of this
        request, if any (see stock.location)."""
        self.ensure_one()
        if not self.location_id:
            return self.env["stock.location"]
        return self.location_id._get_stock_request_source_location()

    def _to_request_uom(self, qty):
        self.ensure_one()
        return self.product_id.uom_id._compute_quantity(
            qty, self.product_uom_id, rounding_method="HALF-UP"
        )

    def _get_location_uncommitted_qty(self, location):
        """Quantity of the product in the location (and its children) that
        no pending transfer is going to take: neither reserved nor demanded
        by a move waiting for it. Incoming quantities are not counted."""
        self.ensure_one()
        product = self.product_id.with_context(location=location.id)
        qty = min(product.free_qty, product.qty_available - product.outgoing_qty)
        return self._to_request_uom(qty)

    def _get_warehouse_free_qty(self):
        """Quantity of the warehouse stock location not committed to any
        pending transfer (e.g. the delivery of a sale to a set aside
        location), without the stock set aside for a destination that is
        kept inside it."""
        self.ensure_one()
        stock_location = self.warehouse_id.lot_stock_id
        qty = self._get_location_uncommitted_qty(stock_location)
        set_aside = self.env[
            "stock.location"
        ]._get_stock_request_set_aside_locations()
        for location in set_aside.filtered(
            lambda loc: loc != stock_location
            and (loc.parent_path or "").startswith(stock_location.parent_path)
        ):
            qty -= self._get_location_uncommitted_qty(location)
        return max(0.0, qty)

    def _get_set_aside_unbacked_moves(self, source_location):
        """Pending moves bringing the product to the set aside location from
        elsewhere in the warehouse that cannot be fully reserved (e.g. the
        delivery of a sale to the pre-obra while there is no stock). Moves
        chained to another pending move (e.g. a receipt) are on their way."""
        self.ensure_one()
        return self.env["stock.move"].search(
            [
                ("product_id", "=", self.product_id.id),
                ("location_dest_id", "child_of", source_location.id),
                ("location_id.usage", "=", "internal"),
                ("state", "in", ("confirmed", "partially_available")),
            ]
        ).filtered(
            lambda m: not (m.location_id.parent_path or "").startswith(
                source_location.parent_path
            )
            and not m.move_orig_ids.filtered(
                lambda o: o.state not in ("done", "cancel")
            )
        )

    def _get_set_aside_unbacked_qty(self, source_location):
        """Quantity on its way to the set aside location without stock to
        send it."""
        self.ensure_one()
        qty = 0.0
        for move in self._get_set_aside_unbacked_moves(source_location):
            reserved = move.product_uom._compute_quantity(
                move.quantity, move.product_id.uom_id, rounding_method="HALF-UP"
            )
            qty += max(0.0, move.product_qty - reserved)
        return qty

    def _get_set_aside_split(self):
        """Quantity set aside for the destination not promised to another
        request yet, split into what is in the set aside location or on its
        way with stock to send it, and what is on its way without stock (it
        has to be purchased for the pending transfer to bring it). What
        pending transfers are going to take from the location is deducted
        from the first part, then from the second."""
        self.ensure_one()
        source_location = self._get_source_location()
        if not source_location:
            return 0.0, 0.0
        product = self.product_id.with_context(location=source_location.id)
        unbacked = self._get_set_aside_unbacked_qty(source_location)
        covered = product.virtual_available - unbacked
        if covered < 0.0:
            unbacked += covered
            covered = 0.0
        return (
            self._to_request_uom(covered),
            self._to_request_uom(max(0.0, unbacked)),
        )

    def _get_set_aside_free_qty(self):
        """Quantity set aside for the destination that is in the set aside
        location or on its way with stock to send it (e.g. a sale whose
        delivery is reserved but not validated yet), minus what pending
        transfers are going to take from it."""
        self.ensure_one()
        return self._get_set_aside_split()[0]

    def _get_free_qty(self):
        self.ensure_one()
        if not self.product_id or not self.warehouse_id:
            return 0.0
        return self._get_set_aside_free_qty() + self._get_warehouse_free_qty()

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

    def _prepare_procurement_values(self, reference_ids=False):
        values = super()._prepare_procurement_values(reference_ids=reference_ids)
        source_location = self._get_source_location()
        if source_location:
            values["stock_request_source_location_id"] = source_location.id
        return values

    def _get_supply_procurement(self, qty, from_set_aside=True):
        """Internal transfer to the destination. It leaves the stock set
        aside for the destination unless from_set_aside is False, in which
        case it leaves the source location of the supply route (the
        warehouse stock)."""
        self.ensure_one()
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
        if not from_set_aside:
            values.pop("stock_request_source_location_id", None)
        return self.env["stock.rule"].Procurement(
            self.product_id,
            qty,
            self.product_uom_id,
            self.location_id,
            self.name,
            self.name,
            self.company_id,
            values,
        )

    def _get_purchase_procurement(self, qty, purchase_route, to_set_aside=True):
        """Purchase of the missing quantity. It is received in the set aside
        location unless to_set_aside is False, in which case it is received
        where the buy rule puts it (the warehouse stock)."""
        self.ensure_one()
        seller = self._get_seller(qty)
        if not seller:
            raise UserError(
                self.env._(
                    "No supplier found for product %(product)s, but "
                    "%(qty)s %(uom)s still need to be purchased.",
                    product=self.product_id.display_name,
                    qty=qty,
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
        if not to_set_aside:
            values.pop("stock_request_source_location_id", None)
        return self.env["stock.rule"].Procurement(
            self.product_id,
            qty,
            self.product_uom_id,
            buy_rule.location_dest_id,
            self.name,
            self.name,
            self.company_id,
            values,
        )

    def _get_supply_split(self):
        """Split the requested quantity into what the stock set aside for
        the destination covers, what is set aside without stock to send it
        (to be purchased for the pending transfer to the set aside location),
        what the warehouse stock covers and what is missing, in that order of
        priority."""
        self.ensure_one()
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )

        def take(qty, available):
            qty = min(qty, max(0.0, available))
            if float_compare(qty, 0.0, precision_digits=precision) <= 0:
                return 0.0
            return qty

        set_aside_covered, set_aside_unbacked = self._get_set_aside_split()
        remaining = self.product_uom_qty
        qty_set_aside = take(remaining, set_aside_covered)
        remaining -= qty_set_aside
        qty_unbacked = take(remaining, set_aside_unbacked)
        remaining -= qty_unbacked
        qty_warehouse = take(remaining, self._get_warehouse_free_qty())
        remaining -= qty_warehouse
        if float_compare(remaining, 0.0, precision_digits=precision) <= 0:
            remaining = 0.0
        return qty_set_aside, qty_unbacked, qty_warehouse, remaining

    def _get_qty_from_stock_and_to_purchase(self):
        """Split the requested quantity into what the free stock covers and
        what is missing."""
        self.ensure_one()
        qty_set_aside, qty_unbacked, qty_warehouse, qty_to_purchase = (
            self._get_supply_split()
        )
        return qty_set_aside + qty_warehouse, qty_unbacked + qty_to_purchase

    def _launch_reserved_procurement(self):
        """Supply the request from the stock set aside for its destination
        and, when it is not enough, from the free warehouse stock. What is
        set aside without stock to send it is purchased and received in the
        warehouse stock, where the pending transfer to the set aside location
        takes it. The quantity nothing covers is purchased and received in
        the set aside location. Both leave from there with the stock set
        aside."""
        self.ensure_one()
        source_location = self._get_source_location()
        # Stock that arrived since the transfer to the set aside location was
        # confirmed is not purchased again.
        self._get_set_aside_unbacked_moves(source_location)._action_assign()
        qty_set_aside, qty_unbacked, qty_warehouse, qty_to_purchase = (
            self._get_supply_split()
        )
        procurements = []
        if qty_set_aside or qty_unbacked or qty_to_purchase:
            procurements.append(
                self._get_supply_procurement(
                    qty_set_aside + qty_unbacked + qty_to_purchase
                )
            )
        if qty_warehouse:
            procurements.append(
                self._get_supply_procurement(qty_warehouse, from_set_aside=False)
            )
        if qty_unbacked or qty_to_purchase:
            purchase_route = self._get_purchase_route()
            if not purchase_route:
                raise UserError(
                    self.env._(
                        "No purchase route found to buy the %(qty)s %(uom)s "
                        "of %(product)s missing in %(location)s.",
                        qty=qty_unbacked + qty_to_purchase,
                        uom=self.product_uom_id.name,
                        product=self.product_id.display_name,
                        location=source_location.display_name,
                    )
                )
            if qty_unbacked:
                procurements.append(
                    self._get_purchase_procurement(
                        qty_unbacked, purchase_route, to_set_aside=False
                    )
                )
            if qty_to_purchase:
                procurements.append(
                    self._get_purchase_procurement(qty_to_purchase, purchase_route)
                )
        self.env["stock.rule"].run(procurements)
        self.write(
            {
                "qty_from_stock": qty_set_aside + qty_warehouse,
                "qty_purchased": qty_unbacked + qty_to_purchase,
            }
        )

    def _launch_split_procurement(self, purchase_route):
        self.ensure_one()
        qty_from_stock, qty_to_purchase = (
            self._get_qty_from_stock_and_to_purchase()
        )
        procurements = []
        if qty_from_stock:
            procurements.append(self._get_supply_procurement(qty_from_stock))
        if qty_to_purchase:
            procurements.append(
                self._get_purchase_procurement(qty_to_purchase, purchase_route)
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
        reserved_requests = self.env["stock.request"]
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
            if request._get_source_location():
                reserved_requests |= request
            elif (
                request.order_id
                and request.order_id.split_purchase
                and request._get_purchase_route()
            ):
                split_requests |= request
            else:
                standard_requests |= request
        for request in reserved_requests:
            try:
                request._launch_reserved_procurement()
            except UserError as error:
                errors.append(str(error))
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
