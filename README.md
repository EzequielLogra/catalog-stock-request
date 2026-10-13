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
- Stock apartado por destino: si la ubicacion destino tiene una ubicacion de
  stock apartado (ver `stock_request_portal`), el pedido se abastece solo
  desde ahi. No se compra nada y pedir mas de lo apartado da error al
  confirmar.

### stock_request_portal

Permite que clientes con usuario portal creen pedidos de abastecimiento
(`stock.request.order`) desde el portal `/my`:

- Formulario multi-linea con el stock libre visible por producto (sin precios)
- Selector de ubicacion destino: el cliente puede tener varias ubicaciones
  destino (una por contacto hijo tipo *entrega*, campo
  `stock_request_location_id` en cada uno). Cada usuario portal solo ve las
  ubicaciones de los contactos donde figura como supervisor (campo
  `stock_request_supervisor_ids`); si no elige o envia una invalida, se usa
  la primera ubicacion disponible. Archivar el contacto hijo (o vaciar su
  campo, o quitar al supervisor) lo quita del selector.
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
   Para varios destinos, crear contactos hijos (tipo *entrega*) con su
   ubicacion cada uno; el portal los muestra en el selector. Para dar de
   baja un destino, archivar el contacto hijo o vaciar su campo.
2. Crear el usuario portal desde el contacto del supervisor
   (Contacto -> *Conceder acceso al portal*) y agregarlo en **Stock Request
   Supervisors** de cada contacto (obra) para la que puede pedir. Sin esa
   asignacion el usuario no puede crear pedidos.
3. Rutas: regla interna deposito -> ubicacion cliente y regla *buy* del
   deposito para que la confirmacion genere transferencias y RFQs.
4. Stock apartado (opcional): para que las ventas a una obra aparten la
   mercaderia y el supervisor solo pueda pedir lo apartado, cargar en el
   contacto de la obra una **Ubicacion de cliente** interna (la "pre-obra";
   el campo se ve en modo desarrollador). Hace falta una ruta aplicable al
   almacen con una regla deposito -> ubicacion padre de las pre-obras para
   que la venta genere la transferencia interna. Los pedidos del portal para
   esa obra salen de la pre-obra (no de la ubicacion origen de la regla
   interna), no generan compra y se rechazan si superan lo disponible ahi.
   El catalogo del portal muestra para esa obra solo los productos con
   stock libre en su pre-obra, con la cantidad disponible; al cambiar de
   obra se vacia el pedido en curso.
   Si todas las obras del supervisor tienen pre-obra, la pagina solo
   incluye los productos apartados para ellas: el resto del catalogo no se
   envia al navegador.

### Colores del catalogo del portal

El catalogo toma los colores del tema del sitio web. Para personalizarlos sin
tocar el modulo, crear estos parametros del sistema (Ajustes -> Tecnico ->
Parametros del sistema) con un color hexadecimal (`#rgb` o `#rrggbb`):

| Parametro | Se aplica a |
| --- | --- |
| `stock_request_portal.color_primary` | Titulos, categoria activa, total |
| `stock_request_portal.color_accent` | Selector de cantidad, boton agregar, paginador, contador de lineas, boton de envio |

Un valor vacio o invalido se ignora y se usa el color del tema.

## Notas

- El campo del form "Split Stock / Purchase" activa el comportamiento por orden
  (el portal lo activa siempre)
- Rename del modulo original `hos_stock_request_purchase` (sin prefijo `hos_`)
