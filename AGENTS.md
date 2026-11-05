# YEIKAR ERP — Agent Guide

## Stack

- **Backend**: Python 3.13+ · FastAPI 0.115 · SQLAlchemy 2.0 · Alembic · PostgreSQL
- **Frontend**: React 18 · TypeScript · Vite · Tailwind 3 · React Router 7
- **Auth**: JWT (python-jose) + bcrypt · refresh token rotation

## Quick start

```sh
# backend
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL + SECRET_KEY (pon DEBUG=true en dev)
# --no-proxy-headers: NO confiar en X-Forwarded-For (anti-spoofing del rate
# limit y del lockout de login). En dev detrás de otro proxy, configura
# FORWARDED_ALLOW_IPS en .env en su lugar.
uvicorn app.main:app --reload --no-proxy-headers   # http://localhost:8000

# frontend (separate terminal)
cd frontend && npm install
npm run dev                          # http://localhost:5173, /api proxied → :8000
```

## Database

- Managed via Docker Compose (`docker compose up -d db`) or local PostgreSQL
- Default connection: `postgresql://yeikar:yeikar123@localhost:5432/yeikar`
- Migrations: `cd backend && alembic revision --autogenerate -m "msg" && alembic upgrade head`

## API structure

| Prefix | Module | Auth |
|--------|--------|------|
| `/api/v1/...` | All business modules | JWT (Bearer) |
| `/api/auth/...` | Login, register, refresh | Mixed |

Frontend proxy (`vite.config.ts`) forwards `/api` → `localhost:8000` in dev.
Axios interceptor (`src/services/api.ts`) auto-attaches JWT, handles 401 → refresh → retry.

## Frontend conventions

- **Tailwind**: Custom `yeikar-{primary/secondary/tertiary/neutral}` palette (gold/brown/cream/dark)
- **Fonts**: `font-headline` (Hanken Grotesk), `font-body` (Inter), `font-mono` (JetBrains Mono)
- **API services**: `src/services/*.ts` — each module has a service file wrapping axios calls (e.g., `produccionService`, `productosService`)
- **Pages**: `src/pages/*.tsx`, one per route. Routes defined in `src/App.tsx` with `<PrivateRoute>` + `<DashboardLayout>`
- **Build**: `npm run build` runs `tsc --noEmit` then `vite build`. TypeScript strict mode.
- **Dev**: `npm run dev` — esbuild for TS, no separate typecheck step in dev

## Backend conventions

- Module structure under `backend/app/modules/<name>/`: `model.py`, `router.py`, `schemas.py`, `service.py`
- Routes registered in `app/main.py` with prefix
- Auth dependency: `usuario_actual: Usuario = Depends(get_current_user)` on all endpoints
- Alembic env imports all model files explicitly (see `alembic/env.py`) — always add new models there
- Pydantic v2 with `from_attributes = True` on response schemas

## Key business modules

| Module | Backend prefix | Frontend route | Frontend service |
|--------|---------------|----------------|------------------|
| Products | `/api/v1/producto/...` + `/api/v1/material/...` | `/productos` | `productosService.ts` |
| Quotes | `/api/v1/cotizacion/...` | `/cotizaciones` | `cotizacionService.ts` |
| IQE (cotizador manual) | `/api/v1/intelligent-quotation/...` | `/cotizaciones-ia` | `iqeService.ts` |
| Orders | `/api/v1/pedido/...` | `/pedidos` | `pedidoService.ts` |
| Production (Kanban) | `/api/v1/produccion/...` | `/produccion` | `produccionService.ts` |
| Inventory | `/api/v1/inventory/...` | `/inventario` | `inventarioService.ts` |
| Libro de Entradas y Salidas | `/api/v1/inventario/libro` | Libros → pestaña "Libro de Entradas y Salidas" (`/historial?tipo=entradas-salidas`) | `inventarioService.ts` |
| Sales | `/api/v1/venta/...` + `/api/v1/pago/...` | `/ventas` | `ventaService.ts` |
| Facturación (fiscal SENIAT) | `/api/v1/factura/...` | `/facturacion` | `facturacionService.ts` |

## Production Kanban specifics

- Etapas have states: `ASIGNADA` → `EN_PROCESO` → `PAUSADA` → `COMPLETADA`
- Product recipe stored in `producto_material` with `seccion` field (EBANISTERIA, TAPICERIA, PINTURA, etc.)
- Recipe quantities scale via `tipo_escala` (FIJO, LINEAL, AREA, ESPACIADO, POR_RANGO, FORMULA) — logic in `cost_service.py`
- Stage modal loads reference recipe from `GET /produccion/etapa/{id}/referencia-receta`
- Botón "Hoja de Trabajo" en el modal de etapa → documento imprimible por área (`DocumentoHojaTrabajo.tsx`, SIN montos, foto grande del mueble, observaciones destacadas, materiales con casillas). Genera PDF via `utils/pdfCaptura.ts` (tubería html2canvas→jsPDF con saltos inteligentes `data-pdf-item`; reutilizable para otros documentos). La receta de referencia funciona también para órdenes EXHIBICION/STOCK (producto de la orden, sin detalle de pedido)

## Product recipe / cost system

- Two parallel structures:
  1. `ProductoMaterial` (flat paramétrico) — `seccion`, `tipo_escala`, `cantidad_base`
  2. `SeccionProducto` → `ElementoSeccion` (hierarchical, with policies and production costs)
- Costing engine in `cost_service.py` (`calcular_costo_producto`)
- Excel import fallback: `precio_costo_base`, `precio_venta_base` on Producto model

## Regalo de plástico (colchón) — manual

- **Ya no hay promo automática.** `producto.es_colchon` marca los colchones; en Cotizaciones aparece la pregunta **“¿Lleva plástico de regalo?”** en la línea del colchón.
- La variedad es la lista curada de `promocion_obsequio` (6 productos distintos; `13050 TAPA DE CESTA` puede salir agotada y deshabilitada).
- El regalo es una línea `REVENTA` con `es_obsequio=True`, **precio 0**, máximo **1 por unidad de colchón**. Se valida en `validar_regalos_plastico` al crear/editar cotización y al crear/convertir pedido.
- La tabla `promocion_obsequio` queda como lista curada/histórica: **ya no auto-agrega** regalos. Los regalos históricos siguen funcionando.

