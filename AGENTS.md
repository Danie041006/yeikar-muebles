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

## Production order flow

1. Quote converted → `Pedido` nace DIRECTAMENTE en `PRODUCCION` (sin paso intermedio COTIZADO/APROBADO) y se auto-crea la orden por cada línea FABRICADO (`OrdenProduccion` estado=PENDIENTE)
2. `POST /produccion/orden/desde-pedido/{detalle_id}` devuelve la orden existente (idempotente)
3. First etapa changes orden to EN_PRODUCCION
4. Etapas are tracked per area (Ebanistería → Tapicería → Pintura → etc.)
5. Completing all etapas: supervisor presses "Finalizar" which sets estado=FINALIZADA, auto-calculates costs
6. When all órdenes for a pedido are FINALIZADA, pedido → TERMINADO and envio auto-created

### Pedidos de material y captura flexible de madera

- **Pedido ABIERTO**: `es_pedido=true` sin `cantidad` → consumo PENDIENTE sin tocar stock/gasto (piden "madera" a secas). Al confirmar se descuenta todo lo usado.
- **Confirmación MULTI-USO**: `PUT /produccion/consumo/{id}/confirmar` acepta `usos: [{cantidad, unidad_captura?, pieza_*?}]` → un consumo CONFIRMADO por uso (renglón aislado en costos y en la estructura), cada uno con su movimiento (reversa por fila exacta) y su gasto. La cabeza del pedido conserva `cantidad_pedida`.
- **Capturas** (motor único `produccion/unidades.py`): pieza = `(largo m × ancho cm × espesor cm) × n.º piezas ÷ 10000`; `unidad_captura='CM'` en m³ = cuenta del ebanista ÷ 10000; en lineales (m) = cm ÷ 100.
- `consumo_material.detalle_uso` guarda la etiqueta legible ("Pieza 2×10×5 × 2", "1500 cm (cuenta del taller)"); `costos-en-vivo` la expone como `captura` por renglón y `CostosOrdenEnVivo.tsx` la muestra bajo el material.
- **Costo final al finalizar**: `CostoProduccion.costo_total` = materiales + MO registrada + **gastos por sección** (ReglaGastoSeccion, default 10%, helper `_gastos_seccion_orden`); `POST /produccion/costo/calcular/{id}` sin `costo_gastos` también los autocalcula. Con MO con recargo explícito el total cuadra exacto con la tablita de costos en vivo.
- **Nómina**: lee `mano_obra` directamente (no los consumos); el costo de producción suma esa misma fila `monto × (1+recargo/100)`.

### Muebles a la medida y piezas del juego (checklist)

- **Renglón a medida**: `DetalleCotizacion`/`DetallePedido` aceptan `tipo_item=FABRICADO` con `producto_id NULL` si hay `descripcion_especifica` (juegos, diseños nuevos). En Cotizaciones, el selector de productos muestra la fila contextual «Usar “…” como mueble a la medida» al escribir; el precio se digita a mano. Es la vía para teclear notas de papel completas.
- **Conversión cotización→pedido**: los renglones CON producto/material se emparejan por clave y son reutilizables (un renglón cotizado puede dividirse en varias líneas del pedido: facturación independiente por `detalle_pedido`); los A MEDIDA (sin producto) se emparejan **por posición, consumiendo** (antes `(tipo, None, None)` colapsaba todos en uno).
- **Checklist de piezas** (`orden_pieza`): al crear la orden se auto-detecta desde la descripción con `production/piezas.py` («SOFA DE 3 PUESTOS Y 2 POLTRONAS» → Sofá ×1 + Poltrona ×2); sin conjunto claro no genera nada (cero ruido). Endpoints: `POST /produccion/orden/{id}/piezas`, `PUT/DELETE /produccion/pieza/{id}` (marcar = `PUT {completada: true}`). Se muestra en el modal (tab La etapa), en la tarjeta y en la Hoja de Trabajo. NO toca precio, receta, stock ni costos; finalizar AVISA si faltan piezas (no bloquea). Backfill de órdenes viejas: `venv/bin/python scripts/sembrar_piezas_ordenes.py --aplicar`.
- **Ficha/Hoja de Trabajo sin producto**: `GET /produccion/etapa/{id}/referencia-receta` devuelve `producto_id: null`, `materiales: []`, la descripción y `piezas_mueble` (antes 404).

