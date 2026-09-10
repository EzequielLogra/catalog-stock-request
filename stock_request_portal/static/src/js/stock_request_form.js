/** @odoo-module */

const linesContainer = document.querySelector("#stock_request_lines");
const lineTemplate = document.querySelector("#o_sr_line_template");
const noLinesRow = document.querySelector("#o_sr_no_lines");

if (linesContainer && lineTemplate) {
    const formatFreeQty = (qty, uom) => {
        const parsed = parseFloat(Number(qty).toFixed(2));
        return uom ? `${parsed} ${uom}` : `${parsed}`;
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
        row.querySelector(".o_sr_free_qty").textContent = formatFreeQty(
            card.dataset.freeQty,
            card.dataset.uom
        );
        linesContainer.appendChild(row);
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
            button.closest("tr").remove();
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
                    '<tr class="table-danger"><td colspan="4">Add at least one product line to submit a request.</td></tr>'
                );
            }
        });
    }
}