## Production order flow

1. Quote converted → `Pedido` nace DIRECTAMENTE en `PRODUCCION` (sin paso intermedio COTIZADO/APROBADO) y se auto-crean las órdenes de cada línea FABRICADO (`OrdenProduccion` estado=PENDIENTE). Si la línea declara PIEZAS del juego, se crea UNA orden interna por pieza; si no, una sola orden como siempre.
2. `POST /produccion/orden/desde-pedido/{detalle_id}` crea las órdenes que falten y devuelve la primera (idempotente)
3. First etapa changes orden to EN_PRODUCCION
4. Etapas are tracked per area (Ebanistería → Tapicería → Pintura → etc.)
5. Completing all etapas: supervisor presses "Finalizar" which sets estado=FINALIZADA, auto-calculates costs
6. When ALL internal orders/pieces for a pedido are FINALIZADA, pedido → TERMINADO and envio auto-created (helper `pedido_produccion_finalizada`)

### Entregas parciales (varios despachos por pedido)

- **Modelo**: `envio.pedido_id` ya NO es único. Cada despacho lleva `envio_detalle` (`detalle_pedido_id`, `orden_produccion_id` opcional para piezas, `cantidad`). Un pedido puede tener N envíos; la guía imprime solo los ítems de ese envío.
- **Regla**: se puede entregar un ítem cuando SU orden está `FINALIZADA` (o es `REVENTA`/`INSUMO`/`SERVICIO`), aunque el resto del pedido siga en producción. No se puede exceder lo pendiente ni duplicar un ítem reservado por otro despacho `PREPARADO`/`EN_TRANSITO`.
- **Estados**: el pedido sigue en `PRODUCCION`/`TERMINADO` mientras falte algo. `entrega_resumen` (en `GET /pedido/` y `GET /pedido/{id}`) expone `total`, `entregado`, `pendiente`, `estado` (PENDIENTE/PARCIAL/COMPLETO) y `envios`. La última entrega pone el pedido en `ENTREGADO`. `PUT /pedido/{id} {estado:'ENTREGADO'}` se rechaza si quedan ítems.
- **Flete**: `GET /pedido/{id}/rentabilidad` suma el `costo_flete_en_moneda_base` de todos los despachos no `FALLIDO` (varios viajes).
- **Cancelación**: no se puede cancelar un pedido con envíos vivos (`PREPARADO`/`EN_TRANSITO`) ni con entregas `ENTREGADO`; primero se marca `FALLIDO`/se elimina el despacho.
- **Despachos**: un `PREPARADO` se puede eliminar (libera sus ítems) para dividir la entrega; un `FALLIDO` se puede reprogramar creando un nuevo despacho con los mismos ítems (el fallido queda en el historial).
- **API**: `GET /api/v1/envio/pendientes/{pedido_id}` (solo Dueño/Admin) devuelve los ítems con `cantidad_lista`; `POST /api/v1/envio/` acepta `detalles: [{detalle_pedido_id, orden_produccion_id?, cantidad}]`; `GET /api/v1/envio/?pedido_id=N` lista los despachos. Sin `detalles` se despacha todo lo pendiente que ya esté listo (compatibilidad/auto).
- **UI**: Pedidos → botón **Entregar** (modal `EntregaParcialModal`), columna de progreso `x/y`, historial de entregas en el detalle. Despachos → asignar chofer/guía; la guía PDF usa `envio.detalles` y el total de la tanda. MisDespachos muestra solo los ítems del despacho.
- **Facturación**: sigue siendo UNA factura por pedido con todas sus líneas; NO hay facturación parcial por entrega (decisión pendiente si se necesita).
- **Migración**: `f3a1b2c4d5e6_entregas_parciales` depende de `f8840b56521c` (piezas del juego): desplegar ambas juntas y correr `alembic upgrade head`.
- Tests: `pytest test/test_entregas_parciales.py -v`.

### Pedidos de material y captura flexible de madera

- **Pedido ABIERTO**: `es_pedido=true` sin `cantidad` → consumo PENDIENTE sin tocar stock/gasto (piden "madera" a secas). Al confirmar se descuenta todo lo usado.
- **Confirmación MULTI-USO**: `PUT /produccion/consumo/{id}/confirmar` acepta `usos: [{cantidad, unidad_captura?, pieza_*?}]` → un consumo CONFIRMADO por uso (renglón aislado en costos y en la estructura), cada uno con su movimiento (reversa por fila exacta) y su gasto. La cabeza del pedido conserva `cantidad_pedida`.
- **Capturas** (motor único `produccion/unidades.py`): pieza = `(largo m × ancho cm × espesor cm) × n.º piezas ÷ 10000`; pieza con las TRES medidas en cm = `unidad_captura='CM'` + `pieza_*` → ÷ 1.000.000 (el taller a veces recibe las medidas en cm); `unidad_captura='CM'` en m³ sin piezas = cuenta del ebanista ÷ 10000; en lineales (m) = cm ÷ 100. La UI del modo "Por pieza" tiene el toggle "Largo (m) + cm" / "Todo en cm" y muestra el resultado de la multiplicación en m³.
- `consumo_material.detalle_uso` guarda la etiqueta legible ("Pieza 2×10×5 × 2", "1500 cm (cuenta del taller)"); `costos-en-vivo` la expone como `captura` por renglón y `CostosOrdenEnVivo.tsx` la muestra bajo el material.
- **Costo final al finalizar**: `CostoProduccion.costo_total` = materiales + MO registrada + **gastos por sección** (ReglaGastoSeccion, default 10%, helper `_gastos_seccion_orden`); `POST /produccion/costo/calcular/{id}` sin `costo_gastos` también los autocalcula. Con MO con recargo explícito el total cuadra exacto con la tablita de costos en vivo.
- **Nómina**: lee `mano_obra` directamente (no los consumos); el costo de producción suma esa misma fila `monto × (1+recargo/100)`.
- **Sobrantes de lámina RETIRADOS** (decisión del dueño: ocultar y apagar, sin borrar datos): el inventario de retazos ya no se crea, ni se consume, ni se repone. Los endpoints `/inventario/sobrantes` NO existen; un `origen_sobrante_id` en un consumo se rechaza con 400 claro; la confirmación por cortes ya no registra el retazo. La tabla `sobrante_lamina`, las columnas `origen_sobrante_id` y el modelo quedan **congelados** (sin uso) para no romper el historial ni las FKs. Los cortes siguen funcionando con costo proporcional al área.

