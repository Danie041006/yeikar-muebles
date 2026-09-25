# 📘 Guía del Desarrollador — YEIKAR ERP

> **Para quién es esto:** para cualquier desarrollador (nuevo, o el mismo Daniel
> volviendo después de meses) que quiera entender el proyecto, levantarlo
> localmente, o continuar desarrollándolo. Es deliberadamente generosa en
> detalles: cada módulo, cada tabla importante, cada función clave y cada
> decisión de negocio rara está explicada acá.
>
> Guía documentada/progresada de forma incremental a la fecha: **agosto 2026**.
> Si algo no cuadra con el código, el código manda — esta guía se debe
> mantener actualizada.

---

## Contenido

1. [¿Qué es YEIKAR?](#1--qué-es-yeikar)
2. [Stack tecnológico](#2--stack-tecnológico)
3. [Estructura del proyecto](#3--estructura-del-proyecto)
4. [Quick start](#4--quick-start)
5. [Base de datos](#5--base-de-datos)
6. [Backend: arquitectura](#6--backend-arquitectura)
7. [Autenticación y permisos](#7--autenticación-y-permisos)
8. [Módulo por módulo](#8--módulo-por-módulo)
9. [Frontend: estructura](#9--frontend-estructura)
10. [Mapa de endpoints](#10--mapa-de-endpoints)
11. [Testing](#11--testing)
12. [Docker / producción](#12--docker--producción)
13. [Errores comunes](#13--errores-comunes)
14. [Cómo agregar un nuevo módulo](#14--cómo-agregar-un-nuevo-módulo)
15. [Glosario rápido de términos de negocio](#15--glosario-rápido-de-términos-de-negocio)
16. [Roadmap / estado por módulo](#16--roadmap--estado-por-módulo)

---

## 1. 📌 ¿Qué es YEIKAR?

YEIKAR es un sistema ERP (**Enterprise Resource Planning**) hecho a medida para
**Comercializadora YEIKAR**, una empresa de mueblería que fabrica y vende camas,
closets, comedores, salas, colchones y electrodomésticos. Opera entre
**Venezuela y Colombia**, por lo que el dinero se maneja en tres monedas:
**COP** (peso colombiano, la **moneda base / funcional**), **USD** y **VES**
(bolívares venezolanos).

El objetivo es reemplazar el caos de Excel por un sistema centralizado que
maneje, de punta a punta:

- Cotizaciones **paramétricas** de muebles a medida (precio calculado según
  ancho/largo + receta de materiales).
- Pedidos y conversión de cotización → pedido → producción.
- **Producción por etapas/áreas** (Ebanistería → Preparación → Pintura →
  Tapicería) con tablero **Kanban**.
- Inventario de materiales (**kardex**) y de productos terminados / de reventa.
- **Ventas, pagos/abonos** y cuentas por cobrar, con registro en **caja**.
- **Facturación fiscal venezolana** (SENIAT).
- **Nómina semanal por destajo**, catálogo de precios de producción por área y
  acumulación de **aguinaldo**.
- Gastos, tasas de cambio, reportes financieros (P&L, informe mensual) y
  saldos por cuenta/método de caja.
- Control de **acceso por módulo** por rol, y **auditoría** de cambios.

> **Estado actual (ago 2026):** backend + frontend 100 % funcionales y
> desplegados con Docker. Auth JWT con refresh rotatorio, Kanban de producción,
> caja contable, nómina, facturación fiscal, roles modulares y auditoría.

---

## 2. 🧰 Stack Tecnológico

### Backend

| Capa | Tecnología | Versión (`requirements.txt`) |
|------|-----------|------------------------------|
| Framework | FastAPI | 0.115.6 |
| Servidor ASGI | uvicorn[standard] | 0.34.0 |
| ORM | SQLAlchemy 2.0 (declarativo) | 2.0.36 |
| Migraciones | Alembic | 1.14.1 |
| Base de datos | PostgreSQL | 15+ |
| Driver | psycopg2-binary | 2.9.10 |
| Config | pydantic-settings + python-dotenv | 2.7.0 / 1.0.1 |
| Validación | Pydantic v2 | 2.10.4 |
| Auth | python-jose[cryptography] | 3.3.0 |
| Hash | passlib[bcrypt] + bcrypt | 1.7.4 / 4.2.0 |
| Form-urlencoded | python-multipart | 0.0.20 |
| Email | email-validator (EmailStr) | 2.3.0 |
| Tests | pytest + httpx | 8.3.4 / 0.28.1 |
| IA (histórico) | openai / google-genai | 1.59.7 / 1.0.0 |

> ⚠️ El Cotizador IA actual es **100 % manual** (sin llamadas a APIs de pago);
> `openai`/`google-genai` quedan en el `requirements.txt` por compatibilidad con
> el modo API anterior, pero ya **no** se usan.

### Frontend

| Capa | Tecnología | Versión (`package.json`) |
|------|-----------|--------------------------|
| Framework | React | 18.3.1 |
| Lenguaje | TypeScript (strict) | 5.5.3 |
| Bundler | Vite | 5.3.4 |
| Estilos | Tailwind CSS 3 | 3.4.4 |
| Router | react-router-dom **v7** | 7.17.0 |
| HTTP | axios | 1.17.0 |
| Gráficas | recharts | 3.8.1 |
| Animación | framer-motion | 13.0.0 |
| Iconos | lucide-react | 1.28.0 |
| PDF | jspdf + html2canvas | 4.2.1 / 1.4.1 |
| SEO | react-helmet-async | 3.0.0 |

---

## 3. 🗂️ Estructura del Proyecto

```
YEIKAR/
├── backend/                        ← API REST (FastAPI + Python)
│   ├── app/
│   │   ├── main.py                 # Crea la app FastAPI, registra TODOS los routers y los handlers de error globales
│   │   ├── core/                   # Lógica transversal (no módulo de negocio)
│   │   │   ├── config.py           # Settings: DATABASE_URL, SECRET_KEY, DEBUG, rate limit, etc.
│   │   │   ├── caja.py             # registrar_movimiento_caja(): el "cerebro" de la contabilidad de caja
│   │   │   ├── rate_limit.py       # Rate limit por IP en memoria (middleware)
│   │   │   ├── client_ip.py        # obtener_ip_cliente(): IP real del socket (anti-spoofing X-Forwarded-For)
│   │   │   └── state_machine.py    # Máquinas de estado: pedido, orden, etapa, envío (+ validar_transicion)
│   │   ├── db/
│   │   │   ├── session.py          # engine + session_local + get_db (pool 4+2, statement_timeout 30s)
│   │   │   └── base.py             # Base declarativa de SQLAlchemy (DeclarativeBase)
│   │   └── modules/<nombre>/       # Un paquete por módulo de negocio (ver sección 8)
│   │       ├── model.py            # Clases ORM → tablas
│   │       ├── schemas.py          # Pydantic: entrada/salida
│   │       ├── service.py          # Lógica de negocio
│   │       └── router.py           # Endpoints FastAPI (protegidos con require_module/get_current_user)
│   ├── alembic/                    # Migraciones de base de datos (versionado)
│   │   ├── env.py                  # IMPORTA todos los modelos (¡agregar los nuevos aquí!) y apunta el target_metadata
│   │   └── versions/               # 34 migraciones (cadena desde 8d0e6ee658f6 hasta h2i3j4k5l6m7)
│   ├── test/                       # Suite pytest (ver sección 11)
│   │   ├── conftest.py             # TestClient, tokens firmados, fixture cleaner + ORDEN_LIMPIEZA
│   │   └── test_*.py               # Ver sección 11
│   ├── scripts/                    # Scripts de importación de datos (Excel, sinónimos, estructuras)
│   ├── esquema.sql                 # Dump BASE de 32 tablas (pre-Alembic, junio 2026). Ya NO es la fuente principal
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile                  # ⚠️ Python 3.11-slim (ver nota gotcha)
├── frontend/                       # React + TS + Vite + Tailwind (ver sección 9)
│   ├── src/
│   │   ├── main.tsx                # Monta <App/> en #root
│   │   ├── App.tsx                 # Rutas + ROUTE_MODULES + PrivateRoute
│   │   ├── index.css               # Tailwind + paleta yeikar-* + fuentes
│   │   ├── components/Ui/*         # Kit de UI reutilizable (Button, Modal, DataTable…)
│   │   ├── components/Layout/*     # Sidebar, Navbar, DashboardLayout
│   │   ├── pages/*.tsx             # Una página por ruta (ver sección 9)
│   │   ├── services/*.ts           # Un servicio axios por módulo (api.ts, clienteService…)
│   │   ├── context/                # AuthContext (usuario + modulos + hasModulo) y ToastContext
│   │   └── utils/                  # format.ts (moneda), informePrintHtml.ts
│   ├── nginx.conf                  # SPA fallback, gzip, proxy /api → backend:8000, rate limit
│   ├── Dockerfile                  # Node 20 build → nginx:alpine
│   └── vite.config.ts              # Dev: /api → http://localhost:8000
├── docs/                           # Documentación del proyecto (esta guía está en docs/development/)
├── docker-compose.yml              # db + backend + frontend + backup (perfil) 
├── scripts/                        # (vacío por ahora)
├── infra/                          # (vacío por ahora)
├── backup_inventario_*.sql         # Backups puntuales del inventario
├── .env.example                    # Plantilla de variables para docker compose
└── README.md                       # Resumen ejecutivo
```

> **Patrón de módulos:** cada módulo de negocio tiene su `model.py`,
> `schemas.py`, `service.py`, `router.py`. Si entiendes uno, los entiendes
> todos.

> **Carpetas legacy/vacías (ignorar):** en `backend/app/modules/` existen
> `auth/`, `costs/`, `material/`, `payments/`, `ubicacion/` sin uso real (no
> registradas en `main.py`). En `frontend/src/` hay `features/`, `routes/`,
> `store/`, `hooks/`, `types/`, `app/` vacías (esqueleto). No usarlas: seguir
> el patrón de `pages/` + `services/`.

---

## 4. 🚀 Quick Start

### Requisitos

- Python 3.13+ (dev), PostgreSQL 15+ local o vía Docker, Node 18+ y npm.

### 4.1. Base de datos

```bash
# Opción A: Docker (recomendada en dev)
docker compose up -d db        # PostgreSQL en localhost:5432 (yeikar/yeikar123, db yeikar)

# Opción B: PostgreSQL local
sudo -u postgres psql -c "CREATE USER yeikar WITH PASSWORD 'yeikar123';"
sudo -u postgres psql -c "CREATE DATABASE yeikar OWNER yeikar;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE yeikar TO yeikar;"
```

### 4.2. Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # edita DATABASE_URL + SECRET_KEY (DEBUG=true en dev)

# --no-proxy-headers: NO confiar en X-Forwarded-For (anti-spoofing del rate
# limit y del lockout de login). En dev detrás de otro proxy, configura
# FORWARDED_ALLOW_IPS en .env en su lugar.
uvicorn app.main:app --reload --no-proxy-headers   # http://localhost:8000
```

- Swagger (`/docs`), ReDoc y `/openapi.json` **solo** están habilitados con
  `DEBUG=true`.
- Verificar conexión: `python -c "from app.db.session import engine; print('OK')"`.

### 4.3. Frontend (otra terminal)

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 — /api proxied → :8000
```

> `npm run build` ejecuta `tsc --noEmit` y luego `vite build` (typecheck estricto antes de empaquetar; en dev no hay typecheck separado).

### 4.4. Primeros datos

Si es una BD nueva, restaura el esquema base y aplica las migraciones (ver
sección 5.3). El usuario inicial se crea por SQL o por registro admin.

---

## 5. 🐘 Base de Datos

### 5.1. Resumen

- **Motor:** PostgreSQL 18 (imagen `postgres:18-alpine` en compose).
- **BD por defecto:** `yeikar` (usuario `yeikar` / `yeikar123`), definida en
  `backend/app/core/config.py` (`DATABASE_URL`).
- **Moneda base:** `COP` → `moneda.id = 1`. Todo lo que "no es COP" se expresa
  además en COP mediante `tasa_cambio` (COP por 1 unidad) y el campo
  `monto_en_moneda_base` (o `total_en_moneda_base`).
- **Fuente de verdad del esquema desde junio 2026:** **Alembic**. El dump
  `esquema.sql` (32 tablas) era el esquema original y **sigue sirviendo como
  base para una BD nueva**, pero cualquier cambio nuevo se hace **solo** como
  migración Alembic. Total actual: **~70 tablas** (32 base + ~37 creadas por
  migraciones).

### 5.2. Conexión (`app/db/session.py`)

```python
engine = create_engine(settings.DATABASE_URL,
    pool_size=4, max_overflow=2, pool_pre_ping=True, pool_timeout=5,
    connect_args={"options": "-c statement_timeout=30000"})
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

- `get_db()` es la dependencia FastAPI que provee la sesión y la cierra
  siempre. Un `TimeoutError` de la base se traduce a **503**.
- Varios servicios usan `with_for_update()` (bloqueo de fila) para serializar
  operaciones concurrentes sobre dinero/inventario (pagos, conversiones,
  consumos, finalización de órdenes).

### 5.3. Restaurar una BD desde cero

```bash
# 1. Crear usuario y BD (ver 4.1)

# 2. Cargar el esquema base (32 tablas originales)
psql -U postgres -d yeikar < backend/esquema.sql

# 3. Permisos (¡crítico! sin esto: "permission denied for table")
sudo -u postgres psql -d yeikar -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO yeikar;"
sudo -u postgres psql -d yeikar -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO yeikar;"

# 4. Aplicar las migraciones (el resto del esquema)
cd backend && source venv/bin/activate
alembic upgrade head
```

> ⚠️ El paso de `GRANT` es crítico: sin él la app falla con
> `permission denied for table`. En Docker la BD se crea sola con el usuario de
> compose (`DB_USER`/`DB_PASSWORD`), así que no hace falta este paso ahí.

### 5.4. Migraciones (Alembic)

```bash
cd backend && source venv/bin/activate
alembic revision --autogenerate -m "msg" && alembic upgrade head
```

- Primera migración: `8d0e6ee658f6_crear_detalle_cotizacion` (`down_revision = None`).
- Head actual: `h2i3j4k5l6m7_gasto_area_opcional` (verificar siempre con
  `alembic heads`).
- **Importante:** `alembic/env.py` tiene una **lista explícita de imports** de
  todos los `app.modules.*.model`. **Agregar cualquier modelo nuevo ahí**, o el
  autogenerate no lo detectará.
- Las migraciones no solo alteran el esquema: varias **siembran datos**
  (áreas de catálogo, `precio_produccion` con el LISTADO DE PRECIOS,
  `nomina_area_config`, permisos de módulo en `rol_modulo`, tasas de impuesto).

### 5.5. Tablas por grupo

| Grupo | Tablas |
|-------|--------|
| **Acceso y usuarios** | `usuario`, `usuario_rol`, `rol`, `rol_modulo`, `login_intento`, `refresh_token` |
| **Catálogos** | `area`, `cargo`, `tipo_producto`, `unidad_medida`, `moneda`, `ubicacion`, `tipo_gasto`, `tasa_impuesto` |
| **Maestros** | `cliente`, `proveedor`, `empleado`, `producto`, `material` |
| **Receta paramétrica** | `producto_material`, `regla_gasto_seccion`, `seccion_producto`, `elemento_seccion`, `politica_seccion`, `costo_produccion_seccion` |
| **IQE / atributos** | `mueble_atributos`, `cama_historica_atributos` (legacy), `material_sinonimo` |
| **Cotizaciones** | `cotizacion`, `detalle_cotizacion`, `cotizacion_detalle_material`, `cotizacion_analisis_ia`, `cotizacion_material_ajuste` |
| **Pedidos** | `pedido`, `detalle_pedido` |
| **Producción** | `orden_produccion`, `etapa_produccion`, `etapa_asignado_adicional`, `consumo_material`, `mano_obra`, `costo_produccion` |
| **Inventario** | `inventario`, `movimiento_inventario`, `producto_inventario`, `movimiento_producto_inventario` |
| **Compras** | `compra`, `detalle_compra` |
| **Ventas / cobros** | `venta`, `detalle_venta`, `pago` |
| **Facturación fiscal** | `factura`, `detalle_factura` |
| **Finanzas** | `gasto`, `tasa_cambio` |
| **Caja y reportes** | `metodo_caja`, `movimiento_caja`, `devolucion_venta`, `concepto_reporte`, `valor_concepto_mensual` |
| **Nómina** | `nomina`, `nomina_detalle`, `nomina_linea`, `nomina_concepto_vario`, `nomina_area_config`, `precio_produccion` |
| **Envíos** | `envio`, `envio_asignacion`, `envio_ubicacion` |
| **Auditoría** | `audit_event` |

### 5.6. Características del esquema

- Todos los modelos tienen `created_at`/`updated_at` (en los objetos
  SQLAlchemy modernos `updated_at` usa `onupdate`; los esquemas Pydantic de
  respuesta marcan estos campos como `Optional` para tolerar `NULL` inicial).
- Estados con valores permitidos definidos **en el backend** (con
  `validar_transicion` en `app/core/state_machine.py`) y en varios casos con
  `CHECK` en BD (p. ej. `cotizacion_estado_check`).
- Las FKs usan `ON DELETE` RESTRICT/CASCADE/SET NULL según el caso — se
  explota el handler global de `IntegrityError` de `main.py` para devolver 400
  en vez de 500.

---

## 6. ⚙️ Backend: Arquitectura

### 6.1. `app/main.py` — el cerebro del registro

`main.py` hace 4 cosas:

1. Importa **todos** los routers de módulos.
2. Crea `FastAPI(title="YEIKAR API", version="0.0.1", docs_url="/docs" si DEBUG)`.
3. Registra el **`RateLimitMiddleware`** y el **`CORSMiddleware`** (orígines de
   `ALLOWED_ORIGINS`, incluye `localhost:5173` por defecto).
4. **Registra los routers** con `app.include_router(...)` usando los prefijos
   exactos de la tabla de endpoints (sección 10). Este archivo es la fuente de
   verdad del mapa de rutas.

También registra dos manejadores globales de excepciones:

```python
@app.exception_handler(IntegrityError)   # CHECK/FK/UNIQUE → 400 con mensaje amigable
@app.exception_handler(DataError)        # desbordamiento/tipo inválido → 400
```

### 6.2. El patrón de módulo — ejemplo completo: Gastos

Para no repetir: el patrón es idéntico en **todos** los módulos. Tomemos
`gastos` como plantilla (es además el módulo más representativo del circuito
contable).

**`app/modules/gastos/model.py`** — tabla `gasto`:
```python
class Gasto(Base):
    __tablename__ = "gasto"
    id, tipo_gasto_id (FK), moneda_id (FK), area_id (FK opcional),
    fecha, descripcion, monto, tasa_cambio, monto_en_moneda_base,
    observaciones, creado_por_id, actualizado_por_id, created_at, updated_at
```

**`app/modules/gastos/schemas.py`** — Pydantic con `from_attributes = True` en
las respuestas (`GastoCreate`, `GastoUpdate`, `GastoResponse`).

**`app/modules/gastos/service.py`** — funciones clave:
- `_validar_fks(db, tipo_gasto_id, moneda_id)` → valida que existan.
- `_resolver_tasa(db, moneda, fecha, tasa)` → si es COP devuelve 1.0; si no
  usa la tasa dada o la vigente de `tasas_cambio`.
- `crear_gasto(db, gasto, usuario)` → crea el registro, y **si
  `metodo_caja_id` viene indicado, llama a
  `registrar_movimiento_caja(..., tipo="SALIDA", referencia=f"Gasto #{id}")`**
  → el efectivo **sale** de esa cuenta (egreso real, no fantasma).
- `actualizar_gasto` / `eliminar_gasto` → al eliminar, **borra también el
  movimiento de caja** con la referencia `Gasto #{id}` para no dejar egresos
  fantasma en el saldo.
- `_adjuntar_metodo_caja` → en las respuestas del listado adjunta el
  `metodo_caja_id/nombre` de cada gasto resolviéndolo desde su movimiento.

**`app/modules/gastos/router.py`**:
```python
router = APIRouter(prefix="/gastos", tags=["Gastos"],
                   dependencies=[Depends(require_module('gastos'))])
# POST /api/v1/gastos/   → crear_gasto
# GET  /api/v1/gastos/   → listar (filtros: tipo_gasto, categoria, area, fechas)
# GET  /api/v1/gastos/{id} · PUT /{id} · DELETE /{id}
```
Cada endpoint toma `current_user: Usuario = Depends(get_current_user)` y
envuelve en `try/except ValueError → HTTPException(400)`.

### 6.3. `app/core/` — herramientas transversales

| Archivo | Qué aporta |
|---------|-----------|
| `config.py` | `Settings()` con todas las variables. `_secret_key()`: en dev sin `SECRET_KEY` se genera una aleatoria por arranque; **en producción** una SECRET_KEY ausente/débil/corta aborta el arranque (fail-safe). |
| `caja.py` | **`registrar_movimiento_caja(db, *, metodo_caja_id|codigo, tipo, monto, moneda_id, tasa_cambio, fecha, referencia, ...)`** — crea `MovimientoCaja`, calcula `monto_en_moneda_base = monto × tasa`, y **crea la cuenta automáticamente** (`crear_cuenta_si_no_existe`) si se pasa un `codigo` (p. ej. `EFECTIVO_USD`). Exige `monto > 0`: la dirección del flujo se expresa con el `tipo` (`ENTRADA`/`SALIDA`/`APERTURA`/`AJUSTE`). Lo usan ventas, compras, gastos, devoluciones y nómina. |
| `rate_limit.py` | Middleware por IP (en memoria, por proceso) con `X-RateLimit-*` y 429 + `Retry-After`. Solo aplica a `/api/`. |
| `client_ip.py` | `obtener_ip_cliente()`: usa la IP real del socket; solo confía en `X-Forwarded-For` si el peer está en `FORWARDED_ALLOW_IPS`. Es lo que hace seguro el rate limit y el lockout de login. |
| `state_machine.py` | Matrices de transición legal de estados: `TRANSICIONES_PEDIDO` (COTIZADO→APROBADO→PRODUCCION→…→ENTREGADO), `TRANSICIONES_ORDEN_PRODUCCION`, `TRANSICIONES_ETAPA_PRODUCCION` (ASIGNADA→EN_PROCESO→PAUSADA/COMPLETADA), `TRANSICIONES_ENVIO` (PREPARADO→EN_TRANSITO→ENTREGADO/FALLIDO). `validar_transicion()` lanza un `ValueError` legible ("Estado X es terminal", "Transición no permitida…") que el router convierte en 400. |

### 6.4. `app/db/`

- `base.py` → `Base(DeclarativeBase)` compartida por **todos** los modelos.
- `session.py` → engine/session local/`get_db` (ver 5.2).

### 6.5. Auditoría transversal

`app/modules/auditoria/service.py` expone **`record_event(db, *, actor, action,
entity_type, entity_id, before, after, request)`**. Los servicios de negocio lo
llaman en cada CREATE/UPDATE/DELETE/STATE_CHANGE (¿quién cambió qué y cuándo),
y el módulo `auditoria` expone `GET /api/v1/auditoria/` (solo
Dueño/Administrador) para leer `audit_event`.

---

## 7. 🔐 Autenticación y Permisos

### 7.1. Flujo JWT + refresh con rotación

1. `POST /api/auth/login` (form-urlencoded, OAuth2) verifica la contraseña
   contra el hash bcrypt y devuelve `{access_token, token_type, refresh_token}`.
   El **access token** vive `ACCESS_TOKEN_EXPIRE_MINUTES` (30) con
   `{"sub": nombre_usuario, "type": "access", "jti": uuid}`. El **refresh
   token** vive `REFRESH_TOKEN_EXPIRE_DAYS` (7) con `"type": "refresh"`.
2. En cada petición protegida el cliente manda
   `Authorization: Bearer <access_token>`.
3. `POST /api/auth/refresh` recibe el refresh, **lo revoca** (rotación) mediante
   su hash en `refresh_token` (con `FOR UPDATE` para serialización y safe
   contra replay), y emite un **nuevo par**. El access/login con un token
   `type != "access"` es rechazado (401) → no se puede usar un refresh como
   access.
4. En el frontend, `api.ts` maneja el 401 → refresh → reintento transparente
   (ver sección 9.4).

### 7.2. `get_current_user` (`app/modules/users/deps.py`)

La pieza clave de toda la protección:

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token=Depends(oauth2_scheme), db=Depends(get_db)) -> Usuario:
    # 1. Decodifica el JWT con settings.SECRET_KEY y settings.ALGORITHM
    # 2. Requiere que "sub" exista y "type" == "access"
    # 3. Busca el usuario por nombre (case-insensitive) y exige que exista y esté activo
    #    → si falla: HTTP 401 "No se pudieron validar las credenciales"
```

> Todos los routers la importan (`from app.modules.users.router import
> get_current_user` — `users/router.py` la re-exporta desde `deps.py`) y la
> usan como `current_user: Usuario = Depends(get_current_user)`.

### 7.3. Permisos por módulo

- **`MODULOS_CATALOGO`** (en `deps.py`) es el catálogo central de módulos
  (clave → nombre → descripción). La clave es lo que se guarda en `rol_modulo`
  y lo que piden los guards. Módulos: `dashboard, clientes, cotizaciones,
  cotizaciones_ia, pedidos, ventas, facturacion, produccion, inventario,
  envios, productos, materiales, proveedores, empleados, gastos, cuentas,
  compras, costos_produccion, nomina, reportes, tasas, catalogos, usuarios`.
- **`ROL_MODULO`**: tabla `rol_modulo(rol_id, modulo, gestionar)`.
  `gestionar=False` → solo lectura (GET); `True` → lectura+escritura.
- **`ROLES_SUPER = ("Dueño", "Administrador")`**: acceso total a TODO sin
  necesitar filas en `rol_modulo`. `es_admin_user()` lo detecta por el nombre
  del rol.
- **`MODULOS_LECTURA_COMPARTIDA = {clientes, productos, materiales, tasas,
  catalogos}`**: catálogos operativos que cualquier usuario con sesión puede
  **consultar** (para trabajar en otros módulos), aunque su mutación exige el
  permiso de gestión.

**`require_module(modulo, solo_escritura=False)`** es la dependencia reutilizable
en cada router:

```python
router = APIRouter(prefix="/gastos", dependencies=[Depends(require_module('gastos'))])
```

- GET/HEAD/OPTIONS → basta tener el módulo (o ser superusuario).
- `solo_escritura=True` → las lecturas solo exigen estar autenticado.
- POST/PUT/DELETE → exige `gestionar=True`; si no → **403** con mensaje claro.
- Superusuario pasa siempre.

Otras piezas: `es_admin()` (endpoints solo Dueño/Administrador), y
`filtrar_registros_propios(query, columna, usuario)` para **alcance por fila**
(usuarios no administradores solo ven/operan sus propios registros).

### 7.4. Cómo otorgar un módulo a un rol (sin SQL)

Desde el panel **Usuarios** (`/usuarios`), rol → "privilegios":

- `GET /api/auth/modulos` → catálogo de módulos.
- `GET /api/auth/roles/{rol_id}/permisos` → estado actual de cada módulo.
- `PUT /api/auth/roles/{rol_id}/permisos` con
  `{"permisos": [{"modulo": "gastos", "gestionar": true}, ...]}` → guarda y
  reemplaza los accesos del rol (`guardar_permisos_rol` en `deps.py`).

### 7.5. En el frontend

- `GET /api/auth/me` (tras login) devuelve el usuario + `modulos:
  [{modulo, gestionar}]` (+ roles). `AuthContext` (ver 9.5) los guarda en
  memoria.
- `hasModulo(modulo, gestionar?)` → si el usuario tiene el módulo (y opcionalmente
  si puede gestionarlo).
- `esAdmin` → si algún rol es "Dueño"/"Administrador".
- El `ROUTE_MODULES` de `App.tsx` y el filtro del `Sidebar` usan `hasModulo`
  para ocultar rutas/menús; el backend **siempre** es la autoridad final.

---

## 8. 📦 Módulo por Módulo

> Notación: **tablas → funciones clave del service → endpoints (ver sección 10
> para la lista completa) → lógica de negocio destacada.**

### 8.1. `users` (Auth / Acceso)

- **Tablas:** `usuario`, `usuario_rol`, `login_intento`, `refresh_token`.
- **Key fields (Usuario):** `empleado_id` (opcional), `nombre_usuario` (único,
  ci), `email`, `password_hash`, `activo`, `ultimo_acceso`, relación many2many
  con `rol`.
- **Service:** `verificar_password`, `obtener_password_hash`, `crear_usuario`
  (único por nombre y email), `autenticar_usuario` (usa un **DUMMY_HASH** para
  igualar tiempos cuando el usuario no existe → anti-enumeración),
  `crear_token_acceso` (añade `jti` aleatorio), `registrar_intento`,
  `usuario_bloqueado` (anti-brute-force: fallos por cuenta+IP, tope por IP y
  detección de **≥3 IPs distintas** sobre la misma cuenta), `guardar_refresh_token`
  (hash sha256 en BD), `rotar_refresh_token` (con `FOR UPDATE`, revoca el usado),
  `revocar_tokens_usuario`.
- **Endpoints:** login (público), refresh (público), register y todo el CRUD de
  usuarios/roles/permisos (**solo Dueño/Administrador**). Protecciones extras:
  no puedes desactivar/eliminar tu propia cuenta (400).
- **Lógica destacada:** el correo usa `EmailStr` de Pydantic (valida TLD reales).

### 8.2. `catalogos` (Catálogos)

- **Módulo frontend:** `/catalogos` (lectura compartida; escritura con
  `solo_escritura=True`).
- **Tablas:** `area`, `cargo`, `tipo_producto`, `unidad_medida`, `moneda`,
  `ubicacion`, `tipo_gasto`, `rol`, `rol_modulo`.
- **Valores típicos:** `area`: Ebanistería, Preparación, Pintura, Tapicería
  (también terminación/vidriería en recetas); `moneda`: COP (id 1), USD (2),
  VES (3); `ubicacion.tipo`: DEPOSITO/TALLER/PUNTO_VENTA.
- **CRUD genérico** en `/api/v1/catalogos/{tipo}/…` para cada catálogo.

### 8.3. `clients`, `proveedores`, `empleados` (Maestros)

- **Tablas:** `cliente` (teléfono NOT NULL), `proveedor`, `empleado`.
- `empleado` además trae los campos de nómina: `en_nomina` (bool), `tipo_pago`
  (`DESTAJO`/`FIJO`), `sueldo_semanal`, `saldo_aguinaldo`, `porcentaje_aguinaldo`
  (opcional, sobrescribe el % del área), `cargo_id`.
- **CRUD estándar** en `/api/v1/cliente`, `/api/v1/proveedor`, `/api/v1/empleado`.

### 8.4. `productos` (Productos, Materiales y **motores de costeo**)

Dos estructuras de receta **paralelas** (cuidado: ambas conviven en el costeo):

1. **`ProductoMaterial` (receta plana paramétrica)** — filas
   `(producto_id, material_id, cantidad_base, tipo_escala, seccion,
   condicion_activacion, rangos, distancia_pauta_cm, tornillos_por_pieza,
   formula_personalizada, es_fijo_override)`. El campo `seccion` guarda el área
   (`EBANISTERIA`, `TAPICERIA`, `PINTURA`, `NOCHEROS`, `MANO_DE_OBRA`, …).
   - `tipo_escala`: **FIJO** (no escala), **LINEAL** (∝ largo), **AREA**
     (∝ ancho×largo), **ESPACIADO** (∝ perímetro/distancias de tornillos),
     **POR_RANGO** (saltos discretos JSON), **FORMULA** (reservado → usa base).
2. **`SeccionProducto` → `ElementoSeccion` (receta jerárquica por secciones)** —
   cada sección tiene sus insumos, su `PoliticaSeccion` (mano_de_obra_base,
   `pct_liquidacion_mo`, `pct_gastos_seccion`, `costo_fabricacion`,
   `pct_trabajadores`, `pct_negocio`) y N `CostoProduccionSeccion`
   (PREPARADO CAMA, PINTURA CAMA… con costo_base + %).

Además: `ReglaGastoSeccion` (% de gasto indirecto por sección) y en `Producto`
los precios del Excel histórico: `precio_costo_base`, `precio_venta_base`,
`precio_venta_con_iva`, `ancho_base`/`largo_base`, `es_reventa`.

**`cost_service.py — calcular_costo_producto(...)`** es el cerebro del costeo.
Reglas de precio YEIKAR:

```
a = costo_producción × (1 + impuesto%)      # impuesto_porcentaje default 7%
b = a × (1 + ganancia%)                     # ganancia default 40%
precio_con_iva = b × (1 + iva%)             # IVA default 0% (muebles en Colombia)
```

- Si hay receta **y** las dimensiones pedidas son iguales a las base → usa
  `precio_costo_base` del Excel como **fuente de verdad** directa.
- Si las dimensiones difieren y hay `precio_costo_base` → **escala por área**.
- Si no hay Excel → suma por sección con sus % de gasto (o la receta plana con
  mano de obra `pct_mano_obra` 15% y gastos `pct_gastos` 10%).
- La respuesta es un dict con **muchos alias** (`materiales_detalle`,
  `costo_total`, `precio_sugerido`, `costo_gastos_indirectos`, `precio_venta`…)
  para que el frontend siempre encuentre los campos (los históricos fixes de
  `NaN` dependen de esto).

**Endpoints destacados** (en `/api/v1/producto/…`): CRUD, `GET|POST
/producto/{id}/calcular-precio` (costeo paramétrico), CRUD de receta
`/producto/{id}/receta`, receta estructurada `/receta-estructurada`, secciones,
elementos, políticas, costos de producción por sección y
`POST /recalculate-custom-recipe`.

### 8.5. `quotes` (Cotizaciones + IQE)

- **Tablas:** `cotizacion`, `detalle_cotizacion` (con `costo_materiales`,
  `costo_mano_obra`, `costo_gastos`, `costo_total`, `receta_personalizada`
  JSON), `cotizacion_detalle_material` (receta editable por cotización),
  `cotizacion_analisis_ia`, `cotizacion_material_ajuste`, y en `productos` las
  de atributos.
- **Service:** `crear_cotizacion` (guarda la cabecera + detalles, y convierte
  totales a moneda base), `_validar_consistencia_detalles` (una cotización en
  moneda extranjera debe cuadrar sus precios de detalle con el total — evita
  mandar COP como USD creyendo que es USD), filtros históricos con
  `solo_mes_actual`/`mes`/`anio`, `eliminar_cotizacion` (rechaza si ya hay un
  `pedido` asociado → 400).
- **Estado:** `BORRADOR, ENVIADA, APROBADA, RECHAZADA, VENCIDA` (mayúsculas en
  BD; el front debe mandar mayúsculas).

**Cotizador Inteligente (IQE)** — `intelligent_router.py`, prefix
`/api/v1/intelligent-quotation`. **100 % manual, sin APIs de pago**:
1. `GET /contexto-exportar` → arma el **paquete** (inventario con costos +
   receta de un producto similar + reglas de costeo + `ESQUEMA_JSON`) listo
   para pegar en una IA de navegador (ChatGPT/Gemini/Claude) junto con la foto.
2. `POST /import-structure` → la IA devuelve JSON
   (`estructura_propuesta`), el ERP lo matchea con inventario (fuzzy +
   `material_sinonimo`) y arma la estructura con **precios vigentes**.
3. `POST /recalculate-structure` → recálculo tras ediciones.
4. `POST /finalize-structure` → guarda como **Cotización** o como **Producto**
   nuevo (con receta y vector de similitud).
Filosofía: **"La IA interpreta, el ERP calcula, el vendedor decide"**. No
existen ya los endpoints de visión (analyze-image/find-similar eran del modo
API previo; `vision_provider.py` fue eliminado y sus modelos viven en
`quotes/atributos.py`).

### 8.6. `orders` (Pedidos y conversión de cotización)

- **Tablas:** `pedido` (único por `cotizacion_id`), `detalle_pedido` (guarda
  snapshot de `costo_unitario`, `porcentaje_ganancia` y dimensiones/color/
  acabado).
- **Service:**
  - `crear_pedido`, `actualizar_pedido` — si el pedido pasa a **PRODUCCION**,
    genera automáticamente (misma transacción) una `OrdenProduccion` por
    detalle (`estado=EN_PRODUCCION`). Si pasa de PRODUCCION a TERMINADO
    manualmente, exige que **todas** las órdenes estén FINALIZADA. Usa
    `validar_transicion(TRANSICIONES_PEDIDO, ...)`.
  - **`convertir_cotizacion_a_pedido`** — la joya del flujo: con `FOR UPDATE`
    (idempotente), valida estados (no RECHAZADA/VENCIDA), valida que los
    detalles de pedido **coincidan exactamente** con los cotizados, maneja el
    **adelanto opcional** (deriva la tasa del abono con `_derivar_tasa_pago` o
    exige `tasa_cambio_adelanto`), marca la cotización `APROBADA`, crea el
    pedido + detalles, **crea la venta automática** (en la moneda de la
    cotización, con `commit=False`) y registra el adelanto como **primer pago**
    — todo en una sola transacción atómica.
- **Endpoints:** CRUD + `POST /api/v1/pedido/convertir/{id_cotizacion}`
  (⚠️ la ruta histórica era `/desde-cotizacion/{id}`, ya no existe).

### 8.7. `production` (Órdenes, Etapas/Kanban, Consumos, Mano de obra, Costo)

- **Tablas:** `orden_produccion` (única por `detalle_pedido_id`),
  `etapa_produccion` (área + empleado responsable + estado + fechas),
  `etapa_asignado_adicional` (multi-empleado), `consumo_material` (congela
  `costo_unitario`), `mano_obra` (monto + `porcentaje_recargo` + `pagado`),
  `costo_produccion` (único por orden).
- **Máquina de estados:** orden `PENDIENTE → EN_PRODUCCION → PAUSADA →
  FINALIZADA / CANCELADA`; etapa `ASIGNADA → EN_PROCESO → PAUSADA/COMPLETADA`
  (véase `state_machine.py`).
- **Service:**
  - `crear_etapa_produccion`: rechaza **dos etapas activas de la misma área**
    (el retrabajo se modela con pasar-a-area) y pasa la orden `PENDIENTE →
    EN_PRODUCCION` al crear la primera etapa.
  - `cambiar_estado_orden_produccion`: al pasar a **FINALIZADA** exige que
    exista ≥1 etapa y que **todas** estén `COMPLETADA`, calcula y guarda el
    costo si no existe, y **sincroniza el pedido**: si todas las líneas del
    pedido tienen su orden FINALIZADA → pedido = TERMINADO y se crea el envío
    automático (`crear_envio_automatico`).
  - `crear_consumo_material`: exige etapa `EN_PROCESO`, descuenta inventario
    (ubicación "Depósito Principal"), y si existe el tipo de gasto "Consumo de
    Materia Prima en Producción" genera un **gasto automático** (COP). Al
    eliminar el consumo se repone stock y se borra el gasto.
  - `calcular_y_guardar_costo`: materiales = Σ cantidad×costo_unitario
    (congelado), mano de obra = Σ monto×(1+recargo), + gastos + ganancia.
  - `obtener_referencia_receta`: receta del producto de la etapa (para el modal
    del Kanban).
  - Endpoints extra del Kanban: `POST /etapa/{id}/pasar-a-area` (completa la
    etapa actual y crea una nueva en el área destino, con responsables
    adicionales), `referencia-receta`, `PUT /mano-obra/{id}/pagar`.

### 8.8. `inventory` (Materiales + Productos de reventa)

- **Tablas:** `inventario` (stock por `material_id`×`ubicacion_id` con unique),
  `movimiento_inventario` (kardex: ENTRADA/SALIDA/AJUSTE/DAÑO/DEVOLUCION,
  `referencia_tipo`/`referencia_id`), `producto_inventario` (stock de
  productos terminados/reventa con `costo_promedio`), `movimiento_producto_inventario`.
- **Service:** `registrar_movimiento` — `FOR UPDATE` sobre la fila de
  inventario, crea la fila si no existe (con savepoint y captura del
  IntegrityError del unique para no duplicar en carreras), descuenta/agrega
  según tipo, valida stock, actualiza `material.costo_base` con el costo de la
  entrada, y hace **flush (no commit)** porque el caller (compra/producción)
  commitea al final. `registrar_movimiento_producto` igual para productos con
  costo promedio.

### 8.9. `purchases` (Compras)

- **Tablas:** `compra` (estado BORRADOR/EMITIDA/RECIBIDA/CANCELADA, `tipo_pago`
  CONTADO/CREDITO, `metodo_caja_id`, `total_en_moneda_base`), `detalle_compra`.
- **Service:** `crear_compra` — si estado `RECIBIDA` dispara la **entrada de
  stock** (por cada material) y actualiza `material.costo_base` al instante con
  el último precio de compra; si `tipo_pago=CONTADO` registra la **SALIDA de
  caja** (`_movimiento_caja_compra` → `movimiento_caja` con referencia
  `Compra #{id}`). `actualizar_compra` — al entrar o salir de RECIBIDA registra
  la entrada o la **reversa** de stock/caja (neto, idempotente, sin dejar
  egresos fantasma).

### 8.10. `sales` (Ventas/Facturas + Pagos) y la conexión con caja

- **Tablas:** `venta` (única por `pedido_id`; `total`, `moneda_id`,
  `tasa_cambio`, `total_en_moneda_base`; estados PENDIENTE/ABONADA/PAGADA/
  ANULADA/CANCELADA), `detalle_venta` (snapshot de `costo_unitario`,
  `porcentaje_ganancia`, `utilidad`, `descuento`), `pago`.
- **Service:**
  - `crear_venta_desde_pedido` — exige pedido facturable (`APROBADO,
    PRODUCCION, TERMINADO, ENTREGADO` — y COTIZADO solo en la conversión
    automática), una sola venta por pedido, **moneda = moneda de la
    cotización** (los precios del pedido están fijados en ella), tasa congelada
    de la cotización, y descuenta stock de productos **`es_reventa`** al
    facturar. Costo del detalle convertido a la moneda de la venta para que el
    margen sea coherente.
  - `crear_pago` — `FOR UPDATE` sobre la venta (pagos concurrentes
    serializados), valida método↔moneda (`EFECTIVO_COP/BANCOLOMBIA=COP`,
    `EFECTIVO_USD/ZELLE=USD`, `EFECTIVO_VES/BANCARIBE=VES`), tasa mínima, no
    sobrepasar el saldo, y **registra la ENTRADA de caja** del método de pago
    (`_registrar_movimiento_caja_pago` — crea la cuenta si falta, vincula
    `pago_id` para poder limpiar/evitar duplicados). Recalcula el estado de la
    venta: PAGADA si está cubierta, ABONADA si está parcial.
  - `get_cuentas_por_cobrar` para el reporte de saldos.
  - `eliminar_venta` rechaza ventas con pagos (hay que anular primero).
- **La conexión con caja (concepto clave):** un **pago = ENTRADA** en la cuenta
  del método de pago; un **gasto/compras contado/nómina/devolución = SALIDA**.
  Todo pasa por `app/core/caja.py`. Ver sección 8.14.

### 8.11. `facturacion` (Factura fiscal SENIAT)

- **Separación conceptual:** la **`venta`** es el flujo de dinero (cobros); la
  **`factura`** es el documento fiscal. Independientes: se factura un pedido
  **pagado al 100 %** (su venta `PAGADA`), en **USD** con los precios por línea
  que decide la dueña, y se convierte a **bolívares (Bs)** con
  `tasa_usd_ves`.
- **Tablas:** `factura` (total_usd, tasa_usd_ves, base_imponible_bs, iva_bs,
  igtf_bs, total_bs, estado EMITIDA/ANULADA; **sin UNIQUE** por pedido porque
  tras anular se puede re-facturar), `detalle_factura` (por `detalle_pedido.id`,
  `precio_usd`, subtotales), `tasa_impuesto` (IVA e IGTF configurables).
- **Service:** `calcular_impuestos` (IVA sobre base; IGTF sobre el total con
  IVA), `crear_factura_desde_pedido`, `pedidos_facturables`, `anular_factura`,
  tasas de impuesto. Puede existir `FacturaNoAutorizadaError` si se intenta
  facturar con saldo pendiente (solo Dueño/Admin autorizan).

### 8.12. `gastos` — ver ejemplo completo en 6.2

- Registra egresos con **salida de caja** opcional (si `metodo_caja_id`) e
  imputación opcional a un **área** (`area_id`). Al eliminar, revierte el
  movimiento de caja. El `TipoGasto` tiene `categoria` OPERATIVO/PASIVO/
  PRODUCCION/ADMINISTRATIVO/FINANCIERO/IMPUESTO (la categoría agrupa el informe
  mensual). La nómina crea gastos automáticos tipo "NÓMINA SEMANAL".

### 8.13. `tasas_cambio` (TRM)

- **Tabla:** `tasa_cambio(moneda_origen_id, moneda_destino_id, fecha, valor)`
  (única por par+fecha).
- **Service:** `obtener_tasa_moneda_a_cop(db, moneda_id, fecha)` → tasa del día
  o la más reciente anterior (para COP = 1.0; si no hay tasa = 1.0). Endpoints:
  `GET /api/v1/tasa/convertir` y CRUD bajo `/api/v1/tasa/tasas-cambio/`.

### 8.14. `reports` (Reportes financieros + **sistema de caja**)

**Modelos:** `concepto_reporte` + `valor_concepto_mensual` (informe mensual
configurable), **`metodo_caja`** (cuenta catalogo: `nombre`, `codigo` único,
`activo`, `orden`) y **`movimiento_caja`** (la bitácora contable), y
`devolucion_venta`.

**El sistema de caja — cómo se mueve cada peso:**
- `app/core/caja.py::registrar_movimiento_caja(...)` es el punto único de
  entrada. Tipos: **APERTURA / ENTRADA / SALIDA / AJUSTE**. Guarda `monto`,
  `moneda_id`, `tasa_cambio` y `monto_en_moneda_base` (su valor en COP).
- **Al crear una cuenta** (`crear_metodo_caja` → `crear_cuenta` en el CRUD) se
  registra una **APERTURA de 1.000.000 COP** por defecto ("milón" de saldo
  inicial) — migración `e2d4c6a8b1f3` y código en `reports/service.py`.
- Cada cobro de venta → `ENTRADA`; cada gasto con cuenta / compra contado /
  nómina / devolución → `SALIDA`; se referencia al registro origen
  (`referencia="Pago #N"`, `"Gasto #N"`, `"Compra #N"`) para poder revertirlo.
- **`resumen_cuentas`** (service) → saldo por cuenta desglosado por moneda y
  total en COP. Convención: `APERTURA/ENTRADA/AJUSTE` suman, `SALIDA` resta
  (un `AJUSTE` puede traer monto negativo).
- Endpoints: `/api/v1/cuenta/resumen`, CRUD de `metodo_caja` y de
  `movimiento_caja`, y `POST /cuenta/{metodo_id}/movimiento`.

**Reportes (`/api/v1/reports/`, solo Dueño/Admin):**
- `GET /pnl?mes=YYYY-MM` → P&L **agrupado por moneda** con equivalentes COP.
  Egresos = Gastos generales + Compras `RECIBIDA` + Mano de obra `pagado=True`
  (la MO se paga SIEMPRE en COP). Ingresos = Pagos del mes (con su
  `monto_en_moneda_base` congelado).
- `GET /informe-mensual?mes=YYYY-MM` → el informe completo: **Control Interno
  de Ingresos** (líneas de venta con costo/ganancia/descuento + devoluciones
  como líneas negativas), **Resumen del mes** (ingresos − egresos =
  disponible), **Estado de Resultados** (ventas contado/crédito, inventarios
  inicial u/final desde `concepto_reporte`, compras, gastos por categoría) y
  **Pendientes de pago** al cierre. Nota: los saldos de caja se exponen aparte
  (`saldos_caja`) y **NO** se suman a inventarios finales (había fabricado
  utilidad ficticia).
- `GET /rentabilidad-producto` → margen = precio promedio de venta − costo
  promedio de producción (de órdenes FINALIZADA, `CostoProduccion.costo_total`).
- `GET /alertas-stock?umbral=`.
- **`GET /diario?fecha=YYYY-MM-DD`** (`service.resumen_diario`) → **Estado del
  día**: saldo inicial por cuenta (COP acumulado antes de la fecha), ingresos y
  egresos del día (por moneda y COP), saldo final, y cada movimiento
  enriquecido con **concepto legible** ("Gasto: {tipo} — {descripción}",
  "Pago venta #N — {cliente}", "Nómina semanal", "Compra") y **quién** lo hizo
  (`movimiento_caja.usuario_id`, que los pagos de venta ahora registran). La UI
  es la página `/reporte-diario` ("Estado del día") + un widget "Hoy" en el
  Dashboard (solo Dueño/Admin).
- CRUD de `conceptos`, `valores-mensuales` y `devoluciones` (una devolución
  **reembolsa caja** por el último método de pago usado).

### 8.15. `dashboard`

- `GET /api/v1/dashboard/metrics` → pedidos activos, órdenes de producción
  activas, alertas de stock (umbral 5), e ingresos del mes por moneda. Respeta
  el alcance por fila del usuario.
- Filtro por módulo `dashboard` (siempre accesible por salida de acceso).

### 8.16. `envios` (Despachos)

- **Tablas:** `envio` (único por pedido; estados PREPARADO/EN_TRANSITO/ENTREGADO/
  FALLIDO), `envio_asignacion` (historial de asignación/desasignación de
  empleados), `envio_ubicacion` (GPS: lat/lng, precisión, velocidad, rumbo,
  fuente web/móvil).
- **Service:** `crear_envio_automatico` (llamado por producción cuando el
  pedido termina), `_scope_envios` (un usuario con `empleado_id` solo ve sus
  envíos asignados; Dueño/Admin ve todo), `registrar_ubicacion` (el repartidor
  reporta su posición). Los drivers reciben un DTO **recortado**
  (`EnvioRepartoResponse`) vs Dueño/Admin que ven el detalle operativo.
- `GET /api/v1/envio/mis-asignaciones` es exclusivo de repartidores asignados.

### 8.17. `costos_produccion` (Catálogo de precios de producción) — NUEVO (ago 2026)

- **Tabla:** `precio_produccion(area_id, descripcion, producto_id opcional,
  precio, activo, orden)` — el catálogo del **"LISTADO DE PRECIOS Y CATEGORÍAS
  DE MUEBLES"**: el valor que suma cada pieza fabricada al empleado que la
  hizo (la **base de la nómina por destajo**).
- La migración `f5c6d7e8f9a0` además: crea el área **"Preparación"**, siembra
  los ~200 precios por área (Ebanistería / Preparación / Pintura / Tapicería) y
  otorga el módulo `costos_produccion` (gestionar) a **Dueño, Administrador y
  Producción**.
- **Endpoints:** CRUD en `/api/v1/costo-produccion/` (listar con filtros
  `area_id`, `buscar` por descripción, `activo`).

### 8.18. `nomina` (Nómina semanal por destajo) — NUEVO (ago 2026)

**Tablas:** `nomina` (periodo, estado BORRADOR/PAGADA/ANULADA, total),
`nomina_detalle` (bloque por empleado: `tipo_pago`, `total_produccion`,
`bono_aguinaldo`, `monto_a_pagar`, `metodo_caja_id`, `gasto_id`),
`nomina_linea` (origen `ETAPA`|`MANUAL`, producto, área, cliente, cantidad,
precio_unitario, total), `nomina_concepto_vario` (CARMEN MANILLAS, ALMUERZOS…),
`nomina_area_config` (área → `porcentaje_aguinaldo`, seeded: **Ebanistería 8 %,
Preparación/Pintura/Tapicería 5 %**).

**Algoritmo de generación (`generar_nomina`, `app/modules/nomina/service.py`):**

```
1. Empleados en nómina (en_nomina=True, activo=True), ordenados por cargo.
2. Etapas COMPLETADAS del periodo (fecha_fin dentro de [desde, hasta]) con
   su orden→detalle→producto y pedido→cliente.
3. Para CADA etapa, si el responsable está en nómina y es DESTAJO:
     precio = PrecioProduccion[(area_id, producto_id)] (activo)  *si no: 0
     total  = precio × cantidad (cantidad = detalle_pedido.cantidad)
     → una NominaLinea (origen=ETAPA) agrupada por empleado.
4. Por empleado (regla de pago):
     - Empleado FIJO → entra con su SUELDO_SEMANAL como una línea "NOMINA SEMANA".
     - Empleado DESTAJO → monto_a_pagar = Σ líneas de producción.
     - bono_aguinaldo (solo DESTAJO) = Σ (línea.total × %área / 100),
       o bien total_produccion × empleado.porcentaje_aguinaldo/100 si el
       empleado tiene % propio (sobrescribe).
     - total_nomina = Σ montos + conceptos varios.
```

**Extras añadidos (post-escritura de este doc, ago 2026):**
- **Guarda de semana duplicada**: `crear_nomina` rechaza (400) si ya existe
  una nómina BORRADOR/PAGADA para el mismo periodo.
- **`POST /api/v1/nomina/aguinaldo/pagar`** (`pagar_aguinaldo`): entrega el
  bono acumulado — crea un gasto **"AGUINALDO ANUAL"** (descuenta la cuenta y
  aparece como egreso) y **resetea `empleado.saldo_aguinaldo` a 0**. Rechaza
  con 400 si el empleado no tiene saldo.

**Pago (`pagar_nomina`)** — por cada detalle con `monto_a_pagar > 0` (y
`metodo_caja_id` obligatorio):
1. Crea un **Gasto** automático tipo "NÓMINA SEMANAL" (categoría OPERATIVO)
   por empleado → eso dispara la **SALIDA de caja** de su cuenta.
2. Guarda `detalle.gasto_id`.
3. **Acumula el aguinaldo**: `empleado.saldo_aguinaldo += bono_aguinaldo`.
4. Marca la nómina `PAGADA`.

**Anulación (`anular_nomina`)** — revierte: resta el `bono_aguinaldo` del saldo
del empleado y `eliminar_gasto` de cada detalle (lo que revierte la salida de
caja), y marca la nómina `ANULADA`.

**Endpoints (`/api/v1/nomina`):** config de áreas (lista/update), `POST /generar`
(draft sin guardar), CRUD, `GET /saldos-aguinaldo` (saldo por empleado),
edición del borrador (detalle, líneas manuales, conceptos varios — solo en
`BORRADOR`), `POST /{id}/pagar`, `POST /{id}/anular`.

### 8.19. `auditoria`

- **Tabla:** `audit_event` (actor, action CREATE/UPDATE/DELETE/STATE_CHANGE,
  entity_type/id, before/after JSON, changed_fields, ip, user_agent).
- `record_event(...)` se llama desde los services (ver 6.5). Solo
  Dueño/Administrador leen `GET /api/v1/auditoria/` (filtros facultativos).

---

## 9. 🖥️ Frontend — Estructura y Convenciones

### 9.1. Rutas y permisos (`src/App.tsx`)

- `ROUTE_MODULES: Record<ruta, clave>` mapea cada ruta a la clave del catálogo
  de módulos del backend (`/gastos → 'gastos'`, `/cuentas → 'cuentas'`,
  `/costos-produccion → 'costos_produccion'`, `/nomina → 'nomina'`,
  `/auditoria → 'usuarios'`, ...).
- Cada ruta se registra como
  `<Route path="/x" element={<PrivateRoute><DashboardLayout>…</DashboardLayout></PrivateRoute>} />`.
- **`PrivateRoute`** (definido en `App.tsx`): sin token → `/login`; mientras
  `loading` muestra spinner; si no hay `user` → `/login`; si el módulo de la
  ruta no lo tiene `hasModulo` → redirige a `/dashboard`; y `/reportes`
  adicionalmente exige `esAdmin`.
- `pageMeta` define título/descripción SEO por ruta (react-helmet-async).

### 9.2. Layout

- `components/Layout/DashboardLayout.tsx` → `<Sidebar/>` + `<Navbar/>` +
  contenedor `premium-grid` con transición framer-motion por ruta.
- `Sidebar.tsx` → **grupos de menú** (Resumen / Operación / Finanzas /
  Administración). Cada `MenuItem` trae `module` (clave) y la visibilidad se
  decide con `hasModulo(item.module)` (y `esAdmin` para Reportes). NO hay
  `rolePaths` hardcodeado: es **100 % por módulo** vía `/me`.
- `Navbar.tsx` → título de la página, botón de menú móvil, buscador (visual),
  fecha y badge "Sistema en línea". **No existe toggle de modo oscuro** (el
  tema es fijo, paleta dorada/crema sobre fondo oscuro en el Sidebar).

### 9.3. `src/services/api.ts` — dos instancias axios + refresh automático

```ts
const api = axios.create({ baseURL: API_URL + '/api/v1' });       // módulos
export const authApi = axios.create({ baseURL: API_URL + '/api/auth' });  // auth
```

- Interceptor de request: adjunta `Authorization: Bearer <token>` a ambas.
- Interceptor de response de `api`: ante **401** (y no sea refresh/login) →
  `tryRefresh()` con `POST /api/auth/refresh` (usando `refresh_token` de
  localStorage), actualiza tokens, **encola** peticiones concurrentes
  (`failedQueue`) mientras refresca, y **reintenta** la original con el token
  nuevo. Si el refresh falla → limpia sesión y redirige a `/login`.
- `authApi` tiene el mismo patrón pero sin re-encolar (redirige directo).

> **Gotcha importante (AGENTS.md):** usa `api` para `/api/v1/*` y `authApi`
> para `/api/auth/*`; mezclarlos rompe el refresh.

### 9.4. `src/context/AuthContext.tsx`

- Al montar, llama `authApi.get('/me')` → guarda `user` (con `roles` y
  `modulos: [{modulo, gestionar}]`).
- Expone: `user`, `loading`, `modulos`, **`esAdmin`** (¿algún rol Dueño/
  Administrador?), **`hasModulo(modulo, gestionar=false)`** (busca el módulo en
  la lista del usuario) y `logout`.

### 9.5. Servicios (`src/services/*.ts`)

| Servicio | Endpoints que envuelve |
|----------|------------------------|
| `clienteService.ts` | `/cliente/*` (CRUD) |
| `productosService.ts` | `/producto/*`, `/material/*`, calcular-precio, recetas (nótese el nombre `productosService`) |
| `cotizacionService.ts` | `/cotizacion/*` + `calculatePrice` |
| `iqeService.ts` | `/intelligent-quotation/*` |
| `pedidoService.ts` | `/pedido/*` + convertir |
| `produccionService.ts` | `/produccion/*` (órdenes, etapas, consumos, mano de obra, costos) |
| `inventarioService.ts` | `/inventario/*` (stock, alertas, movimientos) |
| `ventaService.ts` | `/venta/*`, `/pago/*`, `cuentas-por-cobrar` + `METODOS_PAGO` |
| `facturacionService.ts` | `/factura/*` |
| `reportesService.ts` | `/reports/*` (P&L, informe mensual, rentabilidad, alertas) |
| `gastoService.ts` | `/gastos/*` |
| `cuentasService.ts` | `/cuenta/*` (resumen, métodos, movimientos) |
| `costosProduccionService.ts` | `/costo-produccion/*` |
| `nominaService.ts` | `/nomina/*` |
| `empleadosService.ts` | `/empleado/*` |
| `envioService.ts` | `/envio/*` (despachos + ubicaciones) |

### 9.6. Páginas (`src/pages/*.tsx`) → ruta

| Página | Ruta | Módulo (ROUTE_MODULES) |
|--------|------|------------------------|
| `Login.tsx` | `/login` | — |
| `Dashboard.tsx` | `/dashboard` | dashboard |
| `Clientes.tsx` | `/clientes` | clientes |
| `Cotizaciones.tsx` | `/cotizaciones` | cotizaciones |
| `CotizadorInteligente.tsx` | `/cotizaciones-ia` | cotizaciones_ia |
| `Pedidos.tsx` | `/pedidos` | pedidos |
| `ProduccionKanban.tsx` | `/produccion` | produccion |
| `Empleados.tsx` | `/empleados` | empleados |
| `Inventario.tsx` | `/inventario` | inventario |
| `Productos.tsx` | `/productos` | productos |
| `Calculadora.tsx` | `/costos` | productos (costeo) |
| `Despachos.tsx` | `/envios` | envios |
| `Ventas.tsx` | `/ventas` | ventas |
| `Facturacion.tsx` | `/facturacion` | facturacion |
| `Gastos.tsx` | `/gastos` | gastos |
| `CostosProduccion.tsx` | `/costos-produccion` | costos_produccion |
| `Nomina.tsx` | `/nomina` | nomina |
| `Cuentas.tsx` | `/cuentas` | cuentas |
| `Reportes.tsx` | `/reportes` | reportes (solo esAdmin) |
| `Usuarios.tsx` | `/usuarios` | usuarios |
| `Auditoria.tsx` | `/auditoria` | usuarios |

### 9.7. Componentes UI (`src/components/ui/`)

`Button`, `Card`, `Badge`, `Spinner`, `EmptyState`, `StatCard`, `Modal`,
`PageHeader`, `SearchInput`, `Tabs`, `ConfirmDialog`, `SearchSelect`, y
`Field` (exporta `Field, Input, Select, Textarea, Label`). Todos se re-exportan
desde `ui/index.ts` → importar siempre desde `../components/ui`.

Otros componentes de dominio: `FacturaFiscalPDF.tsx`, `InformeMensual.tsx`,
`EstructuraCostosEditor.tsx` (editor de estructura de costos del IQE),
`LocationTracker.tsx` (GPS del repartidor), `SEO.tsx`, `ErrorBoundary.tsx`.

### 9.8. Utils y convenciones

- `utils/format.ts`: `formatCurrency(amount, currencyCode)` con
  `Intl.NumberFormat` por moneda (COP sin decimales), `convertFromCop`,
  `convertToCop`, y las helpers de **moneda por palabra** `nombreMoneda(codigo)`
  (COP→"Pesos", USD→"Dólares", VES→"Bolívares", EUR→"Euros") y
  `fmtMoneda(monto, codigo)` que devuelven el monto seguido del nombre claro
  (sin símbolo) — se usan en saldos pendientes, resúmenes y reportes. También
  `tasaNaturalAAlmacenada`/`convertirConTasaNatural` (pago de Ventas con la
  tasa en dirección natural "1 USD = X COP").
- **Tailwind:** paleta personalizada `yeikar-{primary|secondary|tertiary|neutral}`
  (dorado/marrón/crema/oscuro) definida en `index.css`/`tailwind.config`; sombras
  `shadow-gold`, `shadow-shell`, `shadow-card`, fondo `premium-grid`.
- **Fuentes:** `font-headline` (Hanken Grotesk), `font-body` (Inter),
  `font-mono` (JetBrains Mono).
- **Patrón "página = ruta", servicio por módulo:** crear una página nueva es
  página + ruta en `App.tsx` (ROUTE_MODULES + `<Route>`) + item en `Sidebar` +
  `pageMeta`/Navbar meta.

---

## 10. 🗺️ Mapa de Endpoints

> Fuente: `backend/app/main.py` (registro de routers) + cada `router.py`.
> Todos los `/api/v1/*` requieren JWT (Bearer). Los routers declaran el permiso
> de módulo con `require_module(...)`; los marcados 🔐 exigen Dueño/Admin (`es_admin`).
> GET = lectura (basta tener módulo); POST/PUT/DELETE = exige `gestionar=True`.

### 🔐 Autenticación — prefijo `/api/auth`

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/register` | Crear usuario (🔐 solo Dueño/Admin) |
| POST | `/api/auth/login` | Login (público, form-urlencoded) → access + refresh |
| POST | `/api/auth/refresh` | Renovar par con rotación (público) |
| GET | `/api/auth/me` | Usuario + roles + `modulos` [{modulo, gestionar}] |
| GET | `/api/auth/roles` | 🔐 Lista roles |
| GET | `/api/auth/modulos` | 🔐 Catálogo de módulos |
| GET | `/api/auth/roles/{rol_id}/permisos` | 🔐 Permisos de un rol |
| PUT | `/api/auth/roles/{rol_id}/permisos` | 🔐 Guarda permisos de un rol |
| POST | `/api/auth/usuario/{uid}/roles/{rid}` | 🔐 Asigna rol a usuario |
| DELETE | `/api/auth/usuario/{uid}/roles/{rid}` | 🔐 Quita rol |
| GET | `/api/auth/users` | 🔐 Lista usuarios |
| POST | `/api/auth/users` | 🔐 Crea usuario |
| PUT | `/api/auth/users/{uid}/status?activo=` | 🔐 Activa/desactiva |
| DELETE | `/api/auth/users/{uid}` | 🔐 Elimina usuario |

### 👥 Clientes — `/api/v1/cliente`

POST `/` · GET `/` · GET `/{id}` · PUT `/{id}` · DELETE `/{id}`

### 📦 Catálogos — `/api/v1/catalogos` (lectura compartida)

CRUD completo bajo cada sub-ruta: `/tipo-producto/`, `/unidad-medida/`,
`/tipo-gasto/`, `/ubicacion/`, `/area/`, `/cargo/`, `/moneda/`, `/rol/`
(POST, GET ``, GET `/{id}`, PUT `/{id}`, DELETE `/{id}`).

### 🪑 Productos y Materiales — `/api/v1/producto` y `/api/v1/material`

- `POST/GET /producto/`, `GET/PUT/DELETE /producto/{id}`
- `GET|POST /producto/{id}/calcular-precio?ancho=&largo=…` (costeo)
- `GET/POST /producto/{id}/receta`, `PUT/DELETE /receta/{id}` (receta plana)
- `GET /producto/{id}/receta-estructurada` · `POST /seccion/` ·
  `PUT /seccion/{id}/politica` · `DELETE /seccion/{id}` ·
  `POST /seccion/{id}/elemento` · `DELETE /elemento/{id}` ·
  `POST /seccion/{id}/costo-produccion` · `PUT/DELETE /costo-produccion/{id}` ·
  `POST /recalculate-custom-recipe`
- `/api/v1/material/`: POST `/` · GET `/` · GET `/{id}` · PUT `/{id}` · DELETE `/{id}`

### 🚚 Proveedores — `/api/v1/proveedor` · 👷 Empleados — `/api/v1/empleado`

CRUD estándar en ambos.

### 📋 Cotizaciones — `/api/v1/cotizacion`

POST `/` · GET `/` (con `solo_mes_actual`, `mes`, `anio`) · GET `/{id}` ·
PUT `/{id}` · DELETE `/{id}`

### 🛍️ Pedidos — `/api/v1/pedido`

POST `/` · GET `/` (filtros históricos) · GET `/{id}` · PUT `/{id}` ·
DELETE `/{id}` · **POST `/convertir/{id_cotizacion}`** (con adelanto opcional)

### 🏭 Producción — `/api/v1/produccion`

- Órdenes: POST `/orden/` · POST `/orden/desde-pedido/{detalle_id}` ·
  GET `/orden/` · GET `/orden/{id}` · PUT `/orden/{id}` ·
  PUT `/orden/{id}/estado?estado=` · DELETE `/orden/{id}`
- Etapas: POST `/etapa/` · GET `/etapa/{id}` · PUT `/etapa/{id}` ·
  PUT `/etapa/{id}/estado?estado=` · DELETE `/etapa/{id}` ·
  POST `/etapa/{id}/pasar-a-area` · POST `/etapa/{id}/asignados` ·
  DELETE `/etapa/{id}/asignados/{empleado_id}` · GET `/etapa/{id}/referencia-receta`
- Consumos: POST `/consumo/` · GET `/consumo/por-orden/{orden_id}` ·
  DELETE `/consumo/{id}`
- Mano de obra: POST `/mano-obra/` · DELETE `/mano-obra/{id}` ·
  PUT `/mano-obra/{id}/pagar?pagado=`
- Costos: POST `/costo/calcular/{orden_id}` (body opcional) ·
  GET `/costo/{orden_id}`

### 💵 Ventas / Pagos — `/api/v1/venta` y `/api/v1/pago`

- POST `/venta/` · GET `/venta/` · GET `/venta/cuentas-por-cobrar/` ·
  GET `/venta/{id}` · DELETE `/venta/{id}`
- POST `/pago/` (abono + ENTRADA de caja)

### 🧾 Facturación fiscal — `/api/v1/factura`

POST `/` · GET `/` · GET `/pedidos-facturables/` · GET `/tasas/` ·
PUT `/tasas/{clave}` (🔐) · GET `/{id}` · POST `/{id}/anular`

### 💸 Gastos — `/api/v1/gastos`

POST `/` · GET `/` (filtros) · GET `/{id}` · PUT `/{id}` · DELETE `/{id}`

### 💱 Tasas de cambio — `/api/v1/tasa`

- GET `/convertir?monto=&moneda_origen_id=&moneda_destino_id=&fecha=`
- CRUD bajo `/tasas-cambio/`: POST `/` · GET `/` · GET `/{id}` ·
  GET `/ultima/?moneda_origen_id=&moneda_destino_id=` · DELETE `/{id}`

### 📦 Inventario — `/api/v1/inventario`

GET `/` · GET `/alertas?umbral=` · POST `/movimiento` ·
GET `/movimientos/material/{id}` · GET `/productos` ·
GET `/productos/alertas` · POST `/producto/movimiento` ·
GET `/movimientos/producto/{id}`

### 🛒 Compras — `/api/v1/compras`

POST `/` · GET `/` · GET `/{id}` · PUT `/{id}/estado?estado=`

### 📊 Reportes — `/api/v1/reports` (🔐 Dueño/Admin)

GET `/pnl?mes=` · GET `/informe-mensual?mes=` · GET `/rentabilidad-producto` ·
GET `/alertas-stock?umbral=` · GET `/diario?fecha=` (Estado del día) ·
CRUD `/conceptos` ·
GET/PUT `/valores-mensuales/{mes}` · CRUD `/metodos-caja` ·
CRUD `/movimientos-caja` · CRUD `/devoluciones`

### 💳 Cuentas / Caja — `/api/v1/cuenta`

GET `/` y GET `/resumen` (saldos por cuenta + COP) · POST `/` ·
PUT `/{id}` · DELETE `/{id}` · GET `/movimientos` ·
POST `/{metodo_id}/movimiento` · PUT `/movimiento/{id}` ·
DELETE `/movimiento/{id}`

### 📈 Dashboard — `/api/v1/dashboard`

GET `/metrics`

### 🚚 Envíos — `/api/v1/envio`

POST `/` · GET `/` · GET `/mis-asignaciones` (repartidores) · GET `/{id}` ·
PUT `/{id}` · PUT `/{id}/estado?estado=` · DELETE `/{id}` ·
POST/GET `/{id}/ubicaciones` · GET `/{id}/ubicacion-actual`

### 🤖 Cotizador IA — `/api/v1/intelligent-quotation`

GET `/contexto-exportar` · POST `/import-structure` ·
POST `/recalculate-structure` · POST `/finalize-structure`

### 🕵️ Auditoría — `/api/v1/auditoria` (🔐)

GET `/`

### 🏷️ Costos de Producción — `/api/v1/costo-produccion`

GET `/` (filtros) · POST `/` · PUT `/{id}` · DELETE `/{id}`

### 🧾 Nómina — `/api/v1/nomina`

GET `/area-config` · PUT `/area-config/{area_id}` · POST `/generar` ·
POST `/` · GET `/` · GET `/saldos-aguinaldo` · GET `/{id}` ·
PUT `/detalle/{id}` · POST `/detalle/{id}/linea` · DELETE `/linea/{id}` ·
POST `/{id}/concepto-vario` · DELETE `/concepto-vario/{id}` ·
POST `/{id}/pagar` · POST `/{id}/anular`

---

## 11. 🧪 Testing

```bash
cd backend && source venv/bin/activate
pytest test/ -v              # (ver nota abajo sobre NoCollect)
pytest test/test_money_flow.py -v
```

### 11.1. `conftest.py`

- `_firmar_token(username)` firma JWTs con `settings.SECRET_KEY` para usuarios
  **reales** de la BD: `ADMIN_HEADERS` = `jackson` (Dueño) y `VENTAS_HEADERS` =
  `daniel` (Ventas).
- Fixtures: `client` (TestClient de la app), `db` (sesión), y **`cleaner`**:
  los tests crean datos con prefijo `test_`, registran sus IDs y el `cleaner`
  los borra en el teardown **en orden inverso de FKs** (`ORDEN_LIMPIEZA` va de
  `devolucion_venta`/`pago`/… hasta `usuario`). NUNCA romper el orden de esa
  lista si agregas tablas nuevas al borrado.
- El docstring de conftest advierte: **no** ejecutar `pytest test/` completo en
  solitario; correr los archivos individuales.

### 11.2. Archivos de test y qué cubren

| Archivo | cubre |
|---------|-------|
| `test_money_core.py` | Lógica financiera pura: `_derivar_tasa_pago`, `_evaluar_condicion`, `_calcular_por_rango`. |
| `test_money_flow.py` | Flujo completo cotización → pedido → venta → abonos multi-moneda, control de saldos, idempotencia. |
| `test_concurrency.py` | Carreras: pagos simultáneos, conversión doble de la misma cotización, salidas de inventario concurrentes. |
| `test_production_risks.py` | Riesgos de producción/costeo (C1–C6): escalado de recetas, finalizar sin etapas, TERMINADO sin todas las líneas, stock. |
| `test_fase2_contabilidad.py` | Circuito contable (H1–H7, V2, D1, P1): compras descuentan caja, devoluciones reembolsan, movimientos negativos → 422, etc. |
| `test_facturacion.py` | Factura SENIAT: pedido no pagado → rechazado; pagado → totales con IVA/IGTF. |
| `test_permisos.py` | Rol + `rol_modulo`: acceso por módulo y lecturas compartidas. |
| `test_security.py` | 401/403/400: tokens inválidos o de tipo refresh, replay de refresh, acceso sin permiso, auto-desactivación. |
| `test_auditoria2.py` | Regresiones: abono USD con TRM, DELETE con FK → 409, gasto con FK inexistente → 400, moneda de venta ≠ cotización → 400. |
| `test_integracion_api.py` | Suite estilo script (usa `requests`, no pytest) de auth/usuario/filtros — requiere servidor corriendo. |
| `test_iqe_manual.py` | Modo manual del Cotizador IA: contexto-exportar e import-structure. |
| `test_iqe_fase5.py` | **⚠️ ROTO (no recoge):** importa
  `from app.modules.quotes.vision_provider import FurnitureAttributes`, pero ese
  módulo ya no existe (se eliminó al quitar el modo API; el modelo vive en
  `quotes/atributos.py`). **Problema conocido**: `pytest` falla al recolectarlo
  con `ModuleNotFoundError`. Arreglar cambiando el import a `atributos`
  (pendiente; no afecta a la app). |

### 11.3. Scripts legados

- `backend/scripts/*.py`: importación de productos/recetas desde Excel
  (`importar_productos_y_recetas.py`, `importar_estructuras_v2.py`,
  `importar_insumos_masivo.py`, `importar_recetas_secciones.py`), sinónimos,
  atributos históricos, y migraciones SQL multi-moneda
  (`migracion_pago_multimoneda.sql`).
- `/scratch` y `verify_fixes.py` ya no existen (historial inicial de fixes).

---

## 12. 🐳 Docker / Producción

### 12.1. Arquitectura

| Servicio | Imagen | Puertos | Rol |
|----------|--------|---------|-----|
| `db` | postgres:18-alpine | interno (`expose` no publicado) | PostgreSQL con healthcheck |
| `backend` | Python 3.11-slim (build) | interno 8000 | uvicorn con **2 workers** y `--no-proxy-headers` |
| `frontend` | Node 20 build → nginx:alpine | **80:80** (único punto de entrada público) | SPA estática + proxy `/api → backend:8000` |
| `backup` | postgres:18-alpine (perfil `backup`) | — | pg_dump diario a las 03:00, retención 14 días |

- **`docker-compose.yml`**: DB con volumen `postgres_data`, backend espera a
  que la DB esté sana (`service_healthy`), frontend espera al backend. Todas
  las variables vienen de `.env` compose (`DB_USER`, `DB_PASSWORD`, `DB_NAME`,
  `SECRET_KEY`, `DEBUG`, límites de rate limit/login…). **Compose `up` NO aplica
  migraciones automáticamente**: tras un deploy, ejecuta
  `docker compose exec backend alembic upgrade head` (o documentarlo en el
  manual de deploy).
- **Backend Dockerfile — ⚠️ usa Python 3.11** (no 3.13): los wheels de
  psycopg2 y la imagen `python:3.11-slim` están validados; el dev usa la
  versión instalada localmente.
- **Frontend Dockerfile**: multi-stage Node 20 → nginx:alpine; `npm ci
  --frozen-lockfile` + `npm run build` (que incluye `tsc`).
- **`frontend/nginx.conf`**: gzip, caché inmutable 1 año para assets con hash,
  `location /api/` con `limit_req` (30 r/s burst 60) y `limit_conn` (20), SPA
  fallback, headers de seguridad, y `proxy_pass http://backend:8000` enviando
  `X-Real-IP`/`X-Forwarded-For`. Como el backend arranca con `--no-proxy-headers`,
  **no** confía en esos headers (usa la IP del socket/nginx).
- Salud: healthchecks HTTP en backend y frontend (`docker compose ps` los
  muestra).

### 12.2. Puesta en marcha

```bash
cp .env.example .env    # edita SECRET_KEY y credenciales
docker compose up -d --build
docker compose ps

# Restaurar/aplicar el esquema en la BD del contenedor (primer despliegue)
docker compose exec -T db psql -U yeikar -d yeikar_db < backend/esquema.sql
docker compose exec backend alembic upgrade head

# Backup manual / restauración
docker compose --profile backup up -d                 # cron diario
docker compose exec -T db pg_restore -U yeikar -d yeikar_db < backups/yeikar_*.dump
```

> ⚠️ Solo `:80` (frontend) se publica al host: backends y DB viven en la red
> interna de compose. Para HTTPS pon nginx/certbot (o Caddy) delante de `:80`.

---

## 13. 🛠️ Errores Comunes y Soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `fe_sendauth: no password supplied` | Falta contraseña en `DATABASE_URL` | Verifica el formato del `.env` |
| `permission denied for table X` | El usuario de la BD no tiene permisos | Ejecuta los `GRANT` (sección 5.3) |
| `SECRET_KEY debe configurarse en produccion` | Arranque en modo no-DEBUG sin `SECRET_KEY` fuerte (≥32 chars) | `openssl rand -hex 32` y ponla en el `.env` |
| `{"detail":"Not authenticated"}` / `"No se pudieron validar las credenciales"` | Token ausente, vencido, o con `type` que no es `access` | Incluye `Authorization: Bearer`; haz login/refresh nuevo |
| `ModuleNotFoundError: No module named 'X'` | Falta instalar una dependencia | `pip install -r requirements.txt` con venv activo |
| `{"detail":"Not Found"}` en una ruta | Prefijo incorrecto | Ver mapa de endpoints (sección 10): p. ej. producción es `/api/v1/produccion` (no `production`), pedidos convert es `/convertir/`, catálogos están bajo `/api/v1/catalogos/...` |
| 422 `{"detail":[{"loc":["body"],...}]}` | FastAPI no recibió el **body** (aunque el schema sea opcional) | Manda JSON: `body` falta ≠ campos opcionales; o usa `Body(default_factory=...)` en el endpoint |
| `RequestValidationError` (422) al **enviar** datos | Payload del cliente no cumple el schema (campo faltante/tipo/`estado` no mayúsculas) | Revisa `loc` en `detail`; envía estados en mayúsculas (`BORRADOR`, `APROBADA`…) |
| `ResponseValidationError` (500) al **responder** | Objeto devuelto a un schema que exige campos que vienen `NULL` (p. ej. `updated_at`) | Marca el campo como `Optional[datetime] = None` en el schema de respuesta |
| 400 "viola una restricción de la base de datos" | Check/FK/UNIQUE (handler global de `IntegrityError` en `main.py`) | Lee el campo `detail`; probablemente un `estado` no permitido o FK inexistente |
| Rate limit 429 "Demasiadas solicitudes" | Muchas peticiones desde la misma IP | Sube `RATE_LIMIT_REQUESTS_PER_MINUTE` o usa otra IP; recuerda que es por proceso |
| "Demasiados intentos fallidos" al login (429/blocked) | Lockout por intentos (cuenta+IP / IP / ≥3 IPs) | Espera la ventana (`LOGIN_VENTANA_MINUTOS`); verificar `login_intento` |
| Prefijo duplicado / ruta que no aparece en `/docs` | El router no se registró en `main.py`, o su `prefix` choca con otro | Registra con `app.include_router(..., prefix=...)` y revisa `GET /openapi.json` |
| `Alembic: Target database is not up to date` o `down_revision` roto | Cadena de migraciones editada/rebasada | `alembic history` para ver la cadena; respetar `down_revision` (head actual `h2i3j4k5l6m7`); no editar migraciones ya aplicadas |
| Token "expirado"/401 justo al crear, pero "válido" en scripts | **Zonas horarias:** `crear_token_acceso` usa `datetime.utcnow()`; si firmas/examinas con hora local la validez parece desfasada | Firmar con UTC (patrón del CLI/scripts) y ver la máquina/BD en UTC o en la zona esperada |
| Cambio de modelo sin efecto en autogenerate | El modelo no está importado en `alembic/env.py` | Añade `import app.modules.<nombre>.model` a `env.py` |
| `NaN` en la UI de costos | La respuesta del costeo no trae el campo (mercadeo de aliases) | Usar `materiales_detalle ?? materiales`, `costo_total ?? costo_produccion`, etc. (ver `cost_service.py`) |
| `docker compose up` pero el backend devuelve 500 en el healthcheck | La BD está vacía (only esquema base, falta migración) o `SECRET_KEY` mal | `db` sano → `alembic upgrade head`; SECRET_KEY ≥32 chars |

---

## 14. 🔨 Cómo Agregar un Nuevo Módulo

Patrón repetido (último ejemplo real: `costos_produccion` y `nomina`).

### Backend

```bash
mkdir -p backend/app/modules/andamiaje
touch backend/app/modules/andamiaje/{__init__,model,schemas,service,router}.py
```

1. **`model.py`** — define las clases ORM (heredar de `Base`), con `BigInteger` PK
   indexada, FKs con `ondelete` explícito y `created_at`/`updated_at`.
2. **`schemas.py`** — Pydantic v2; respuestas con `class Config:
   from_attributes = True`; marcar `updated_at` como `Optional`.
3. **`service.py`** — funciones puras de lógica con `Session`; lanzar
   `ValueError` para errores de negocio (los routers lo vuelven 400); usar
   `with_for_update()` si hay riesgo de carrera; llamar `record_event(...)` de
   auditoría en mutaciones.
4. **`router.py`**:

```python
router = APIRouter(prefix="/andamiaje", tags=["Andamiaje"],
                   dependencies=[Depends(require_module('andamiaje'))])
@router.get("/", response_model=List[...])
def listar(db=Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    ...
```

5. **`main.py`** — importa el router y regístralo:
```python
app.include_router(andamiaje_router, prefix="/api/v1", tags=["andamiaje"])
```

6. **Catálogo de permisos** — añade la clave a `MODULOS_CATALOGO`
   (`app/modules/users/deps.py`) y otórgala a los roles mediante una
   **migración** (`INSERT INTO rol_modulo ... ON CONFLICT DO UPDATE`) o desde el
   panel Usuarios. `require_module('andamiaje')` fallará con `ValueError` si la
   clave no está en el catálogo.

7. **Migración** — `alembic revision --autogenerate -m "andamiaje"`; **agrega el
   modelo a `alembic/env.py`** ANTES de autogenerar. Revisa el `down_revision`
   y la cadena; no rompas el head.

### Frontend

1. `frontend/src/services/andamiajeService.ts` — envuelve `/andamiaje/*` usando
   el `api` de `src/services/api.ts`.
2. `frontend/src/pages/Andamiaje.tsx` — página usando componentes de `ui/`.
3. `frontend/src/App.tsx` — añade la ruta a `ROUTE_MODULES`
   (`'/andamiaje': 'andamiaje'`), a `pageMeta`, un `<Route>` envuelto en
   `<PrivateRoute>` + `<DashboardLayout>`, y la ruta a `Navbar.tsx`.
4. `frontend/src/components/Layout/Sidebar.tsx` — item con `module: 'andamiaje'`.
5. **Tests** — añade el módulo al `ORDEN_LIMPIEZA` de `test/conftest.py` si
   creas tablas que otros tests puedan referenciar.

---

## 15. 📖 Glosario Rápido de Términos de Negocio

| Término | Significado |
|---------|-------------|
| **Cotización** | Documento de venta con precio estimado de un mueble a medida (paramétrico). Estados: BORRADOR, ENVIADA, APROBADA, RECHAZADA, VENCIDA. |
| **Pedido** | Orden de un cliente con sus líneas (detalle con dimensiones/color/acabado). Nace COTIZADO al convertir una cotización; flujo: → APROBADO → PRODUCCION → TERMINADO → ENTREGADO (o CANCELADO). |
| **Orden de producción** | Fabricación de **una línea** de un pedido (una por `detalle_pedido`). Estados: PENDIENTE → EN_PRODUCCION → PAUSADA → FINALIZADA / CANCELADA. |
| **Etapa** | Paso de fabricación dentro de una orden en un **área** (Ebanistería, Preparación, Pintura, Tapicería…), con un empleado responsable. Estados: ASIGNADA → EN_PROCESO → PAUSADA / COMPLETADA. Es lo que ve el **Kanban**. |
| **Sección / Área** | Departamento productivo. `area` es el catálogo de producción; `seccion` (en `producto_material` y `seccion_producto`) es el área dentro de una receta. |
| **Destajo** | Empleado pagado por pieza producida (según `precio_produccion` del área). |
| **Fijo** | Empleado pagado con `sueldo_semanal` fijo (entra a la nómina con esa línea). |
| **Aguinaldo** | Bono que se acumula en `empleado.saldo_aguinaldo` al pagar la nómina: % del área (Ebanistería 8 %, otras 5 %) sobre la producción de destajo. |
| **Egreso** | Salida de dinero real: gasto con caja, compra CONTADO recibida, nómina pagada, devolución. Cada egreso genera una SALIDA en `movimiento_caja`. |
| **Cuenta / Método de caja** | Medio o fondo donde se mueve el dinero: EFECTIVO COP, EFECTIVO USD, EFECTIVO VES, BANCOLOMBIA, BANCARIBE, ZELLE (tabla `metodo_caja`). |
| **Movimiento de caja** | Registro contable de cada flujo: APERTURA/ENTRADA/SALIDA/AJUSTE con monto, moneda, tasa y equivalente COP. Los saldos por cuenta se calculan sumándolos. |
| **TRM / Tasa de cambio** | COP que vale 1 unidad de otra moneda (tasa `moneda_origen → COP`, por fecha). Se congela en cotización/venta/compra/pago para el reporte. |
| **Precio de producción** | Catálogo `precio_produccion`: cuánto suma cada pieza fabricada según área y mueble; es la base del pago por destajo. |
| **Moneda base** | COP (id 1). Todos los montos en otra moneda se expresan además en COP con `*_en_moneda_base`. |

---

## 16. 🗺️ Roadmap / Estado por Módulo

### ✅ Completo y en uso (ago 2026)

| Módulo | Estado | Notas |
|--------|--------|-------|
| Autenticación JWT + refresh rotatorio | ✅ | + lockout anti-brute-force, auditoría de login |
| Permisos por módulo (`rol_modulo`) | ✅ | Dueño/Admin totales; lecturas compartidas; panel de privilegios |
| Clientes, Proveedores, Empleados | ✅ | |
| Catálogos | ✅ | bajo `/api/v1/catalogos/*` |
| Productos + Materiales + Recetas | ✅ | plana (`producto_material`) y jerárquica (secciones) + costeo paramétrico |
| Cotizaciones (paramétricas, multi-producto) | ✅ | filtros históricos mes/año |
| Cotizador IA (modo manual) | ✅ | contexto-exportar / import-structure / finalize |
| Pedidos + conversión con adelanto | ✅ | convierte en 1 transacción (pedido+venta+pago) |
| Producción (Kanban, consumos, mano de obra, costos) | ✅ | sincroniza pedido→TERMINADO→envío |
| Inventario (materiales y productos de reventa) | ✅ | kardex + alertas |
| Compras | ✅ | entrada de stock + caja al recibir |
| Ventas, pagos/abonos, cuentas por cobrar | ✅ | cobro → ENTRADA de caja |
| Sistema de caja (métodos + movimientos) | ✅ | apertura 1M COP por cuenta, saldos/resumen |
| Gastos | ✅ | egreso con salida de caja |
| Tasas de cambio | ✅ | |
| Facturación fiscal SENIAT | ✅ | factura por pedido pagado, USD→Bs con IVA/IGTF |
| Reportes P&L + Informe mensual + rentabilidad | ✅ | solo Dueño/Admin |
| Dashboard | ✅ | |
| Auditoría | ✅ | |
| Costos de Producción (catálogo precio_produccion) | ✅ | módulo nuevo (ago 2026) + seed completo |
| Nómina semanal | ✅ | módulo nuevo (ago 2026): destajo, aguinaldo, egresos |
| Envíos/despachos con tracking GPS | ✅ | |

### 🔜 Pendiente / mejoras (orden aproximado)

| Prioridad | Área | Descripción |
|-----------|------|-------------|
| 1 | **Arreglar `test_iqe_fase5.py`** | Cambiar el import a `app.modules.quotes.atributos` para que la suite recolecte completa |
| 2 | **Migraciones automáticas en deploy** | Hook/entrada que ejecute `alembic upgrade head` al levantar el backend en compose |
| 3 | Notificaciones | Alertas de stock bajo / pedidos atrasados (email o WebSocket) |
| 4 | Botón de pagar mano de obra ligado a caja | Hoy `mano-obra/pagar` marca `pagado` pero no genera egreso de caja automático (el P&L sí lo cuenta) — evaluar si debe salir de una cuenta |
| 5 | Página de Compras en el frontend | El backend existe (`/api/v1/compras`); la UI aún no está construida |
| 6 | CI/CD | GitHub Actions: lint + pytest + build docker por PR |
| 7 | App móvil (operarios) | Vista para plantar/ubicación de repartidor (LocationTracker ya existe en web) |

---

*Última actualización: agosto 2026.* Esta guía se reescribió por completo desde
cero (documentación progresiva del estado real del repo). Mantenla viva: al
agregar un módulo, actualiza las secciones 8, 10, 14 y el estado de la 16.
