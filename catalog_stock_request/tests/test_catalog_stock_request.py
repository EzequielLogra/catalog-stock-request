from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError

from odoo.addons.stock_request_purchase.tests.test_stock_request_purchase import (
    TestStockRequestPurchase,
)


class TestSplitPurchase(TestStockRequestPurchase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ward_location = cls.env["stock.location"].create(
            {
                "name": "Ward A",
                "location_id": cls.warehouse.view_location_id.id,
                "usage": "internal",
                "company_id": cls.main_company.id,
            }
        )
        cls.route_supply = cls.env["stock.route"].create(
            {
                "name": "Supply Ward A",
                "product_categ_selectable": False,
                "product_selectable": False,
                "warehouse_selectable": True,
                "warehouse_ids": [(4, cls.warehouse.id)],
                "company_id": cls.main_company.id,
            }
        )
        cls.env["stock.rule"].create(
            {
                "name": "WH Stock to Ward A",
                "route_id": cls.route_supply.id,
                "location_src_id": cls.warehouse.lot_stock_id.id,
                "location_dest_id": cls.ward_location.id,
                "action": "pull",
                "picking_type_id": cls.warehouse.int_type_id.id,
                "procure_method": "make_to_stock",
                "location_dest_from_rule": True,
                "warehouse_id": cls.warehouse.id,
                "company_id": cls.main_company.id,
            }
        )
        cls.supplier_ranked = cls.env["res.partner"].create(
            {"name": "Ranked Supplier", "supplier_rank": 1}
        )
        cls.product.write(
            {
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.supplier_ranked.id,
                            "min_qty": 1,
                            "price": 10,
                        },
                    )
                ],
            }
        )
        cls.product_no_supplier = cls.env["product.product"].create(
            {
                "name": "No Supplier Product",
                "default_code": "NSP",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "company_id": cls.main_company.id,
                "type": "consu",
                "is_storable": True,
            }
        )

    @classmethod
    def _create_order(cls, line_vals, **order_vals):
        expected_date = fields.Datetime.now()
        vals = {
            "company_id": cls.main_company.id,
            "warehouse_id": cls.warehouse.id,
            "location_id": cls.ward_location.id,
            "expected_date": expected_date,
            "split_purchase": True,
            "stock_request_ids": [
                (
                    0,
                    0,
                    dict(
                        {
                            "product_uom_id": cls.product.uom_id.id,
                            "product_uom_qty": 20.0,
                            "company_id": cls.main_company.id,
                            "warehouse_id": cls.warehouse.id,
                            "location_id": cls.ward_location.id,
                            "expected_date": expected_date,
                            "route_id": cls.route_supply.id,
                        },
                        **line_vals,
                    ),
                )
            ],
        }
        vals.update(order_vals)
        return cls.env["stock.request.order"].create(vals)

    def _set_stock(self, product, qty, location=None):
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": (location or self.warehouse.lot_stock_id).id,
                "inventory_quantity": qty,
            }
        )
        quant.action_apply_inventory()

    def test_split_partial(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(order.state, "open")
        self.assertEqual(request.qty_from_stock, 12.0)
        self.assertEqual(request.qty_purchased, 8.0)
        self.assertEqual(request.qty_to_purchase, 8.0)
        pickings = order.picking_ids
        self.assertEqual(len(pickings), 1)
        move = pickings.move_ids
        self.assertEqual(move.product_uom_qty, 12.0)
        self.assertEqual(move.location_dest_id, self.ward_location)
        self.assertEqual(request.qty_reserved, 12.0)
        purchases = request.sudo().purchase_ids
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases.order_line.product_qty, 8.0)
        self.assertEqual(
            purchases.order_line.stock_request_ids, request
        )

    def test_split_all_stock(self):
        self._set_stock(self.product, 20.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 20.0)
        self.assertEqual(request.qty_purchased, 0.0)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 20.0)
        self.assertEqual(len(request.sudo().purchase_ids), 0)

    def test_split_no_stock_ranked_supplier(self):
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 0.0)
        self.assertEqual(request.qty_purchased, 20.0)
        self.assertEqual(len(order.picking_ids), 0)
        purchases = request.sudo().purchase_ids
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases.partner_id, self.supplier_ranked)
        self.assertEqual(purchases.order_line.product_qty, 20.0)

    def test_cancel_with_draft_purchase(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(purchase.state, "draft")
        order.action_cancel()
        self.assertEqual(order.state, "cancel")
        self.assertEqual(purchase.state, "cancel")

    def test_cancel_with_confirmed_purchase(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        purchase.button_confirm()
        with self.assertRaises(UserError):
            order.action_cancel()

    def test_missing_supplier(self):
        self._set_stock(self.product_no_supplier, 5.0)
        order = self._create_order(
            {
                "product_id": self.product_no_supplier.id,
                "product_uom_qty": 10.0,
            }
        )
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_purchase_obra_internal_requester(self):
        order = self._create_order({"product_id": self.product.id})
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(len(purchase), 1)
        self.assertIn(order.name, purchase.origin)
        self.assertIn(self.ward_location.complete_name, purchase.origin)
        self.assertNotIn("(", purchase.origin)
        self.assertEqual(purchase.obra_location_id, self.ward_location)

    def test_purchase_obra_portal_client(self):
        client = self.env["res.partner"].create(
            {"name": "Hospital Sur SA", "is_company": True}
        )
        portal_user = self.env["res.users"].create(
            {
                "name": "Portal Obra User",
                "login": "portal_obra_user",
                "email": "obra@example.com",
                "partner_id": client.id,
                "group_ids": [
                    Command.set([self.env.ref("base.group_portal").id])
                ],
            }
        )
        order = self._create_order(
            {"product_id": self.product.id, "requested_by": portal_user.id},
            requested_by=portal_user.id,
        )
        order.action_confirm()
        purchase = order.stock_request_ids.sudo().purchase_ids
        self.assertEqual(len(purchase), 1)
        self.assertIn(order.name, purchase.origin)
        self.assertIn(self.ward_location.complete_name, purchase.origin)
        self.assertIn(f"({client.name})", purchase.origin)
        self.assertEqual(purchase.obra_location_id, self.ward_location)

    def test_no_split_standard_behavior(self):
        self._set_stock(self.product, 12.0)
        order = self._create_order(
            {"product_id": self.product.id}, split_purchase=False
        )
        order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 0.0)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 20.0)
        self.assertEqual(len(request.sudo().purchase_ids), 0)

    def _create_set_aside_location(self):
        return self.env["stock.location"].create(
            {
                "name": "Ward A set aside",
                "location_id": self.warehouse.view_location_id.id,
                "usage": "internal",
                "company_id": self.main_company.id,
            }
        )

    def _patch_source_location(self, source_location):
        return patch.object(
            type(self.env["stock.location"]),
            "_get_stock_request_source_location",
            lambda location: source_location,
        )

    def test_set_aside_stock_supplies_the_request(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 50.0)
        self._set_stock(self.product, 8.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 8.0}
            )
            request = order.stock_request_ids
            # Set aside stock plus warehouse stock
            self.assertEqual(request.free_qty, 58.0)
            self.assertEqual(request.qty_to_purchase, 0.0)
            order.action_confirm()
        self.assertEqual(request.qty_from_stock, 8.0)
        self.assertEqual(request.qty_purchased, 0.0)
        move = order.picking_ids.move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.product_uom_qty, 8.0)
        self.assertEqual(move.location_id, source_location)
        self.assertEqual(move.location_dest_id, self.ward_location)
        self.assertEqual(len(request.sudo().purchase_ids), 0)

    def _receive(self, purchase):
        purchase.button_confirm()
        receipt = purchase.picking_ids
        for move in receipt.move_ids:
            move.quantity = move.product_uom_qty
        receipt.move_ids.picked = True
        receipt.button_validate()
        return receipt

    def test_set_aside_stock_missing_quantity_is_purchased(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 30.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 40.0}
            )
            request = order.stock_request_ids
            self.assertEqual(request.qty_to_purchase, 10.0)
            order.action_confirm()
        self.assertEqual(request.qty_from_stock, 30.0)
        self.assertEqual(request.qty_purchased, 10.0)
        # The whole request leaves the set aside location in one transfer.
        move = order.picking_ids.move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.product_uom_qty, 40.0)
        self.assertEqual(move.location_id, source_location)
        self.assertEqual(move.location_dest_id, self.ward_location)
        self.assertEqual(move.quantity, 30.0)
        purchase = request.sudo().purchase_ids
        self.assertEqual(len(purchase), 1)
        self.assertEqual(purchase.order_line.product_qty, 10.0)
        self.assertEqual(
            purchase.order_line.stock_request_source_location_id,
            source_location,
        )
        self.assertEqual(purchase.obra_location_id, self.ward_location)

    def test_set_aside_purchase_is_received_in_set_aside_location(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 30.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 40.0}
            )
            order.action_confirm()
            request = order.stock_request_ids
            receipt = self._receive(request.sudo().purchase_ids)
        self.assertEqual(receipt.move_ids.location_dest_id, source_location)
        self.assertEqual(receipt.state, "done")
        # The received products complete the reservation of the transfer.
        picking = order.picking_ids
        self.assertEqual(picking.move_ids.quantity, 40.0)
        self.assertEqual(picking.state, "assigned")
        # The receipt does not count as progress of the request.
        self.assertEqual(request.qty_done, 0.0)
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(request.qty_done, 40.0)
        self.assertEqual(request.state, "done")

    def test_set_aside_without_stock_purchases_everything(self):
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 5.0}
            )
            order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 0.0)
        self.assertEqual(request.qty_purchased, 5.0)
        move = order.picking_ids.move_ids
        self.assertEqual(move.location_id, source_location)
        self.assertEqual(move.quantity, 0.0)
        self.assertEqual(request.sudo().purchase_ids.order_line.product_qty, 5.0)

    def test_set_aside_without_stock_uses_warehouse_stock(self):
        """The warehouse stock is used before purchasing."""
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 50.0)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 5.0}
            )
            request = order.stock_request_ids
            self.assertEqual(request.free_qty, 50.0)
            self.assertEqual(request.qty_to_purchase, 0.0)
            order.action_confirm()
        self.assertEqual(request.qty_from_stock, 5.0)
        self.assertEqual(request.qty_purchased, 0.0)
        move = order.picking_ids.move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.location_id, self.warehouse.lot_stock_id)
        self.assertEqual(move.location_dest_id, self.ward_location)
        self.assertEqual(move.quantity, 5.0)
        self.assertFalse(request.sudo().purchase_ids)

    def test_set_aside_stock_then_warehouse_stock(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 50.0)
        self._set_stock(self.product, 30.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 40.0}
            )
            request = order.stock_request_ids
            self.assertEqual(request.qty_to_purchase, 0.0)
            order.action_confirm()
        self.assertEqual(request.qty_from_stock, 40.0)
        self.assertEqual(request.qty_purchased, 0.0)
        self.assertFalse(request.sudo().purchase_ids)
        moves = order.picking_ids.move_ids
        self.assertEqual(len(order.picking_ids), 2)
        set_aside_move = moves.filtered(
            lambda m: m.location_id == source_location
        )
        warehouse_move = moves - set_aside_move
        self.assertEqual(set_aside_move.product_uom_qty, 30.0)
        self.assertEqual(set_aside_move.quantity, 30.0)
        self.assertEqual(warehouse_move.location_id, self.warehouse.lot_stock_id)
        self.assertEqual(warehouse_move.product_uom_qty, 10.0)
        self.assertEqual(warehouse_move.quantity, 10.0)
        self.assertEqual(moves.location_dest_id, self.ward_location)

    def test_set_aside_and_warehouse_stock_short_purchases_the_rest(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 3.0)
        self._set_stock(self.product, 2.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 10.0}
            )
            order.action_confirm()
            request = order.stock_request_ids
            purchase = request.sudo().purchase_ids
            self.assertEqual(request.qty_from_stock, 5.0)
            self.assertEqual(request.qty_purchased, 5.0)
            self.assertEqual(purchase.order_line.product_qty, 5.0)
            moves = order.picking_ids.move_ids
            set_aside_move = moves.filtered(
                lambda m: m.location_id == source_location
            )
            warehouse_move = moves - set_aside_move
            # The purchase is received in the set aside location and leaves
            # with the stock set aside.
            self.assertEqual(set_aside_move.product_uom_qty, 7.0)
            self.assertEqual(set_aside_move.quantity, 2.0)
            self.assertEqual(warehouse_move.product_uom_qty, 3.0)
            self.assertEqual(warehouse_move.quantity, 3.0)
            self._receive(purchase)
        self.assertEqual(set_aside_move.quantity, 7.0)

    def _send_to_set_aside(self, source_location, qty):
        """Pending transfer of warehouse stock to the set aside location, as
        the delivery of a sale to the obra before it is validated."""
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": source_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": qty,
                            "product_uom": self.product.uom_id.id,
                            "location_id": self.warehouse.lot_stock_id.id,
                            "location_dest_id": source_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def test_set_aside_stock_on_its_way_is_not_reserved_twice(self):
        """Stock on its way to the set aside location covers the request: it
        is neither taken again from the warehouse nor purchased."""
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 10.0)
        with self._patch_source_location(source_location):
            delivery = self._send_to_set_aside(source_location, 5.0)
            self.assertEqual(delivery.state, "assigned")
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 5.0}
            )
            order.action_confirm()
            request = order.stock_request_ids
            self.assertEqual(request.qty_from_stock, 5.0)
            self.assertEqual(request.qty_purchased, 0.0)
            self.assertFalse(request.sudo().purchase_ids)
            move = order.picking_ids.move_ids
            self.assertEqual(len(move), 1)
            self.assertEqual(move.location_id, source_location)
            self.assertEqual(move.quantity, 0.0)
            # Only the delivery reserves warehouse stock.
            self.assertEqual(self.product.with_context(
                location=self.warehouse.lot_stock_id.id).free_qty, 5.0)
            delivery.move_ids.picked = True
            delivery.button_validate()
            order.picking_ids.action_assign()
        self.assertEqual(move.quantity, 5.0)

    def test_set_aside_stock_on_its_way_then_free_warehouse_stock(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 10.0)
        with self._patch_source_location(source_location):
            self._send_to_set_aside(source_location, 5.0)
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 12.0}
            )
            order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 10.0)
        self.assertEqual(request.qty_purchased, 2.0)
        moves = order.picking_ids.move_ids
        set_aside_move = moves.filtered(
            lambda m: m.location_id == source_location
        )
        warehouse_move = moves - set_aside_move
        self.assertEqual(set_aside_move.product_uom_qty, 7.0)
        self.assertEqual(warehouse_move.product_uom_qty, 5.0)
        self.assertEqual(warehouse_move.quantity, 5.0)

    def test_set_aside_stock_promised_to_another_request(self):
        """Stock set aside already promised to a previous request is not
        counted again."""
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 4.0, location=source_location)
        with self._patch_source_location(source_location):
            first = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 4.0}
            )
            first.action_confirm()
            second = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 3.0}
            )
            self.assertEqual(second.stock_request_ids.free_qty, 0.0)
            second.action_confirm()
        self.assertEqual(second.stock_request_ids.qty_purchased, 3.0)

    def test_set_aside_without_stock_to_send_is_purchased_for_it(self):
        """What is on its way to the set aside location without stock to
        send it (a sale to the pre-obra while there is no stock) is purchased
        when a request asks for it, and received in the warehouse stock,
        where the pending transfer to the set aside location takes it."""
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            delivery = self._send_to_set_aside(source_location, 3.0)
            self.assertEqual(delivery.state, "confirmed")
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 3.0}
            )
            request = order.stock_request_ids
            self.assertEqual(request.free_qty, 0.0)
            self.assertEqual(request.qty_to_purchase, 3.0)
            order.action_confirm()
            self.assertEqual(request.qty_from_stock, 0.0)
            self.assertEqual(request.qty_purchased, 3.0)
            move = order.picking_ids.move_ids
            self.assertEqual(len(move), 1)
            self.assertEqual(move.location_id, source_location)
            self.assertEqual(move.product_uom_qty, 3.0)
            purchase = request.sudo().purchase_ids
            self.assertEqual(purchase.order_line.product_qty, 3.0)
            self.assertFalse(
                purchase.order_line.stock_request_source_location_id
            )
            receipt = self._receive(purchase)
            self.assertEqual(
                receipt.move_ids.location_dest_id, self.warehouse.lot_stock_id
            )
            self.assertEqual(delivery.state, "assigned")
            delivery.move_ids.picked = True
            delivery.button_validate()
            order.picking_ids.action_assign()
        self.assertEqual(move.quantity, 3.0)

    def test_set_aside_partly_without_stock_to_send(self):
        """Only the part of the pending transfer to the set aside location
        that has no stock to send it is purchased for it."""
        source_location = self._create_set_aside_location()
        self._set_stock(self.product, 2.0)
        with self._patch_source_location(source_location):
            delivery = self._send_to_set_aside(source_location, 5.0)
            self.assertEqual(delivery.move_ids.quantity, 2.0)
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 5.0}
            )
            order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_from_stock, 2.0)
        self.assertEqual(request.qty_purchased, 3.0)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 5.0)
        line = request.sudo().purchase_ids.order_line
        self.assertEqual(line.product_qty, 3.0)
        self.assertFalse(line.stock_request_source_location_id)

    def test_set_aside_without_stock_to_send_and_missing_quantity(self):
        """In the same request, what is set aside without stock is received
        in the warehouse stock and the rest in the set aside location: the
        two purchases are not merged in one line."""
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            self._send_to_set_aside(source_location, 3.0)
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 4.0}
            )
            order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(request.qty_purchased, 4.0)
        lines = request.sudo().purchase_ids.order_line
        self.assertEqual(len(lines), 2)
        to_stock = lines.filtered(
            lambda line: not line.stock_request_source_location_id
        )
        self.assertEqual(to_stock.product_qty, 3.0)
        self.assertEqual((lines - to_stock).product_qty, 1.0)
        self.assertEqual(
            (lines - to_stock).stock_request_source_location_id, source_location
        )

    def test_set_aside_without_stock_to_send_is_purchased_once(self):
        """A second request does not purchase again what a previous request
        already purchased for the pending transfer: it purchases its own
        missing quantity, received in the set aside location."""
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            self._send_to_set_aside(source_location, 3.0)
            first = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 3.0}
            )
            first.action_confirm()
            second = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 2.0}
            )
            second.action_confirm()
        first_line = first.stock_request_ids.sudo().purchase_ids.order_line
        second_request = second.stock_request_ids
        self.assertEqual(second_request.qty_purchased, 2.0)
        lines = second_request.sudo().purchase_ids.order_line.filtered(
            lambda line: line.stock_request_source_location_id
        )
        self.assertEqual(lines.product_qty, 2.0)
        self.assertEqual(lines.stock_request_source_location_id, source_location)
        self.assertEqual(
            sum(
                first_line.filtered(
                    lambda line: not line.stock_request_source_location_id
                ).mapped("product_qty")
            ),
            3.0,
        )

    def test_set_aside_stock_arrived_after_the_transfer_is_not_purchased(self):
        """Stock that reached the warehouse after the transfer to the set
        aside location was confirmed is reserved for it, not purchased."""
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            delivery = self._send_to_set_aside(source_location, 3.0)
            self._set_stock(self.product, 3.0)
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 3.0}
            )
            order.action_confirm()
        request = order.stock_request_ids
        self.assertEqual(delivery.state, "assigned")
        self.assertEqual(request.qty_from_stock, 3.0)
        self.assertEqual(request.qty_purchased, 0.0)
        self.assertFalse(request.sudo().purchase_ids)

    def test_warehouse_stock_excludes_stock_set_aside_inside_it(self):
        """Stock set aside for a destination, kept in a child location of
        the warehouse stock, is not free for other destinations."""
        set_aside = self.env["stock.location"].create(
            {
                "name": "Other ward set aside",
                "location_id": self.warehouse.lot_stock_id.id,
                "usage": "internal",
                "company_id": self.main_company.id,
            }
        )
        self._set_stock(self.product, 4.0)
        self._set_stock(self.product, 20.0, location=set_aside)
        with patch.object(
            type(self.env["stock.location"]),
            "_get_stock_request_set_aside_locations",
            lambda model: set_aside,
        ):
            order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 10.0}
            )
            request = order.stock_request_ids
            self.assertEqual(request.free_qty, 4.0)
            self.assertEqual(request.qty_to_purchase, 6.0)

    def test_set_aside_purchase_not_merged_with_other_destinations(self):
        source_location = self._create_set_aside_location()
        with self._patch_source_location(source_location):
            set_aside_order = self._create_order(
                {"product_id": self.product.id, "product_uom_qty": 5.0}
            )
            set_aside_order.action_confirm()
        order = self._create_order(
            {"product_id": self.product.id, "product_uom_qty": 7.0}
        )
        order.action_confirm()
        set_aside_request = set_aside_order.stock_request_ids
        request = order.stock_request_ids
        purchase = request.sudo().purchase_ids
        self.assertEqual(set_aside_request.sudo().purchase_ids, purchase)
        self.assertEqual(len(purchase.order_line), 2)
        set_aside_line = purchase.order_line.filtered(
            lambda line: set_aside_request in line.stock_request_ids
        )
        line = purchase.order_line - set_aside_line
        self.assertEqual(set_aside_line.product_qty, 5.0)
        self.assertEqual(line.product_qty, 7.0)
        self.assertFalse(line.stock_request_source_location_id)

    def test_set_aside_missing_quantity_without_supplier_fails(self):
        source_location = self._create_set_aside_location()
        self._set_stock(self.product_no_supplier, 3.0, location=source_location)
        with self._patch_source_location(source_location):
            order = self._create_order(
                {
                    "product_id": self.product_no_supplier.id,
                    "product_uom_qty": 5.0,
                }
            )
            with self.assertRaises(UserError):
                order.action_confirm()
        self.assertEqual(len(order.picking_ids), 0)
