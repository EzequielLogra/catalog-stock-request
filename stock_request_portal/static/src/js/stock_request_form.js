/** @odoo-module */

import { rpc } from "@web/core/network/rpc";

const linesContainer = document.querySelector("#stock_request_lines");
const addLineButton = document.querySelector("#o_sr_add_line");

if (linesContainer) {
    const setFreeQty = (row, product) => {
        const cell = row.querySelector(".o_sr_free_qty");
        if (!cell) {
            return;
        }
        if (!product) {
            cell.textContent = "—";
            return;
        }
        rpc("/my/stock-request-orders/free_qty", { product_ids: [product] }).then(
            (result) => {
                const data = result[product];
                if (!data) {
                    cell.textContent = "—";
                    return;
                }
                const qty = parseFloat(data.free_qty.toFixed(2));
                cell.textContent = `${qty} ${data.uom}`;
            }
        );
    };

    const resetRow = (row) => {
        const select = row.querySelector(".o_sr_product");
        if (select) {
            select.selectedIndex = 0;
        }
        const qty = row.querySelector(".o_sr_qty");
        if (qty) {
            qty.value = "";
        }
        setFreeQty(row, null);
    };

    if (addLineButton) {
        addLineButton.addEventListener("click", () => {
            const firstRow = linesContainer.querySelector(".o_sr_line");
            const newRow = firstRow.cloneNode(true);
            resetRow(newRow);
            firstRow.closest("tbody").appendChild(newRow);
        });
    }

    linesContainer.addEventListener("change", (event) => {
        if (event.target.classList.contains("o_sr_product")) {
            setFreeQty(event.target.closest("tr"), event.target.value || null);
        }
    });

    linesContainer.addEventListener("click", (event) => {
        const button = event.target.closest(".o_sr_remove");
        if (!button) {
            return;
        }
        const row = button.closest("tr");
        const rows = linesContainer.querySelectorAll(".o_sr_line");
        if (rows.length > 1) {
            row.remove();
        } else {
            resetRow(row);
        }
    });
}