### Muebles a la medida y piezas del juego (checklist)

- **Renglón a medida**: `DetalleCotizacion`/`DetallePedido` aceptan `tipo_item=FABRICADO` con `producto_id NULL` si hay `descripcion_especifica` (juegos, diseños nuevos). En Cotizaciones, el selector de productos muestra la fila contextual «Usar “…” como mueble a la medida» al escribir; el precio se digita a mano. Es la vía para teclear notas de papel completas.
- **Conversión cotización→pedido**: los renglones CON producto/material se emparejan por clave y son reutilizables (un renglón cotizado puede dividirse en varias líneas del pedido: facturación independiente por `detalle_pedido`); los A MEDIDA (sin producto) se emparejan **por posición, consumiendo** (antes `(tipo, None, None)` colapsaba todos en uno).
- **Checklist de piezas** (`orden_pieza`): al crear la orden se auto-detecta desde la descripción con `production/piezas.py` («SOFA DE 3 PUESTOS Y 2 POLTRONAS» → Sofá ×1 + Poltrona ×2); sin conjunto claro no genera nada (cero ruido). Endpoints: `POST /produccion/orden/{id}/piezas`, `PUT/DELETE /produccion/pieza/{id}` (marcar = `PUT {completada: true}`). Se muestra en el modal (tab La etapa), en la tarjeta y en la Hoja de Trabajo. NO toca precio, receta, stock ni costos; finalizar AVISA si faltan piezas (no bloquea). Backfill de órdenes viejas: `venv/bin/python scripts/sembrar_piezas_ordenes.py --aplicar`.
- **Ficha/Hoja de Trabajo sin producto**: `GET /produccion/etapa/{id}/referencia-receta` devuelve `producto_id: null`, `materiales: []`, la descripción y `piezas_mueble` (antes 404).

### Juegos con precio global → órdenes internas por pieza

- **Caso real**: la dueña cotiza UN juego completo (mesa, sillas, sillones…) con un solo precio porque fue gusto del cliente y no dio precios por separado. El cliente ve UN renglón; el taller necesita producir y costear cada pieza aparte.
- **Declaración**: `DetalleCotizacion`/`DetallePedido` aceptan `piezas: [{nombre, cantidad, notas?}]` (tablas `detalle_cotizacion_pieza` / `detalle_pedido_pieza`). `cantidad` es **por unidad del renglón** (por juego). Solo aplica a `tipo_item=FABRICADO`; nombres únicos (sin distinguir mayúsculas/acentos) y cantidad > 0 (validado en Pydantic `validar_piezas_juego`). La UI de Cotizaciones tiene el editor compacto `PiezasJuegoEditor` en los renglones FABRICADO; el precio sigue siendo el del renglón.
- **Conversión**: las piezas se copian de la cotización o se aceptan en el body de conversión. Al crear las órdenes, `crear_ordenes_desde_detalle_pedido()` genera UNA `OrdenProduccion` por pieza con `detalle_pieza_id`, `pieza_nombre` (snapshot) y `cantidad = pieza.cantidad × juegos`; `producto_id=NULL` (la pieza no hereda la receta del juego padre). Sin piezas, se crea una sola orden como siempre. `orden_produccion.detalle_pedido_id` ya NO es único: ahora es 1 renglón → N órdenes.
- **Costos**: cada orden-pieza registra sus materiales/MO/etapas con las pantallas de siempre (no hay etiquetas por renglón). El costo real del renglón es la suma de sus órdenes; `GET /pedido/{id}/rentabilidad` agrega `por_pieza` (cada orden con su costo) y el margen se calcula contra el precio global del renglón. `ReferenciaReceta` de una orden-pieza trae `pieza_nombre`/`juego_nombre` y `materiales: []`.
- **Estructura de costes**: el generador desde producción se SALTA las órdenes-pieza (`detalle_pieza_id`/`pieza_nombre`) para no generar la estructura del juego padre con datos de una sola pieza. La estructura estándar se mantiene manual o por importación.
- **Cierre**: `pedido_produccion_finalizada()` exige que TODAS las órdenes de TODAS las líneas fabricables estén FINALIZADA; el pedido pasa a TERMINADO y se crea UN envío. La venta/factura del renglón no cambia (una línea con precio global).
- **Offline**: las mutaciones de piezas viajan en cotización/pedido; las tablas nuevas tienen `trg_sync_cambio`. La creación de órdenes internas es online (ocurre al convertir o al pasar a PRODUCCION).
- Tests: `pytest test/test_juegos_piezas_produccion.py -v`

### Piezas de exhibición (showroom)

- `OrdenProduccion.tipo` (PEDIDO | EXHIBICION | STOCK | RETRABAJO) define el DESTINO de lo fabricado; `es_stock` queda como alias heredado de "sin pedido". El servicio deriva el tipo y rechaza un `tipo` explícito que contradiga el destino
- Las órdenes EXHIBICION usan el MISMO Kanban/etapas que las de pedido; al finalizar NO generan envío: hacen ENTRADA automática en la ubicación EXHIBICIÓN con el costo real, convertido a la moneda del producto (`costo_promedio` siempre vive en la moneda del producto)
- Se venden de stock como si fueran REVENTA (línea tipo_item=REVENTA, pedido nace APROBADO sin producción); al facturar `DetalleVenta.costo_unitario` se sobrescribe con el costo real del inventario (no el estimado de la cotización)
- **Retrabajo de una pieza** (recolor, retapizado, ajustes para venderla; el caso real: la clienta quiso el mueble del showroom en otro color): `POST /produccion/orden/retrabajo` con `{producto_id, motivo?, cliente_nombre?}` → crea `OrdenProduccion.tipo=RETRABAJO` ligada a la fila de `producto_inventario` (`producto_inventario_id`) y registra la **SALIDA** de la pieza (queda apartada: stock 0, imposible de vender). El taller trabaja igual que cualquier orden (etapas, consumos, MO pagada). Al finalizar, el sistema **NO crea stock nuevo**: la pieza vuelve con su costo **X + Y** (Y = materiales + MO + gastos de sección del retoque) vía ENTRADA con `referencia_tipo=PRODUCCION_RETRABAJO`. El retrabajo **se salta la generación de estructura de costes** (la pieza es única: no redefine receta ni precios del catálogo). Cancelar/eliminar (sin etapas) devuelve la pieza con su costo original. Un solo retrabajo abierto por pieza. `GET /produccion/orden/retrabajos-abiertos` marca las piezas "EN RETRABAJO" (Inventario→Exhibición y selector "+ Exhibición" de Cotizaciones). El precio de venta NO se toca por defecto (pérdida aceptada del dueño); cobrar el retoque es manual (renglón de servicio al pedido). Tests: `pytest test/test_retrabajo_exhibicion.py -v`