### Piezas de exhibición (showroom)

- `OrdenProduccion.tipo` (PEDIDO | EXHIBICION | STOCK) define el DESTINO de lo fabricado; `es_stock` queda como alias heredado de "sin pedido". El servicio deriva el tipo y rechaza un `tipo` explícito que contradiga el destino
- Las órdenes EXHIBICION usan el MISMO Kanban/etapas que las de pedido; al finalizar NO generan envío: hacen ENTRADA automática en la ubicación EXHIBICIÓN con el costo real, convertido a la moneda del producto (`costo_promedio` siempre vive en la moneda del producto)
- Se venden de stock como si fueran REVENTA (línea tipo_item=REVENTA, pedido nace APROBADO sin producción); al facturar `DetalleVenta.costo_unitario` se sobrescribe con el costo real del inventario (no el estimado de la cotización)

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
- The `backend/` Dockerfile uses Python 3.11, not 3.13 — dev uses whatever is installed

## Rendimiento / offline (VPS + Venezuela)

- **Catálogos con caché SWR**: `api.ts` cachea en memoria los GET de `/catalogos/*` (sin params) con stale-while-revalidate (TTL 10 min, dedup en vuelo) y sirve la copia anterior si el servidor no responde. NO añadas fetches de catálogos nuevos en componentes: ya hay caché. Endpoints de datos (facturas, pedidos, inventario…) NO se cachean.
- **Autocomplete server-side**: los selectores grandes (material, cliente, producto, empleado, proveedor) usan `SearchSelect` con `loadOptions` + `useDebouncedValue`; los listados usan `buscar` + paginación + `X-Total-Count` (ver `hooks/useDebouncedValue.ts`). No cargues catálogos completos al montar ni filtres en memoria listas grandes.
- **PWA**: `vite.config.ts` genera service worker que precachea el shell (carga instantánea, la interfaz abre sin red) y cachea `/api/v1/catalogos/` con NetworkFirst (catálogos disponibles sin internet). El manifest vive en `public/site.webmanifest`.
- **Backend**: GZipMiddleware activo (`app/main.py`, ~95% menos de payload en catálogos); pool de BD con `pool_pre_ping` + `pool_recycle=3600` (`app/db/session.py`) — clave para un VPS con cortes de red. En VPS corre uvicorn persistente (no serverless) → sin cold starts.

## Deployment (Vercel)

- Production se despliega AUTOMÁTICAMENTE en cada `git push` a `main` (GitHub integrado con Vercel). No hace falta `vercel --prod`.
- Dos proyectos conectados al mismo repo: `yeikar-api` (root dir `backend`, Python) y `yeikar-web` (root dir `frontend`, Vite). Cada push dispara ambos.
- URLs: https://yeikar-api.vercel.app y https://yeikar-web.vercel.app

## Migración a VPS (en curso)

- El plan es: frontend sigue en Vercel; backend + BD migran a un VPS Contabo con Caddy (TLS) y backups offsite a Cloudflare R2.
- Guía completa paso a paso (modo principiante): `DEPLOY.md`
- El `docker-compose.yml` ya soporta el VPS: servicio `caddy` (dominio via `API_DOMAIN` en `.env`, `:80` en local), red con subnet fija (Caddy IP 10.200.0.10 → `FORWARDED_ALLOW_IPS`), `backup` con script verificado (`scripts/backup.sh`) y `offsite-sync` a R2 (`scripts/offsite-sync.sh`, inactivo sin credenciales).
