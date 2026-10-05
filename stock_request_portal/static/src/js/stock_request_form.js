/** @odoo-module */

const linesContainer = document.querySelector("#stock_request_lines");
const lineTemplate = document.querySelector("#o_sr_line_template");
const noLinesHint = document.querySelector("#o_sr_no_lines");
const noLinesError = document.querySelector("#o_sr_no_lines_error");
const lineCountBadge = document.querySelector("#o_sr_line_count");
const totalQtyLabel = document.querySelector("#o_sr_total_qty");
const categoryBar = document.querySelector("#o_sr_categories");
const productGrid = document.querySelector("#o_sr_product_grid");
const pager = document.querySelector("#o_sr_pager");
const searchInput = document.querySelector("#o_sr_search");
const noResults = document.querySelector("#o_sr_no_results");

if (linesContainer && lineTemplate) {
    // ------------------------------------------------------------------
    // Search + category filtering + pagination (client side, no page
    // reload, so the order lines are never lost)
    // ------------------------------------------------------------------
    const productCols = [...document.querySelectorAll(".o_sr_product_col")];
    const perPage = parseInt(productGrid?.dataset.perPage, 10) || 20;
    let currentCategory = "";
    let currentPage = 1;
    let searchTerms = [];

    // Case and accent insensitive matching.
    const normalize = (text) =>
        (text || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase();

    const searchIndex = new Map(
        productCols.map((col) => {
            const data =
                col.querySelector(".o_sr_product_card")?.dataset || {};
            return [
                col,
                normalize(`${data.productRef} ${data.productName}`),
            ];
        })
    );

    const renderCatalog = () => {
        const matching = productCols.filter(
            (col) =>
                (!currentCategory ||
                    col.querySelector(".o_sr_product_card")?.dataset
                        .categoryId === currentCategory) &&
                searchTerms.every((term) =>
                    searchIndex.get(col).includes(term)
                )
        );
        noResults?.classList.toggle(
            "d-none",
            !productCols.length || matching.length > 0
        );
        const pageCount = Math.max(1, Math.ceil(matching.length / perPage));
        currentPage = Math.min(Math.max(1, currentPage), pageCount);
        const visible = new Set(
            matching.slice((currentPage - 1) * perPage, currentPage * perPage)
        );
        productCols.forEach((col) =>
            col.classList.toggle("d-none", !visible.has(col))
        );
        if (pager) {
            pager.classList.toggle("d-none", pageCount <= 1);
            pager.classList.toggle("d-flex", pageCount > 1);
            pager.querySelector("#o_sr_page_current").textContent =
                currentPage;
            pager.querySelector("#o_sr_page_total").textContent = pageCount;
            pager.querySelector(".o_sr_page_prev").disabled =
                currentPage <= 1;
            pager.querySelector(".o_sr_page_next").disabled =
                currentPage >= pageCount;
        }
    };

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
            currentCategory = chip.dataset.categoryId;
            currentPage = 1;
            renderCatalog();
        });
    }

    if (searchInput) {
        searchInput.addEventListener("input", () => {
            searchTerms = normalize(searchInput.value)
                .split(/\s+/)
                .filter(Boolean);
            currentPage = 1;
            renderCatalog();
        });
        // Enter must not submit the order form.
        searchInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
            }
        });
    }

    if (pager) {
        pager.addEventListener("click", (event) => {
            const button = event.target.closest(".o_sr_page_btn");
            if (!button) {
                return;
            }
            currentPage += button.classList.contains("o_sr_page_next")
                ? 1
                : -1;
            renderCatalog();
            // Only bring the list back into view when its top was
            // scrolled out; never push the page down.
            if (productGrid && productGrid.getBoundingClientRect().top < 0) {
                productGrid.scrollIntoView({ block: "start" });
            }
        });
    }

    renderCatalog();

    // ------------------------------------------------------------------
    // Order lines management
    // ------------------------------------------------------------------
    // Quantities are positive integers (min 1).
    const toQty = (value) => {
        const qty = parseInt(value, 10);
        return Number.isFinite(qty) && qty > 0 ? qty : 1;
    };

    const updateSummary = () => {
        const lines = [...linesContainer.querySelectorAll(".o_sr_line")];
        if (lineCountBadge) {
            lineCountBadge.textContent = lines.length;
        }
        if (totalQtyLabel) {
            totalQtyLabel.textContent = lines.reduce(
                (total, line) =>
                    total + toQty(line.querySelector(".o_sr_qty")?.value),
                0
            );
        }
        if (noLinesHint) {
            noLinesHint.classList.toggle("d-none", lines.length > 0);
        }
        if (noLinesError && lines.length) {
            noLinesError.classList.add("d-none");
        }
    };

    const cardFor = (productId) =>
        document.querySelector(
            `.o_sr_product_card[data-product-id="${productId}"]`
        );

    const findRow = (productId) => {
        return linesContainer
            .querySelector(`.o_sr_product[value="${productId}"]`)
            ?.closest(".o_sr_line");
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
            updateSummary();
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
        updateSummary();
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
            updateSummary();
            return;
        }
        const row = lineTemplate.content.firstElementChild.cloneNode(true);
        row.querySelector(".o_sr_line_ref").textContent =
            card.dataset.productRef || "";
        row.querySelector(".o_sr_line_name").textContent =
            card.dataset.productName || "";
        row.querySelector(".o_sr_product").value = productId;
        row.querySelector(".o_sr_qty").value = qty;
        linesContainer.appendChild(row);
        setCardAdded(productId, true);
        updateSummary();
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
            syncCardFromRow(lineInput.closest(".o_sr_line"));
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
            syncCardFromRow(input.closest(".o_sr_line"));
        }
    });

    linesContainer.addEventListener("click", (event) => {
        const button = event.target.closest(".o_sr_remove");
        if (button) {
            const row = button.closest(".o_sr_line");
            const input = row.querySelector(".o_sr_product");
            if (input) {
                setCardAdded(input.value, false);
            }
            row.remove();
            updateSummary();
        }
    });

    const form = document.querySelector("#stock_request_order_form");
    if (form) {
        form.addEventListener("submit", (event) => {
            if (!linesContainer.querySelector(".o_sr_line")) {
                event.preventDefault();
                noLinesError?.classList.remove("d-none");
            }
        });
    }
}