### Composición de conjuntos en piezas (Fase 1 — solo catálogo)

- **Modelo**: un mueble puede ser un CONJUNTO de piezas (un comedor = mesa ×1 + sillas ×6). `producto.es_conjunto` lo mantiene el endpoint de composición (no se edita a mano); `producto.es_pieza` marca los productos que son piezas. Tabla nueva `producto_pieza` (`producto_id` = conjunto, `pieza_producto_id`, `cantidad`, `orden`, UNIQUE conjunto+pieza).
- **La pieza es un `Producto` del catálogo**: su costo y su precio viven en `precio_costo_base`/`precio_venta_base` de ESE producto, no se duplican en la composición. Así la misma pieza sirve para armar el conjunto, cotizarse sola o quedar como sobrante vendible.
- **NO toca la receta** (`producto_material` / secciones) ni el motor de costos: es el desglose comercial y de costo del mueble.
- **API**: `GET /api/v1/producto/{id}/piezas` (cualquier usuario con módulo productos) y `PUT /api/v1/producto/{id}/piezas` (**solo Dueño/Admin**, contrato de lista completa: lo que llega ES la composición, `[]` la vacía y desmarca `es_conjunto`). Devuelve `resumen` con la conciliación suma-de-piezas vs costo/precio del conjunto y sus diferencias (se REPORTAN, nunca se autocorrigen: puede ser el precio de combo) + avisos de piezas sin costo/precio y de monedas mezcladas.
- **Reglas**: sin auto-referencia, sin piezas duplicadas, `cantidad > 0`, y **no se anidan conjuntos** (un conjunto no puede ser pieza de otro). Usar un producto como pieza lo marca `es_pieza=True` (nunca se desmarca solo). Borrar un producto que es pieza de un conjunto responde **409** (la FK es RESTRICT).
- **UI**: panel "Piezas del conjunto" en Productos (panel derecho, `components/Productos/ComposicionEditor.tsx`): agregar pieza del catálogo o crearla al vuelo, cantidad/costo/precio por pieza y botón varita **precio = costo + 40 %** (sugerido y editable). Guardar actualiza primero los precios de las piezas cambiadas y luego la composición.
- **Migración**: `c7d8e9f0a1b2_producto_composicion` (100% aditiva, con `trg_sync_cambio` en la tabla nueva). En la BD local también quedó aplicada la pendiente `u9n8i7f6g5a4` (Gasto Familiar).
- Tests: `pytest test/test_producto_composicion.py -v`.
- **Preexistente (no es de esta feature)**: `test_sync_offline.py::test_cambios_paginados_y_estado` falla en la BD local porque `sync_cambio` ya tiene ~205.000 filas y el test solo pagina 50 × 2000 = 100.000, así que nunca alcanza los cambios recientes.

### Composición comercial en cotización/pedido (Fase 2)

