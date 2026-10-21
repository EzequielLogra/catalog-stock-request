# Capacitación: solicitudes de abastecimiento a obras

Guía de uso del flujo de abastecimiento a obras en Odoo 19 (módulos
`catalog_stock_request` y `stock_request_portal`) y de las ventas a obra con
su cuenta analítica.

Está dividida por rol:

1. [Conceptos](#1-conceptos) — para todos
2. [Supervisor de obra (portal)](#2-supervisor-de-obra-portal)
3. [Administración / depósito (backend)](#3-administración--depósito-backend)
4. [Ventas a una obra](#4-ventas-a-una-obra)
5. [Compras](#5-compras)
6. [Configuración (implementador / admin)](#6-configuración-implementador--admin)
7. [Ejemplos resueltos](#7-ejemplos-resueltos)
8. [Preguntas frecuentes y problemas comunes](#8-preguntas-frecuentes-y-problemas-comunes)

---

## 1. Conceptos

| Término | Qué es |
|---|---|
| **WH/Stock** | El stock del depósito. Es mercadería real, en el almacén. |
| **Obra** | El destino del pedido: la ubicación de la obra o punto de entrega del cliente. |
| **Pre-obra** | Una ubicación **administrativa** (no física) donde queda **apartada** la mercadería ya vendida a una obra. Físicamente sigue en el depósito. Es opcional: no todas las obras la tienen. |
| **Supervisor** | Usuario del portal (del cliente) que pide mercadería para sus obras. |
| **Solicitud de abastecimiento** | El pedido del supervisor. Cuando se confirma, Odoo decide de dónde sale cada unidad. |
| **Reservar** | Comprometer unidades para una transferencia. **No mueve nada físicamente**: lo físico ocurre al validar la transferencia. |
| **Contacto de la obra** | Contacto hijo de la empresa cliente, de tipo *Dirección de entrega*, uno por obra (ej. *AUTONAUTICA - Obra 1*). Las ventas se hacen sobre este contacto. |
| **Cuenta analítica de la obra** | Cuenta del plan analítico **Obras**, una por obra. Junta los ingresos (y los costos imputados) de la obra para ver su resultado. |
| **Modelo de distribución analítica** | Regla que asigna sola la cuenta analítica de la obra a cada línea de venta cuando el cliente del pedido es el contacto de esa obra. |

### Para qué sirve la pre-obra

Evita que la misma mercadería se reserve dos veces. Ejemplo:

- Se vende 5 a la obra → la entrega de la venta lleva 5 de WH/Stock a la pre-obra.
- El supervisor pide esos 5 → el pedido sale **de la pre-obra**, no vuelve a
  tomar otros 5 de WH/Stock.

Sin pre-obra, la venta y el pedido reservarían 5 cada uno: 10 comprometidos
para una necesidad de 5.

### De dónde sale cada unidad (regla de prioridad)

Al confirmar una solicitud, Odoo cubre la cantidad pedida en este orden:

1. **Lo apartado en la pre-obra** de esa obra (si tiene): lo que ya está ahí
   **más lo que está en camino** (por ejemplo, una venta cuya entrega todavía
   no se validó), descontando lo ya prometido a pedidos anteriores.
2. **Lo libre en WH/Stock**: solo lo que no tiene ningún movimiento pendiente
   encima (ni reservado ni esperado por otra entrega) y que no está apartado
   para otra obra.
3. **Compra**: solo lo que no cubrieron los puntos 1 y 2.

> **Regla de oro:** si el stock está, no se compra. Y la misma unidad nunca
> se reserva para dos cosas.

### Qué documentos genera

| Origen de la cantidad | Documento |
|---|---|
| Pre-obra (+ lo que se compra) | Transferencia **pre-obra → obra** |
| WH/Stock | Transferencia **WH/Stock → obra** |
| Faltante | Solicitud de presupuesto (RFQ) al proveedor sugerido. Se recibe **en la pre-obra** si la obra tiene una; si no, en el depósito. |

Por eso un mismo pedido puede generar **dos transferencias**: una desde la
pre-obra y otra desde el depósito.

---

## 2. Supervisor de obra (portal)

### Hacer un pedido

1. Entrar al portal (**Mi cuenta**) → **Solicitudes de abastecimiento** →
   **Nueva solicitud de abastecimiento**.
2. Elegir la **Ubicación destino** (la obra). Solo aparecen las obras donde
   el usuario figura como supervisor.
3. Elegir la **Fecha esperada**.
4. Agregar productos desde el catálogo (se puede filtrar por categoría) y
   ajustar las cantidades.
5. **Enviar solicitud**.

El pedido queda **pendiente de revisión**: el equipo interno recibe un aviso
y lo confirma.

### Qué productos ve el supervisor

- **Obra con pre-obra:** el catálogo muestra solo los productos asignados a
  esa obra (los que tienen o tuvieron mercadería apartada), con la cantidad
  **Disponible** como referencia. Se puede pedir más de lo disponible: la
  diferencia se cubre con stock del depósito o se compra.
- **Obra sin pre-obra:** se ve el catálogo completo.

> Si se cambia de obra a mitad del pedido, **se vacía el pedido en curso**
> (porque cada obra puede tener otro catálogo).

### Seguimiento

En **Solicitudes de abastecimiento** del portal se ven los pedidos enviados y
su estado.

---

## 3. Administración / depósito (backend)

Menú: **Solicitudes de stock → Operaciones → Solicitudes de abastecimiento**.

### Revisar y confirmar un pedido del portal

1. Abrir el pedido (llega notificación por correo y queda registrado en el
   chatter).
2. Revisar las líneas. Antes de confirmar, cada línea muestra:
   - **Libre para usar:** lo apartado en la pre-obra + lo libre en WH/Stock.
   - **Cantidad a comprar:** estimación de lo que faltaría.
   - **Proveedor sugerido.**
3. Confirmar. Odoo reparte cada línea según la [regla de
   prioridad](#de-dónde-sale-cada-unidad-regla-de-prioridad) y genera las
   transferencias y las RFQ.
4. Después de confirmar, cada línea muestra la **Cantidad desde stock** y la
   **Cantidad comprada** reales.

### Despachar

- La transferencia **WH/Stock → obra** queda reservada al confirmar: se
  prepara y se valida como cualquier transferencia interna.
- La transferencia **pre-obra → obra** puede quedar **en espera** si:
  - la entrega de la venta a la pre-obra todavía no se validó, o
  - parte de la cantidad se está comprando.

  Se completa sola cuando llega lo que falta (al validar la entrega de la
  venta o al recibir la compra). Recién ahí se valida.

> Recordatorio: la pre-obra no es un lugar físico. Al validar
> **pre-obra → obra**, la mercadería sale físicamente **del depósito**.

### Cancelar un pedido

Se puede cancelar mientras las compras asociadas estén en borrador (se
cancelan junto con el pedido). Si alguna compra ya está **confirmada**, Odoo no
deja cancelar: primero hay que cancelar esa compra.

---

## 4. Ventas a una obra

Menú: **Ventas → Pedidos → Presupuestos**.

### Cargar el presupuesto

1. **Nuevo**.
2. En **Cliente** elegir el **contacto de la obra** (ej. *AUTONAUTICA,
   AUTONAUTICA - Obra 1*), **no** la empresa.
3. Odoo completa solo:
   - **Dirección de factura:** la empresa (ej. *AUTONAUTICA*). La factura
     sale a nombre de la empresa, con su CUIT.
   - **Dirección de entrega:** la obra.
4. Agregar los productos. Cada línea trae sola la **Distribución analítica**
   de la obra (100 % a la cuenta de la obra). No hay que cargarla a mano.
5. **Confirmar**.

| Campo | Valor |
|---|---|
| Cliente | Contacto de la obra |
| Dirección de factura | Empresa (automático) |
| Dirección de entrega | Contacto de la obra (automático) |
| Distribución analítica (líneas) | Cuenta de la obra (automático) |

> **Importante:** la analítica se asigna según el **Cliente** del pedido, no
> según la dirección de entrega. Si se carga la empresa como cliente y la obra
> solo como entrega, las líneas quedan **sin analítica**.

El plan **Obras** es obligatorio en ventas: si una línea queda sin cuenta
analítica, Odoo **no deja confirmar** el pedido (se puede guardar el
presupuesto, el control es al confirmar).

### Facturar

La analítica pasa de la línea del pedido a la línea de la factura **en el
momento de facturar**. Si se corrige la analítica del pedido después de
facturar, la factura no se actualiza: hay que corregirla en la factura (si
está en borrador) o con nota de crédito y nueva factura.

### Ver el resultado por obra

**Contabilidad → Informes → Estado de resultados** → opción **Analítica** →
agrupar por el plan **Obras**. Queda una columna por obra.

Otras vistas:

- **Contabilidad → Informes → Gestión → Informe analítico**: saldo por cuenta
  analítica.
- **Contabilidad → Contabilidad → Transacciones → Apuntes analíticos**: vista
  pivot (cuenta analítica × cuenta contable), exportable a Excel.

> El inventario se valúa en forma **periódica**: la venta no genera asiento
> de costo de mercadería. En el resultado por obra aparecen los ingresos y
> los costos que se imputen a la obra (por ejemplo, facturas de proveedor con
> la analítica de la obra).

---

## 5. Compras

- Las RFQ generadas por pedidos de obra muestran la columna/campo **Obra**
  (se puede filtrar y agrupar) y en el **Origen** el formato
  `SRO/xxx - Ubicación (Cliente)`.
- El proveedor se elige por **Ranking de proveedor** (campo en el contacto
  del proveedor: menor número = más prioridad, 0 = sin prioridad) y, a
  igualdad, por la secuencia en las tarifas de proveedor del producto.
- Las compras para obras con pre-obra **no se mezclan** en la misma línea con
  compras para otros destinos, porque se reciben en lugares distintos.
- Al recibir una compra de una obra con pre-obra, la mercadería entra en la
  pre-obra (en el sistema) y completa automáticamente la transferencia
  pendiente a la obra.

---

## 6. Configuración (implementador / admin)

### Obra y supervisores

1. En el contacto del cliente (o un contacto hijo tipo *entrega* por cada
   obra) cargar **Ubicación destino de solicitudes de stock**.
2. En el mismo contacto, cargar **Supervisores de solicitudes de stock**.
3. Dar acceso al portal al supervisor (Contacto → *Conceder acceso al
   portal*).

Para dar de baja una obra: archivar el contacto hijo, vaciar la ubicación
destino o quitar al supervisor.

### Pre-obra (opcional)

1. Crear una ubicación interna para la pre-obra. **No puede estar dentro de
   WH/Stock.**
2. En el contacto de la obra, cargar esa ubicación como **Ubicación de
   cliente** (pestaña Inventario; visible en modo desarrollador). Va siempre
   en el **subcontacto de la obra**, nunca en la empresa: Odoo no deja
   guardar una pre-obra en un contacto sin empresa padre. Un cliente con una
   sola obra también necesita su subcontacto.
3. Tener una ruta con una regla depósito → ubicación padre de las pre-obras,
   para que la venta genere la transferencia interna.

### Compras automáticas

- La regla *buy* (Comprar) del depósito debe estar activa.
- Cada producto que se pueda comprar necesita al menos un proveedor en
  **Compra → Proveedores**.

### Alta de una obra para ventas (analítica)

Por cada obra nueva, después de crear el contacto hijo de la obra (ver
[Obra y supervisores](#obra-y-supervisores)):

1. **Cuenta analítica:** Contabilidad → Configuración → Contabilidad
   analítica → **Cuentas analíticas** → Nuevo.
   - **Nombre:** la obra (ej. *Obra 1*).
   - **Plan:** *Obras*.
   - **Cliente:** el contacto de la obra.
2. **Modelo de distribución analítica:** Contabilidad → Configuración →
   Contabilidad analítica → **Modelos de distribución analítica** → Nuevo.
   - **Contacto:** el contacto de la obra (no la empresa).
   - **Empresa:** la empresa que vende.
   - **Distribución analítica:** 100 % a la cuenta de la obra.
   - Producto, categoría y prefijo de cuentas: vacíos.
3. Probar: crear un presupuesto con el contacto de la obra como cliente y
   verificar que la línea traiga la analítica.

> El modelo aplica a las líneas que se cargan **después** de crearlo. Las
> líneas existentes no se recalculan solas: cambiar el producto de la línea o
> cargar la analítica a mano.

### Plan Obras obligatorio en ventas (una sola vez)

Contabilidad → Configuración → Contabilidad analítica → **Planes analíticos**
→ *Obras* → pestaña **Aplicabilidad** → agregar línea:

- **Dominio:** Pedido de venta.
- **Aplicabilidad:** Obligatorio.
- Producto / categoría: vacíos (aplica a todo).

Si se venden también cosas que no son de obra (mostrador, etc.), limitar la
regla a una categoría de producto o crear una cuenta analítica genérica
(*Sin obra*) para esas ventas.

---

## 7. Ejemplos resueltos

Todos con el mismo producto y una obra **con** pre-obra.

| # | Situación | Pedido | Resultado |
|---|---|---|---|
| 1 | Pre-obra: 8. Depósito: 50. | 8 | Transferencia pre-obra → obra por 8. Sin compra. |
| 2 | Pre-obra: 30. Depósito: 50 libres. | 40 | Pre-obra → obra por 30 y WH/Stock → obra por 10. Sin compra. |
| 3 | Pre-obra: 0. Depósito: 50 libres. | 5 | WH/Stock → obra por 5. Sin compra. |
| 4 | Pre-obra: 2. Depósito: 3 libres. | 10 | Pre-obra → obra por 7 (2 reservados + 5 que se compran), WH/Stock → obra por 3, compra de 5. |
| 5 | Venta de 5 con entrega a la pre-obra **sin validar**. Depósito: 10 (5 reservados por esa venta). | 5 | Pre-obra → obra por 5, en espera. **No** toma otros 5 del depósito ni compra. Al validar la entrega de la venta, el pedido queda listo. |
| 6 | Igual que el 5. | 12 | Pre-obra → obra por 7 (5 en camino + 2 a comprar), WH/Stock → obra por 5 (los únicos libres), compra de 2. |
| 7 | Pre-obra: 4, ya prometidos a un pedido anterior. Depósito: 0. | 3 | Compra de 3 (lo apartado ya no está disponible). |

---

## 8. Preguntas frecuentes y problemas comunes

**¿Por qué se generó una compra si "hay stock"?**
Revisar si ese stock está comprometido: reservado para otra entrega, esperado
por otra transferencia pendiente o apartado para otra obra. Esas unidades no
cuentan como libres.

**¿Por qué el pedido salió en dos transferencias?**
Porque una parte se cubrió con lo apartado en la pre-obra y otra con stock
del depósito.

**La transferencia pre-obra → obra está en espera.**
Falta validar la entrega de la venta a la pre-obra o recibir la compra.
Cuando eso ocurre se reserva sola.

**El supervisor no ve un producto.**
Si la obra tiene pre-obra, solo ve productos asignados a ella. Si lo necesita,
se puede vender/transferir a la pre-obra o pedirlo desde el backend.

**El supervisor no ve una obra.**
Verificar que en el contacto de la obra esté cargada la ubicación destino,
que el supervisor figure en **Supervisores de solicitudes de stock** y que el
contacto no esté archivado.

**La línea de venta no trae la cuenta analítica.**
Revisar, en este orden:

1. Que el **Cliente** del pedido sea el contacto de la obra y no la empresa.
2. Que exista el **modelo de distribución analítica** de esa obra, con ese
   mismo contacto.
3. Si la línea se cargó antes de crear el modelo: cambiar el producto de la
   línea (se recalcula) o cargar la analítica a mano.

**No me deja confirmar el pedido de venta: falta la distribución analítica.**
El plan *Obras* es obligatorio en ventas. Ver la pregunta anterior.

**La factura salió sin analítica.**
La analítica se cargó en el pedido después de facturar. Corregirla en la
factura si está en borrador; si ya está publicada, nota de crédito y nueva
factura.

**Mensajes de error al confirmar**

| Mensaje | Causa | Solución |
|---|---|---|
| *No se encontró proveedor para el producto…* | El producto no tiene proveedor y hay que comprar. | Cargar un proveedor en el producto. |
| *La ruta … no tiene regla de compra para el almacén…* | Falta la regla *buy* del depósito. | Activar la ruta Comprar del almacén. |
| *No se encontró ruta interna de abastecimiento…* | No hay ruta depósito → obra. | Configurar la ruta interna hacia la ubicación de la obra. |
| *No se puede cancelar… compras confirmadas* | Hay compras ya confirmadas. | Cancelar primero esas compras. |
| *… no puede tener una ubicación de cliente interna (pre-obra)…* | Se cargó la pre-obra en la empresa (o en un contacto sin empresa padre). | Crear el subcontacto de la obra y cargar ahí la pre-obra. |
| *… no está asignado a …* (portal) | Se pidió un producto que no está en la pre-obra de esa obra. | Ver "El supervisor no ve un producto". |
