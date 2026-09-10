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
                    card.closest(".o_sr_product_col").style.display = match
                        ? ""
                        : "none";
                });
        });
    }

    // ------------------------------------------------------------------
    // Order lines management
    // ------------------------------------------------------------------
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

    const setCardAdded = (productId, added) => {
        const card = cardFor(productId);
        if (!card) {
            return;
        }
        card.classList.toggle("o_sr_added", added);
        const icon = card.querySelector(".o_sr_add_product i");
        if (icon) {
            icon.className = added
                ? "fa fa-check me-1"
                : "fa fa-plus me-1";
        }
    };

    const findRow = (productId) => {
        return linesContainer
            .querySelector(`.o_sr_product[value="${productId}"]`)
            ?.closest("tr");
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
        const existingRow = findRow(productId);
        if (existingRow) {
            const qtyInput = existingRow.querySelector(".o_sr_qty");
            const current = parseFloat(qtyInput.value || "0") || 0;
            qtyInput.value = (current + 1).toFixed(2);
            qtyInput.focus();
            return;
        }
        removeNoLinesHint();
        const row = lineTemplate.content.firstElementChild.cloneNode(true);
        row.querySelector(".o_sr_line_name").textContent =
            card.dataset.productName || "";
        row.querySelector(".o_sr_product").value = productId;
        linesContainer.appendChild(row);
        setCardAdded(productId, true);
        updateLineCount();
    };

    document.addEventListener("click", (event) => {
        const button = event.target.closest(".o_sr_add_product");
        if (button) {
            addProduct(button.closest(".o_sr_product_card"));
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