- **Qué agrega**: cotizar UN renglón compuesto con piezas de muebles DISTINTOS (la mesa de un comedor del showroom + las sillas de otro), con precio por pieza; al convertir, el/los conjuntos se **despiezan**, las piezas llevadas se congelan con su costo real y los **sobrantes vuelven al showroom** como piezas sueltas vendibles.
- **Columnas** (`detalle_cotizacion_pieza` y espejo en `detalle_pedido_pieza`): `producto_id` (producto del catálogo que ES la pieza), `precio` (en la moneda de la cotización), `origen` (`FABRICADO` | `EXHIBICION`; NULL/`FABRICADO` = clásico), `conjunto_origen_id` (conjunto a despiezar), `modificacion`, `requiere_retrabajo`, `precio_modificacion` (cobro del retoque, por unidad). En el pedido también `costo_unitario` (costo REAL congelado en COP) y `detalle_pedido.piezas_apartadas` (idempotencia del despiece).
- **Regla de precio**: si TODAS las piezas traen `precio`, el precio del renglón es `Σ cantidad × (precio + precio_modificacion si requiere retrabajo)`; el backend lo recalcula y recompone `total_estimado` (la UI muestra la suma y bloquea el precio manual). Si NINGUNA trae precio, el renglón conserva su precio global (juegos clásicos). Mezclar precios parciales es **error** (422), igual que `EXHIBICION` sin `producto_id`, retrabajo sin modificación o `precio_modificacion` sin retrabajo.
- **Costo**: el estimado de la cotización usa `precio_costo_base` de cada producto (convertido a COP). En el pedido, el costo REAL de una pieza de exhibición se congela al despiezar y sale de la parte proporcional del costo del conjunto (pesos = costo de catálogo; si falta, cantidad); el valor total del conjunto se conserva entre piezas llevadas y sobrantes. `GET /pedido/{id}/rentabilidad` suma `costo_unitario × cantidad` de las piezas de exhibición + los costos de las órdenes (incluido el retrabajo). El flag `piezas_apartadas` evita mover el inventario dos veces.
- **Despiece** (`orders/despiece.py`): agrupa por `conjunto_origen_id`, calcula los conjuntos necesarios (`ceil` por pieza), hace SALIDA del conjunto a `EXHIBICIÓN` y ENTRADA de los sobrantes como piezas sueltas con costo prorrateado. El sobrante queda marcado `es_exhibicion=True` (vendible en el showroom) sin tocar su receta ni su costo/precio de catálogo. Si el conjunto no tiene fila de inventario (alta simple de exhibición) no se bloquea y no se inventan movimientos; si tiene fila pero no alcanza, responde un error claro. Las piezas de exhibición sin conjunto se apartan con SALIDA simple.
- **Producción**: las piezas `EXHIBICION` sin retrabajo **no generan orden** (ya están listas); las que tienen retrabajo generan una orden `tipo=RETRABAJO` ligada al pedido (`producto_inventario_id=NULL`, al finalizar NO vuelven al showroom porque se entregan al cliente). Un combo solo de exhibición sin retrabajo nace `APROBADO` (nada que fabricar); con piezas fabricadas o retrabajo nace `PRODUCCION`. `_detalle_fabricable_finalizado` considera terminado el renglón cuando sus piezas fabricadas/retrabajos están resueltos (retrabajo cancelado cuenta como resuelto).
- **Entrega**: `envio_detalle.detalle_pieza_id` distingue varias piezas sin orden del mismo renglón. `GET /envio/pendientes/{pedido}` las muestra listas (`estado_produccion="LISTA"`) y `POST /envio/` acepta `detalle_pieza_id`. El índice parcial `uq_envio_detalle_sin_orden_pieza` permite mesa + sillas en el mismo despacho.
- **Facturación**: el renglón sigue siendo `FABRICADO` (producto NULL si es combo a medida); el despiece ya sacó el inventario, así que la factura NO descuenta las piezas otra vez.
- **UI**: `components/Cotizaciones/PiezasJuegoEditor.tsx` tiene el modo "Usar precio por pieza": producto del catálogo (buscador), precio sugerido según moneda, origen (se fabrica / del showroom), conjunto de origen y retrabajo. En `Inventario → Exhibición → detalle de la pieza` hay una pestaña **Composición** que reutiliza `components/Productos/ComposicionEditor.tsx`.
- **Migraciones**: `d9e0f1a2b3c4_composicion_comercial` (columnas + FKs) y `f2a3b4c5d6e7_envio_piezas_sin_orden` (índice del despacho). Ambas dependen de `c7d8e9f0a1b2`.
- Tests: `pytest test/test_combo_exhibicion.py -v` (despiece, sobrantes, entrega, rentabilidad, retrabajo ligado y validaciones).

## Libro de caja y clasificación de gastos (G D/C/P/F/I)

- **Campo `gasto.clasificacion`** (opcional): `GASTO_DEDUCIBLE`, `GASTO_PERSONAL`, `GASTO_FAMILIAR` ("Gasto Familiar"), `GASTO_FABRICA` ("Gastos de Fábrica"), `GASTO_CONSTRUCCION` ("Gastos de Construcción"), `NOMINA_FABRICA` ("Nómina Fábrica"), `NOMINA_CASA` ("Nómina Casa"), `SERVICIO_FABRICA` ("Servicio Fábrica"), `SERVICIO_CASA` ("Servicio Casa"), `GASTO_OFICINA` ("Gastos de Oficina"), `GASTO_HERRAMIENTAS` ("Gastos de Herramientas"), `GASTO_CAMIONES` ("Gastos de Camiones"), `GASTO_INVERSION`, `PRESTAMO`, `DONACION`, `IMPUESTO`. Decisión de la dueña (03/11/2026): "Gasto de Casa" se unificó en **Gasto Familiar** (ya no existe `GASTO_CASA`; el código `G C` del libro se sigue aceptando y se guarda como `GASTO_FAMILIAR`). Se muestra con nombre completo (nunca "G F"). Decisión de la dueña (30/10/2026): Familiar, Fábrica y Camiones son canastas **separadas**; la letra `F` del libro sigue siendo Familiar (los gastos ya registrados quedan ahí) y la fábrica se escribe completa (`G FABRICA`) o desde el dropdown. El parser del libro acepta `G CAMION(ES)`, `G FABRICA`, `G CONSTRUCCION(ES)`, `G NOMINA (DE) FABRICA/CASA`, `G SERVICIO (DE) FABRICA/CASA`, `G OFICINA(S)` y `G HERRAMIENTA(S)` a palabra completa, y el egreso clasificado "Gastos de Camiones" reutiliza el TipoGasto `GASTOS DE CAMIONES` del catálogo (comparación case-insensitive, sin duplicados). Es independiente de `tipo_gasto.categoria` (OPERATIVO/PASIVO/PRODUCCION).
- **Movimientos de caja**: `movimiento_caja.persona_entidad` es la otra parte del movimiento (quien entrega en una entrada, quien recibe en una salida: cliente, proveedor, empleado...). No es el usuario que registra. Es opcional. `movimiento_caja.concepto` reemplaza a `observaciones` (la columna se renombró). `referencia` queda interna (links a pago/gasto/importación) y ya no se pide en el formulario. La `tasa_cambio` del movimiento también es interna: se resuelve sola con la TRM del día (1 para COP) y no se pide en caja.
- **Compras de inventario en caja**: la salida espejo del Gasto se escribe legible — `Compra de material: 15 metros de TELA CUSCO HIELO` (unidad del catálogo en singular/plural; si no se reconoce, se respeta tal cual). Guarda `persona_entidad` (proveedor indicado, o quien registró la compra si no hay) y `usuario_id` (Registrado por), y se clasifica `GASTO_FABRICA` (`GASTO_OFICINA` si el movimiento es del departamento OFICINA). Lógica en `inventory/service.py` (`_descripcion_compra_material`). Histórico: `venv/bin/python scripts/reformatear_compras_inventario.py --gasto-ids N,N --usuario-id N --aplicar` (dry-run por defecto).
- **Transferencias entre cuentas**: `POST /api/v1/cuenta/transferencia` acepta `tasa_conversion` (unidades de moneda destino por 1 de origen; editable y prellenada por `GET /api/v1/cuenta/tasa-transferencia`), `interes` (en moneda destino, con `interes_signo` SUMA/RESTA) y `persona_entidad` (tercero: banco, prestamista...). La tasa manual conserva el guardia de ±50% contra la TRM registrada; si no hay TRM registrada para el par, se permite digitarla. La tasa y el interés quedan en las dos patas (`movimiento_caja.tasa_conversion` / `interes`); el interés ajusta el saldo de la cuenta destino y **no** genera un gasto/ingreso separado (es un dato de la transferencia para reportes). Tests: `pytest test/test_transferencias_caja.py -v`.
- **Importación**: `POST /api/v1/cuenta/libro/preview` analiza el texto pegado sin escribir; `POST /api/v1/cuenta/libro/importar` crea los movimientos y los gastos. `GET /api/v1/cuenta/libro?metodo_caja_id=&fecha_desde=&fecha_hasta=` devuelve la vista con saldo corrido. `DELETE /api/v1/cuenta/libro/{periodo}?metodo_caja_id=` deshace una importación. Arriba del libro se muestra el resumen **"Gastos del período por clasificación"**; al hacer clic en un tipo se filtra la tabla a esos egresos (el saldo corrido se conserva; "Ver todos" quita el filtro). Lógica en `backend/app/modules/reports/libro_caja.py`; UI en **Cuentas → Libro de caja**.
- **Editar/eliminar una fila del libro**: clic en la fila → `Editar` (fecha, hora, tipo, monto, persona, concepto y **tipo de gasto/clasificación**) o `Eliminar` (`DELETE /api/v1/cuenta/movimiento/{id}`). El tipo de gasto se puede cambiar o agregar incluso si la salida no tenía Gasto: se actualiza el Gasto espejo (`referencia = "Gasto #N"`) o se crea uno nuevo sin duplicar el movimiento de caja (`PUT /api/v1/cuenta/movimiento/{id}` acepta `clasificacion`; un préstamo ya creado no se reclasifica desde ahí). Al borrar una salida con Gasto espejo se elimina también el `Gasto`, para que desaparezca de Gastos y de los reportes. Una transferencia se borra completa (sus dos patas) y solo Dueño/Administrador puede hacerlo; de ella solo se puede corregir la hora (se aplica a las dos patas). Los movimientos de un cobro de venta (`pago_id`) no se borran desde caja: sus datos se corrigen/eliminan desde Ventas. Editar y eliminar dejan evento en auditoría (`movimiento_caja`). Tests: `pytest test/test_libro_caja.py -v`.
- El parser infiere D/M vs M/D por el mes dominante, usa el **cambio de saldo** como signo (el libro a veces trae el ingreso/egreso en la columna contraria), omite filas de notas sin montos y marca **posibles duplicados** comparando sentido + importe + nombre contra los movimientos ya existentes. La importación puede omitirlos (`omitir_duplicados`, default true) y **cuadrar el saldo inicial** contra lo que ya tiene la cuenta (`cuadrar_saldo_inicial`, registra un ajuste por la diferencia, no una apertura duplicada).
- Tests: `cd backend && venv/bin/python -m pytest test/test_libro_caja.py -v`.

