# catalog-stock-request

Modulos para el flujo de solicitudes de abastecimiento de grupohos (Odoo 19).

## Modulos

### catalog_stock_request

Extiende los stock requests de Odoo para, al confirmar una orden:

- Reservar el stock libre disponible en el deposito
- Generar las cotizaciones de compra (RFQ) solo por la cantidad faltante
- Sugerir el proveedor segun un ranking manual (`supplier_rank` en el contacto) y los precios de compra del producto
- Agregar productos desde el catalogo (product.catalog.mixin)
- Mostrar la obra y el cliente en las ordenes de compra generadas: columna/campo
  "Obra" (filtrable y agrupable) y origin enriquecido con formato
  `SRO/xxx - Ubicacion (Cliente)`. Las compras manuales o de reorden no se ven
  afectadas.

### stock_request_portal

Permite que clientes con usuario portal creen pedidos de abastecimiento
(`stock.request.order`) desde el portal `/my`:

- Formulario multi-linea con el stock libre visible por producto (sin precios)
- Crea la orden en borrador hacia la ubicacion destino configurada en el
  contacto del cliente (`stock_request_location_id`)
- Notifica por email a los usuarios del grupo *Stock Request Manager* y deja
  registro en el chatter
- Un admin confirma desde el backend y `catalog_stock_request` divide
  automaticamente: transfiere el stock disponible y genera RFQs por lo faltante

## Dependencias

- Odoo 19
- [OCA/stock-logistics-request](https://github.com/OCA/stock-logistics-request) rama `19.0`: modulos `stock_request` y `stock_request_purchase`

## Instalacion

```bash
git clone --recurse-submodules https://github.com/EzequielLogra/catalog-stock-request.git
git clone -b 19.0 https://github.com/OCA/stock-logistics-request.git
```

Agregar ambas carpetas al `addons_path` e instalar el modulo necesario desde
Apps: `catalog_stock_request` (solo backend) o `stock_request_portal` (arrastra
todo el flujo).

## Configuracion de stock_request_portal

1. En el contacto del cliente, configurar **Stock Request Destination
   Location** (ubicacion interna/transito destino de las transferencias).
2. Crear el usuario portal desde el contacto del cliente
   (Contacto -> *Conceder acceso al portal*).
3. Rutas: regla interna deposito -> ubicacion cliente y regla *buy* del
   deposito para que la confirmacion genere transferencias y RFQs.

## Notas

- El campo del form "Split Stock / Purchase" activa el comportamiento por orden
  (el portal lo activa siempre)
- Rename del modulo original `hos_stock_request_purchase` (sin prefijo `hos_`)
