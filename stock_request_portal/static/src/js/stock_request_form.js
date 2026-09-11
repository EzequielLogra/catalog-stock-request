/** @odoo-module */

const linesContainer = document.querySelector("#stock_request_lines");
const lineTemplate = document.querySelector("#o_sr_line_template");
const noLinesRow = document.querySelector("#o_sr_no_lines");
const lineCountBadge = document.querySelector("#o_sr_line_count");
const categoryBar = document.querySelector("#o_sr_categories");

if (linesContainer && lineTemplate) {
    // ------------------------------------------------------------------
    // Category filtering (client side, no page reload)
    // ------------------------------------------------------------------
    if (categoryBar) {
        categoryBar.addEventListener("click", (event) => {
            const chip = event.target.closest(".o_sr_category_chip");
            if (!chip) {
                return;
            }
            categoryBar
                .querySelectorAll(".o_sr_category_chip")
                .forEach((element) => element.classList.remove("active"));
            chip.classList.add("active");
            const categoryId = chip.dataset.categoryId;
            document
                .querySelectorAll(".o_sr_product_card")
                .forEach((card) => {
                    const match =
                        !categoryId ||
                        card.dataset.categoryId === categoryId;
                    const col = card.closest(".o_sr_product_col") || card;
                    col.style.display = match ? "" : "none";
                });
        });
    }

    // ------------------------------------------------------------------
    // Order lines management
    // ------------------------------------------------------------------
    // Quantities are positive integers (min 1).
    const toQty = (value) => {
        const qty = parseInt(value, 10);
        return Number.isFinite(qty) && qty > 0 ? qty : 1;
    };

    const updateLineCount = () => {
        if (lineCountBadge) {
            lineCountBadge.textContent =
                linesContainer.querySelectorAll(".o_sr_line").length;
        }
    };

    const cardFor = (productId) =>
        document.querySelector(
            `.o_sr_product_card[data-product-id="${productId}"]`
        );

    const findRow = (productId) => {
        return linesContainer
            .querySelector(`.o_sr_product[value="${productId}"]`)
            ?.closest("tr");
    };

    const setCardQty = (card, qty) => {
        const input = card.querySelector(".o_sr_card_qty");
        if (input) {
            input.value = qty;
        }
    };

    const setRowQty = (row, qty) => {
        const input = row.querySelector(".o_sr_qty");
        if (input) {
            input.value = qty;
        }
    };

    const setCardAdded = (productId, added) => {
        const card = cardFor(productId);
        if (!card) {
            return;
        }
        card.classList.toggle("o_sr_added", added);
        if (!added) {
            setCardQty(card, 1);
        }
        const icon = card.querySelector(".o_sr_add_product i");
        if (icon) {
            icon.className = added
                ? "fa fa-check me-1"
                : "fa fa-plus me-1";
        }
    };

    // The card stepper is the source of truth: when the product already
    // has a line, editing the card quantity replaces the line quantity.
    const applyCardQty = (card) => {
        if (!card) {
            return;
        }
        const row = findRow(card.dataset.productId);
        if (row) {
            setRowQty(
                row,
                toQty(card.querySelector(".o_sr_card_qty")?.value)
            );
        }
    };

    const syncCardFromRow = (row) => {
        if (!row) {
            return;
        }
        const productId = row.querySelector(".o_sr_product")?.value;
        const card = productId && cardFor(productId);
        if (card) {
            setCardQty(card, toQty(row.querySelector(".o_sr_qty")?.value));
        }
    };

    const removeNoLinesHint = () => {
        if (noLinesRow && noLinesRow.isConnected) {
            noLinesRow.remove();
        }
    };

    const addProduct = (card) => {
        const productId = card.dataset.productId;
        if (!productId) {
            return;
        }
        const qty = toQty(card.querySelector(".o_sr_card_qty")?.value);
        const existingRow = findRow(productId);
        if (existingRow) {
            setRowQty(existingRow, qty);
            existingRow.querySelector(".o_sr_qty").focus();
            return;
        }
        removeNoLinesHint();
        const row = lineTemplate.content.firstElementChild.cloneNode(true);
        row.querySelector(".o_sr_line_name").textContent =
            card.dataset.productName || "";
        row.querySelector(".o_sr_product").value = productId;
        row.querySelector(".o_sr_qty").value = qty;
        linesContainer.appendChild(row);
        setCardAdded(productId, true);
        updateLineCount();
    };

    const stepCardQty = (card, delta) => {
        if (!card) {
            return;
        }
        const input = card.querySelector(".o_sr_card_qty");
        if (!input) {
            return;
        }
        input.value = Math.max(1, toQty(input.value) + delta);
        applyCardQty(card);
    };

    document.addEventListener("click", (event) => {
        const plus = event.target.closest(".o_sr_qty_plus");
        if (plus) {
            stepCardQty(plus.closest(".o_sr_product_card"), 1);
            return;
        }
        const minus = event.target.closest(".o_sr_qty_minus");
        if (minus) {
            stepCardQty(minus.closest(".o_sr_product_card"), -1);
            return;
        }
        const button = event.target.closest(".o_sr_add_product");
        if (button) {
            addProduct(button.closest(".o_sr_product_card"));
        }
    });

    // Live sync between the card steppers and their order lines.
    const syncQty = (event) => {
        const cardInput = event.target.closest(".o_sr_card_qty");
        if (cardInput) {
            applyCardQty(cardInput.closest(".o_sr_product_card"));
            return;
        }
        const lineInput = event.target.closest(".o_sr_qty");
        if (lineInput) {
            syncCardFromRow(lineInput.closest("tr"));
        }
    };
    document.addEventListener("input", syncQty);
    document.addEventListener("change", syncQty);

    // Normalize empty or sub-minimum values once the field is left.
    document.addEventListener("focusout", (event) => {
        const input = event.target.closest(".o_sr_card_qty, .o_sr_qty");
        if (!input) {
            return;
        }
        input.value = toQty(input.value);
        const card = input.closest(".o_sr_product_card");
        if (card) {
            applyCardQty(card);
        } else {
            syncCardFromRow(input.closest("tr"));
        }
    });

    linesContainer.addEventListener("click", (event) => {
        const button = event.target.closest(".o_sr_remove");
        if (button) {
            const row = button.closest("tr");
            const input = row.querySelector(".o_sr_product");
            if (input) {
                setCardAdded(input.value, false);
            }
            row.remove();
            updateLineCount();
        }
    });

    const form = document.querySelector("#stock_request_order_form");
    if (form) {
        form.addEventListener("submit", (event) => {
            if (!linesContainer.querySelector(".o_sr_line")) {
                event.preventDefault();
                removeNoLinesHint();
                linesContainer.insertAdjacentHTML(
                    "beforeend",
                    '<tr class="table-danger"><td colspan="3">Add at least one product line to submit a request.</td></tr>'
                );
            }
        });
    }
}