## Cuentas por pagar (fiado) — abonos con descuento del proveedor

- **Módulo**: Gastos → pestaña **Por Pagar** (`/api/v1/cuentas-por-pagar/...`). La deuda nace con su `Gasto` (P&L) sin tocar caja.
- **Abono con descuento** (ej. 5% por mayorista): modal **Abonar** → campo **“Descuento del proveedor (%)”** opcional (cualquier %, vacío = sin descuento). El monto escrito es lo que se aplica a la deuda; el descuento reduce la salida de caja. **El % se calcula sobre la deuda ORIGINAL (`cuenta_por_pagar.monto`), no sobre el monto del abono**: una deuda de 9.800.000 con saldo 5.000.000 al 5% genera 490.000 de descuento y el cajero paga 4.510.000 (la deuda baja los 5.000.000).
- **Regla de oro**: `pago_cuenta_por_pagar.monto` = dinero que sale de caja (neto); `descuento` = condonado; `monto + descuento` = lo que baja la deuda. `cuenta_por_pagar.monto_pagado` acumula efectivo y `monto_descontado` acumula descuentos; `saldo = monto − monto_pagado − monto_descontado`.
- **El costo NO cambia**: el `Gasto` original (y el costo de inventario) sigue siendo el precio completo; el descuento no lo reduce ni crea otro gasto/ingreso. La caja solo registra el neto.
- **Multimoneda**: el descuento va en la moneda de la deuda y solo el neto se convierte a la moneda de la cuenta con la `tasa_cambio` (misma fórmula que un abono normal).
- **Revertir** un abono devuelve efectivo + descuento al saldo y borra la salida de caja. Migración: `p6a7b8c9d0e1_descuento_abonos_por_pagar`.
- Tests: `pytest test/test_cuentas_por_pagar.py -v`.

## Préstamos por cobrar (dinero que la empresa prestó)

- **Nacen en Cuentas, no en un módulo aparte**: `Salida` de caja con Tipo de gasto **Préstamo** + `persona_entidad` obligatoria. El backend crea el `Gasto` de siempre **y** un registro en `prestamo` (tabla nueva) ligado al movimiento de caja. En la UI hay un sub-selector: **"Presté dinero (me deben)"** (`tipo_prestamo=POR_COBRAR`, default) vs **"Pagué un préstamo que yo debo"** (`PAGO_DEUDA`, no genera deuda).
- **Se cobran desde la Entrada**: `ENTRADA` con `cobro_prestamo: {persona_nombre, moneda_id, monto, tasa_conversion?}`. La entrada de caja y el abono (`pago_prestamo`) se crean en la **misma transacción**. El monto va en la moneda del préstamo y puede ser parcial; se aplica **FIFO** (más antiguo primero) entre los préstamos pendientes de esa persona y moneda.
- **Moneda distinta**: si la cuenta donde entra el dinero no es la del préstamo, `tasa_conversion` es obligatoria (`1 [moneda préstamo] = X [moneda cuenta]`). El valor en COP del cobro se congela a la tasa del préstamo (no se revalúa) y `movimiento_caja.tasa_cambio` se deriva para que `monto × tasa = monto_en_moneda_base`.
- **Borrar/editar**: eliminar la entrada de cobro devuelve el saldo al préstamo; eliminar la salida que prestó borra el préstamo (si no tiene cobros; si los tiene responde 409). Editar monto/fecha/persona de la salida sincroniza la deuda solo si no hay cobros; el concepto sí se puede corregir siempre. El gasto no se puede borrar desde Gastos (hay que hacerlo desde Cuentas).
- **API**: `GET /api/v1/prestamo/` (historial con pagos), `GET /api/v1/prestamo/pendientes` (selector: persona + moneda + saldo) y `GET /api/v1/prestamo/resumen` (totales por moneda y por persona). Módulo de permisos: `cuentas`.
- **No hay backfill**: solo se registran los préstamos creados desde el despliegue (31/10/2026). Los `PRESTAMO` históricos quedan como gastos y no generan deuda.
- **UI**: tarjeta "Préstamos por cobrar" en **Cuentas → Cuentas y saldos** y el detalle con abonos. Sin pantalla nueva en el menú.
- Tests: `pytest test/test_prestamos.py -v`.

