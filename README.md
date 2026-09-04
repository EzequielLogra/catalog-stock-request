# catalog_stock_request

Extiende los stock requests de Odoo para, al confirmar una orden:

- Reservar el stock libre disponible en el deposito
- Generar las cotizaciones de compra (RFQ) solo por la cantidad faltante
- Sugerir el proveedor segun un ranking manual (`supplier_rank` en el contacto) y los precios de compra del producto
- Agregar productos desde el catalogo (product.catalog.mixin)

## Dependencias

- Odoo 19
- [OCA/stock-logistics-request](https://github.com/OCA/stock-logistics-request) rama `19.0`: modulos `stock_request` y `stock_request_purchase`

## Instalacion

```bash
git clone --recurse-submodules https://github.com/EzequielLogra/catalog-stock-request.git
git clone -b 19.0 https://github.com/OCA/stock-logistics-request.git
```

Agregar ambas carpetas al `addons_path` e instalar `catalog_stock_request` desde Apps.

## Notas

- El campo del form "Split Stock / Purchase" activa el comportamiento por orden
- Rename del modulo original `hos_stock_request_purchase` (sin prefijo `hos_`)
