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

## Product recipe / cost system

- Two parallel structures:
  1. `ProductoMaterial` (flat paramétrico) — `seccion`, `tipo_escala`, `cantidad_base`
  2. `SeccionProducto` → `ElementoSeccion` (hierarchical, with policies and production costs)
- Costing engine in `cost_service.py` (`calcular_costo_producto`)
- Excel import fallback: `precio_costo_base`, `precio_venta_base` on Producto model

## Production order flow

1. Pedido created → DetallePedido with dimensions (ancho, largo) and product
2. `POST /produccion/orden/desde-pedido/{detalle_id}` creates `OrdenProduccion` (estado=PENDIENTE)
3. First etapa changes orden to EN_PRODUCCION
4. Etapas are tracked per area (Ebanistería → Tapicería → Pintura → etc.)
5. Completing all etapas: supervisor presses "Finalizar" which sets estado=FINALIZADA, auto-calculates costs
6. When all órdenes for a pedido are FINALIZADA, pedido → TERMINADO and envio auto-created

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
- Frontend `api.ts` has two axios instances: `api` (for `/api/v1/`) and `authApi` (for `/api/auth/`) — use the right one
- Alembic env has an explicit import list for all models — adding a new module means adding its model import there
- `ALLOWED_ORIGINS` default includes `localhost:5173` (Vite dev) — add yours if using a different port
- The `backend/` Dockerfile uses Python 3.11, not 3.13 — dev uses whatever is installed