## Testing

```sh
cd backend && source venv/bin/activate
pytest test/ -v
pytest test/test_iqe.py -v     # specific test
```

## Docker (production)

```sh
docker compose up -d --build    # builds backend + frontend + db
# Backend on :8000, Frontend on :80, DB on :5432
```

## Gotchas

- El Cotizador IA es 100% manual (sin APIs de pago): `contexto-exportar` arma el paquete (inventario + receta similar + ejemplos reales + esquema JSON) para una IA de navegador, e `import-structure` importa el JSON pegado. No requiere `OPENAI_API_KEY` ni claves de Gemini
- Alcance de cotizaciones: TODOS con el módulo `cotizaciones` VEN todas las cotizaciones (lectura compartida), pero solo su autor (o Dueño/Administrador) puede editarlas, cambiar estado, eliminarlas o convertirlas a pedido. `PUT /cotizacion/{id}` acepta `detalles` y los reemplaza completos (mismo contrato que al crear). El botón lápiz del frontend se oculta si no eres el autor
- Frontend `api.ts` has two axios instances: `api` (for `/api/v1/`) and `authApi` (for `/api/auth/`) — use the right one
- Alembic env has an explicit import list for all models — adding a new module means adding its model import there
- `ALLOWED_ORIGINS` default includes `localhost:5173` (Vite dev) — add yours if using a different port
- **Fotos de producto (varias por mueble)**: cada foto es una fila de `adjunto` tipo PRODUCTO; no hay límite. Se listan en ORDEN DE SUBIDA (`Producto.fotos`, `adjuntos_info`/`adjuntos_info_batch` con `orden="asc"`): la PRIMERA es la portada (cotización, tarjetas, factura, selector y hero de la Hoja de Trabajo) y las nuevas se agregan al final. `DocumentoCotizacion` muestra hasta 2 por renglón; la Hoja de Trabajo muestra TODAS (hero + "Vistas adicionales"). Multicarga en `Productos.tsx` y en "Producto nuevo" de Cotizaciones (subida secuencial: el orden de selección = orden de portada). OJO: los comprobantes (CRUDO/PAGO/GASTO/COMPRA) mantienen el default `orden="desc"` (la más reciente primero): en crudo "cambiar foto" depende de eso (`_foto_crudo`). Test: `pytest test/test_adjuntos_orden.py -v`
- **Fecha de los abonos**: `pago.fecha` es la fecha real del pago (editable, puede ser pasada; se ancla a mediodía y no admite futuros) y `pago.created_at` es el momento del registro (automático, hora VE, inmutable). `pago.creado_por_id` guarda quién lo registró. `POST /pago/` acepta `fecha`; sin ella → HOY en hora VE (`ahora_ve`). La conversión cotización→pedido acepta `fecha_adelanto` (mismo default) y el primer pago de la factura queda con esa fecha. `PUT /pago/{id}` corrige SOLO fecha/referencia/observaciones y arrastra la fecha del `movimiento_caja` (no toca monto/moneda/método). La UI muestra "Pago: ..." y "Registrado: ... · usuario" (y avisa si se registró días después). Frontend: "Fecha en que se hizo el pago" en el modal de Ventas (default `hoyVE()`, se envía como `YYYY-MM-DDT12:00:00`) y "Fecha del abono" en el modal de conversión. Test: `pytest test/test_pago_fecha.py -v`
- The `backend/` Dockerfile uses Python 3.11, not 3.13 — dev uses whatever is installed

## Rendimiento / offline (VPS + Venezuela)

- **Catálogos con caché SWR**: `api.ts` cachea en memoria los GET de `/catalogos/*` (sin params) con stale-while-revalidate (TTL 10 min, dedup en vuelo) y sirve la copia anterior si el servidor no responde. NO añadas fetches de catálogos nuevos en componentes: ya hay caché. Endpoints de datos (facturas, pedidos, inventario…) NO se cachean.
- **Autocomplete server-side**: los selectores grandes (material, cliente, producto, empleado, proveedor) usan `SearchSelect` con `loadOptions` + `useDebouncedValue`; los listados usan `buscar` + paginación + `X-Total-Count` (ver `hooks/useDebouncedValue.ts`). No cargues catálogos completos al montar ni filtres en memoria listas grandes.
- **PWA**: `vite.config.ts` genera service worker que precachea el shell (carga instantánea, la interfaz abre sin red) y cachea `/api/v1/catalogos/` con NetworkFirst (catálogos disponibles sin internet). El manifest vive en `public/site.webmanifest`.
- **Backend**: GZipMiddleware activo (`app/main.py`, ~95% menos de payload en catálogos); pool de BD con `pool_pre_ping` + `pool_recycle=3600` (`app/db/session.py`) — clave para un VPS con cortes de red. En VPS corre uvicorn persistente (no serverless) → sin cold starts.

## Sync offline (F0 — backend listo)

- **Bitácora de cambios**: triggers PostgreSQL en las tablas de negocio llenan `sync_cambio` (cursor monótono `id`) en INSERT/UPDATE/DELETE, incluidas cascadas de FK — única fuente de tombstones. `GET /api/v1/sync/cambios?desde=<cursor>&limite=` los entrega; `GET /api/v1/sync/estado` da el último cursor.
- **Push idempotente**: `POST /api/v1/sync/push` recibe `{operaciones: [{operacion_id (UUID), tipo, payload, ocurrida_en}]}` y aplica cada una con el handler registrado en `app/modules/sync/handlers.py`. Los handlers reutilizan los services del módulo (mismos permisos/validaciones/auditoría que la vía online). La idempotencia vive en `sync_operacion`: reintentar la misma `operacion_id` devuelve el resultado original. Estados: `ok`, `conflicto`, `error`, `en_proceso`.
- **Agregar un handler** (al hacer offline un módulo, F2+): decorar `@handler("modulo.accion")` y lanzar `SyncConflicto`/`ValueError` para rechazos de negocio.
- **Tablas nuevas**: la migración `b3c4d5e6f7a8` adjuntó `trg_sync_cambio` a las tablas existentes; tras crear una tabla nueva correr `venv/bin/python scripts/adjuntar_triggers_sync.py --aplicar`. No se replican: `audit_event`, `refresh_token`, `login_intento`, `sesion`, `credencial_webauthn`, `sync_*`, `alembic_version`.
- **Trigger `sync_registrar_cambio`**: compara la fila completa con `to_jsonb(NEW) IS NOT DISTINCT FROM to_jsonb(OLD)` (migración `g5c6d7e8f9a0`). El operador directo `NEW IS NOT DISTINCT FROM OLD` revienta con columnas `json` (no tienen equality operator) y rompía los UPDATE de tablas como `producto_material` (editar recetas).
- **Pruebas**: `pytest test/test_sync_offline.py -v`.

## Frontend offline (F1/F2/F3 — base + Producción + Ventas)

- **Interruptor de producción**: TODO el modo offline vive detrás de `VITE_OFFLINE_MODE` (`src/offline/interruptor.ts`). Producción (Vercel, `npm run build`) compila con la bandera APAGADA: sin PIN, sin espejo, sin cola, sin llamadas a `/sync` — comportamiento idéntico al de siempre. Encendido en dev (`.env.development`) y en `npm run build:offline` (`.env.offline`) para pruebas/VPS. El guardián `e2e/offline-apagado.spec.ts` verifica que el build normal no active nada.
- **Capa `src/offline/`**: `db.ts` (Dexie: `espejo`, `outbox`, `meta`, `ids`), `cifrado.ts` (AES-GCM + PBKDF2 con WebCrypto), `repo.ts` (espejo cifrado, IDs locales), `cache.ts` (helpers genéricos `conCache`/`mutarOEncolar`/`parchearCache` sobre la tabla `cache_api`), `sesion.ts` (sesión cacheada + PIN), `sync.ts` (motor: push del outbox, pull de la bitácora, reintento a 15s, listeners `online`/visibilidad/60s).
- **Producción offline (F2)**: `produccionService` cachea los GET del Kanban (`ordenes:`, `orden:`, `etapa:`, `receta:`, `costos:`, `areas`) y encola las mutaciones sin red con parches optimistas (`src/offline/produccionOffline.ts`): estado de etapa, pasar a área, asignados, piezas, consumos y mano de obra. Siguen online-only: crear orden, finalizar orden y costos.
- **Clientes / Cotizaciones / Pedidos offline (F3)**: `clienteService` completo (crear/editar/eliminar); `cotizacionService` crear/editar/eliminar; `pedidoService` lectura + estado/observaciones/eliminar. Editar un registro creado offline actualiza la operación encolada (`actualizarOperacionLocal`), no crea otra. **Convertir cotización→pedido sigue online-only** (crea venta/órdenes; se hará en F4).
- **Handlers de push**: `app/modules/sync/handlers.py` (`produccion.*`, `cliente.*`, `cotizacion.*`, `pedido.*`) reutilizan services/routers; lanzar `SyncConflicto`/`ValueError` = conflicto visible.
- **Sesión offline**: tras el primer login online, `PromptPinOffline` ofrece configurar un PIN (4-8 dígitos). Con PIN, la clave del dispositivo queda envuelta con PBKDF2; al reabrir sin red aparece `PantallaBloqueo` → PIN → adentro. En `/login` sin red hay "Entrar sin conexión (PIN)". Logout (o 5 PIN fallidos) **borra la copia local completa**.
- **Indicador**: `OfflineIndicator` (en `DashboardLayout`) muestra sin conexión / pendientes / conflictos con "Sincronizar ahora". `AuthContext` expone `sinConexion`, `bloqueado`, `resumen`, `desbloquear`, `configurarPin`.
- **E2E offline**: el service worker solo existe en build → `npm run build:offline && npm run preview` y `npx playwright test e2e/offline.spec.ts e2e/offline-produccion.spec.ts e2e/offline-clientes.spec.ts` (usan `context.setOffline`). El guardián `e2e/offline-apagado.spec.ts` se corre al revés: `npm run build && npm run preview`. El motor solo sincroniza con sesión y clave desbloqueada.

## Deployment (Vercel)

- Production se despliega AUTOMÁTICAMENTE en cada `git push` a `main` (GitHub integrado con Vercel). No hace falta `vercel --prod`.
- Dos proyectos conectados al mismo repo: `yeikar-api` (root dir `backend`, Python) y `yeikar-web` (root dir `frontend`, Vite). Cada push dispara ambos.
- URLs: https://yeikar-api.vercel.app y https://yeikar-web.vercel.app

## Migración a VPS (en curso)

- El plan es: frontend sigue en Vercel; backend + BD migran a un VPS Contabo con Caddy (TLS) y backups offsite a Cloudflare R2.
- Guía completa paso a paso (modo principiante): `DEPLOY.md`
- El `docker-compose.yml` ya soporta el VPS: servicio `caddy` (dominio via `API_DOMAIN` en `.env`, `:80` en local), red con subnet fija (Caddy IP 10.200.0.10 → `FORWARDED_ALLOW_IPS`), `backup` con script verificado (`scripts/backup.sh`) y `offsite-sync` a R2 (`scripts/offsite-sync.sh`, inactivo sin credenciales).
