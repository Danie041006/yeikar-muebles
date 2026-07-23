# 📘 Guía del Desarrollador — YEIKAR ERP

> **Para quién es esto:** Para cualquier desarrollador (nuevo o el mismo Daniel en 6 meses) que quiera entender el proyecto, levantarlo localmente, o continuar desarrollándolo.
>
> Si nunca has tocado este proyecto, lee esta guía de arriba a abajo y tendrás todo funcionando.

---

## 📌 ¿Qué es YEIKAR ERP?

YEIKAR es un sistema ERP (Enterprise Resource Planning) hecho a medida para **Comercializadora YEIKAR**, una empresa en Venezuela que fabrica y vende muebles, camas, colchones y electrodomésticos.

El objetivo es reemplazar el caos de Excel con un sistema centralizado que maneje:

- Clientes y proveedores
- Productos y materiales
- Órdenes de producción paso a paso
- Control de inventario
- Costos reales (en COP, USD, VES)
- Ventas y pagos

**Estado actual (junio 2026):** Backend + Frontend 100 % funcionales. Autenticación JWT con refresh token automático, Kanban de producción, inventario, reportes financieros, gestión de productos, roles granulares (`rol` + `usuario_rol`) y despliegue Docker listo.

---

## 🗂️ Estructura del Proyecto

```
YEIKAR/
├── backend/                        ← API REST (FastAPI + Python)
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py           # Lee el .env y expone las variables
│   │   ├── db/
│   │   │   ├── session.py          # Crea el engine de SQLAlchemy y la sesión
│   │   │   └── base.py             # Base declarativa compartida por todos los modelos
│   │   ├── modules/
│   │   │   ├── users/              # Autenticación JWT
│   │   │   │   ├── model.py        # Clase Usuario (tabla "usuario")
│   │   │   │   ├── schemas.py      # Pydantic: entrada/salida de usuarios
│   │   │   │   ├── service.py      # Lógica: hashear contraseñas, tokens
│   │   │   │   └── router.py       # Rutas: /register, /login, /me
│   │   │   ├── clients/            # CRUD de clientes
│   │   │   ├── catalogos/          # Catálogos (área, cargo, moneda, unidad, tipo_producto, ubicación, tipo_gasto)
│   │   │   ├── productos/          # Productos y materiales
│   │   │   ├── proveedores/        # Proveedores
│   │   │   ├── empleados/          # Empleados
│   │   │   ├── quotes/             # Cotizaciones (modelo, schemas, service, router)
│   │   │   ├── orders/             # Pedidos y detalle de pedido
│   │   │   └── production/         # Módulo completo de Producción
│   │   │       ├── model.py        # OrdenProduccion, EtapaProduccion, ConsumoMaterial, ManoObra, CostoProduccion
│   │   │       ├── schemas.py      # Schemas Pydantic de producción
│   │   │       ├── service.py      # Lógica de negocio (Kanban, cálculo de costos)
│   │   │       └── router.py       # Endpoints de órdenes, etapas, consumos, mano de obra y costos
│   │   └── main.py                 # Punto de entrada: crea la app y registra los routers
│   ├── alembic/                    # Migraciones de base de datos (Alembic)
│   ├── venv/                       # Entorno virtual Python (NO se sube a git)
│   ├── .env                        # Variables secretas locales (NO se sube a git)
│   ├── .env.example                # Plantilla del .env para que otros sepan qué poner
│   ├── requirements.txt            # Lista de dependencias Python
│   └── esquema.sql                 # Dump completo de la base de datos
├── docs/                           # Toda la documentación del proyecto
│   ├── architecture/               # Esquema de BD, diagramas ERD
│   ├── business/                   # Flujos de negocio (producción, ventas, etc.)
│   ├── decisions/                  # Decisiones técnicas (por qué se eligió X)
│   ├── development/                # Esta guía y otras guías de desarrollo
│   └── setup/                      # Instrucciones de instalación del entorno
├── frontend/                       # React + TypeScript + Vite + Tailwind CSS
├── infra/                          # Configuración de infraestructura
├── scripts/                        # Scripts utilitarios
├── docker-compose.yml              # Levanta toda la app con Docker
└── README.md                       # Resumen ejecutivo del proyecto
```

> **Patrón de módulos:** Cada módulo (users, clients, products…) tiene siempre los mismos 4 archivos: `model.py`, `schemas.py`, `service.py`, `router.py`. Así el código es predecible y fácil de navegar.

---

## 🔧 Stack Tecnológico

| Capa | Tecnología | Versión | ¿Por qué? |
|------|-----------|---------|-----------|
| Framework backend | FastAPI | 0.115.6 | Rápido, genera documentación automática (Swagger), ideal para APIs REST |
| Servidor ASGI | Uvicorn | 0.34.0 | Servidor de alto rendimiento para FastAPI |
| ORM | SQLAlchemy | 2.0.36 | Mapea clases Python a tablas SQL, sin escribir SQL a mano |
| Migraciones | Alembic | 1.14.1 | Controla los cambios en el esquema de BD con versionado |
| Base de datos | PostgreSQL | 15+ | Confiable, soporta transacciones ACID y múltiples monedas |
| Driver PostgreSQL | psycopg2-binary | 2.9.10 | Adaptador para conectar Python con PostgreSQL |
| Autenticación | python-jose | 3.3.0 | Genera y valida tokens JWT |
| Hash de contraseñas | passlib[bcrypt] | 1.7.4 | Hashea contraseñas de forma segura con bcrypt |
| Validación de datos | Pydantic | integrado en FastAPI | Valida los datos de entrada y salida automáticamente |
| Variables de entorno | python-dotenv | 1.0.1 | Lee el archivo .env |
| Frontend (futuro) | React + TypeScript + Vite | — | Interfaz moderna, tipada y rápida de desarrollar |

> Ver decisión completa en [`docs/decisions/adr-001-stack-tecnologico.md`](../decisions/adr-001-stack-tecnologico.md)

---

## 🐘 Base de Datos

### Resumen

- **Motor:** PostgreSQL 15+
- **Nombre de la BD:** `yeikar`
- **Usuario de la app:** `yeikar` / contraseña: `yeikar123`
- **Superusuario local:** `postgres`
- **Total de tablas:** 32 (el esquema cubre todo el negocio)

### Grupos de tablas

| Grupo | Tablas |
|-------|--------|
| **Catálogos** | `area`, `cargo`, `tipo_producto`, `unidad_medida`, `moneda`, `ubicacion` |
| **Acceso** | `usuario`, `rol`, `usuario_rol` |
| **Maestros** | `cliente`, `proveedor`, `empleado`, `producto`, `material` |
| **Ventas** | `cotizacion`, `detalle_cotizacion`, `pedido`, `detalle_pedido`, `venta`, `detalle_venta`, `pago` |
| **Compras** | `compra`, `detalle_compra` |
| **Producción** | `orden_produccion`, `etapa_produccion`, `consumo_material`, `mano_obra`, `costo_produccion` |
| **Inventario** | `inventario`, `movimiento_inventario` |
| **Finanzas** | `gasto`, `tasa_cambio` |

### Restaurar la base de datos desde cero

```bash
# 1. Crear usuario y base de datos en PostgreSQL
sudo -u postgres psql -c "CREATE USER yeikar WITH PASSWORD 'yeikar123';"
sudo -u postgres psql -c "CREATE DATABASE yeikar OWNER yeikar;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE yeikar TO yeikar;"

# 2. Restaurar el dump completo
psql -U postgres -d yeikar < backend/esquema.sql

# 3. Dar permisos al usuario yeikar sobre todas las tablas
sudo -u postgres psql -d yeikar -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO yeikar;"
sudo -u postgres psql -d yeikar -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO yeikar;"
```

> ⚠️ **Importante:** El paso 3 (GRANT) es crítico. Sin él, el usuario `yeikar` no puede hacer INSERT ni UPDATE y la app falla con `permission denied for table`.

### Características del esquema

- Todos los modelos tienen `created_at` y `updated_at`.
- `updated_at` se actualiza automáticamente via **triggers** (`trg_*_updated`).
- Los campos `estado` tienen **CHECK constraints** con los valores permitidos.
- Las claves foráneas usan `ON DELETE RESTRICT` o `CASCADE` según corresponda.

> Ver el diagrama completo en [`docs/architecture/erd.md`](../architecture/erd.md)

---

## 🚀 Instalación Local (paso a paso)

### Requisitos

- Python 3.13+
- PostgreSQL 15+
- Git

### 1. Clonar el repositorio

```bash
git clone <repo-url>
cd YEIKAR
```

### 2. Configurar el backend

```bash
cd backend

# Crear el entorno virtual
python3 -m venv venv

# Activarlo
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
# Copiar la plantilla
cp .env.example .env

# Editar con tus valores
nano .env
```

El archivo `.env` debe contener (ver `.env.example`):

```env
DATABASE_URL=postgresql://yeikar:yeikar123@localhost:5432/yeikar_db
SECRET_KEY=una-clave-secreta-larga-y-aleatoria-minimo-32-caracteres
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

> 🔑 **SECRET_KEY:** Puedes generar una así: `python3 -c "import secrets; print(secrets.token_hex(32))"`
>
> ⚠️ **Nunca** subas el `.env` real a git. Ya está en el `.gitignore`.

### 4. Verificar la conexión a la base de datos

```bash
python -c "from app.db.session import engine; print('✅ Conexión OK')"
```

Si falla, revisa que PostgreSQL esté corriendo y que las credenciales del `.env` sean correctas.

### 5. Levantar el servidor

```bash
uvicorn app.main:app --reload
```

El servidor quedará en **http://localhost:8000**

- 📖 **Swagger UI** (pruebas interactivas): http://localhost:8000/docs
- 📄 **ReDoc** (lectura): http://localhost:8000/redoc

---

## 🔐 Módulo de Autenticación (`/api/auth`)

### ¿Cómo funciona?

1. El usuario envía su `nombre_usuario` y `password` al endpoint `/login`.
2. El servidor verifica la contraseña contra el hash bcrypt guardado en la BD.
3. Si es correcta, genera un **token JWT** firmado con `SECRET_KEY`.
4. El cliente guarda ese token y lo manda en el header `Authorization: Bearer <token>` en cada petición protegida.
5. El servidor decodifica el token, extrae el `nombre_usuario`, busca al usuario en la BD y lo inyecta en la función del endpoint.

### Modelo de datos — tabla `usuario`

```python
class Usuario(Base):
    __tablename__ = "usuario"

    id            = Column(Integer, primary_key=True)
    empleado_id   = Column(Integer, nullable=True)       # Puede estar vinculado a un empleado
    nombre_usuario= Column(String(100), unique=True)     # Login
    email         = Column(String(150), unique=True)
    password_hash = Column(String)                       # bcrypt, NUNCA texto plano
    activo        = Column(Boolean, default=True)
    ultimo_acceso = Column(DateTime)                     # Se actualiza en cada login
    created_at    = Column(DateTime, server_default=func.now())
    updated_at    = Column(DateTime, onupdate=func.now())
```

### Esquemas Pydantic — `schemas.py`

| Esquema | Uso | Campos |
|---------|-----|--------|
| `UsuarioCreate` | Entrada al registrar | `nombre_usuario`, `email`, `password` |
| `UsuarioResponse` | Respuesta al cliente | `id`, `nombre_usuario`, `email`, `activo`, `ultimo_acceso`, `created_at` |
| `Token` | Respuesta del login | `access_token`, `token_type` |
| `TokenData` | Datos dentro del JWT | `nombre_usuario` |

### Funciones clave — `service.py`

| Función | Qué hace |
|---------|----------|
| `verificar_password(plain, hashed)` | Compara la contraseña con el hash bcrypt |
| `obtener_password_hash(password)` | Genera un hash bcrypt seguro |
| `obtener_usuario_por_nombre(db, username)` | Busca un usuario por su nombre de usuario |
| `autenticar_usuario(db, username, password)` | Valida credenciales y retorna el usuario (o `False`) |
| `crear_token_acceso(data, expires_delta)` | Genera el JWT con fecha de expiración |
| `actualizar_ultimo_acceso(db, user_id)` | Actualiza `ultimo_acceso` en cada login |
| `crear_usuario(db, user)` | Crea un nuevo usuario hasheando la contraseña |

### Endpoints — `router.py`

#### `POST /api/auth/register` — Crear usuario *(público)*

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"nombre_usuario": "nuevo_usuario", "email": "correo@ejemplo.com", "password": "mipassword123"}'
```

#### `POST /api/auth/login` — Iniciar sesión *(público)*

> Usa `application/x-www-form-urlencoded`, no JSON. Así funciona el estándar OAuth2.

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=carolina&password=carolina2025$"
```

Respuesta:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### `GET /api/auth/me` — Ver mi usuario *(requiere token)*

```bash
TOKEN="<el token que obtuviste arriba>"
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Respuesta:

```json
{
  "nombre_usuario": "carolina",
  "email": "carolina@yeikar.com",
  "id": 2,
  "activo": true,
  "ultimo_acceso": "2026-06-05T03:43:55.111502",
  "created_at": "2026-06-03T22:25:54.255140"
}
```

### La dependencia `get_current_user`

Esta función es la clave de todo el sistema de protección. Está definida en `router.py` del módulo `users` y se reutiliza en cualquier módulo que necesite proteger sus endpoints:

```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> model.Usuario:
    # 1. Decodifica el JWT
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    username = payload.get("sub")

    # 2. Busca el usuario en la BD
    user = service.obtener_usuario_por_nombre(db, username=username)

    # 3. Verifica que existe y está activo
    if user is None or not user.activo:
        raise HTTPException(status_code=401, ...)

    return user
```

Para proteger cualquier endpoint, simplemente agrega:

```python
current_user: Usuario = Depends(get_current_user)
```

---

## 👥 Módulo de Clientes (`/api/v1/cliente`)

### Modelo de datos — tabla `cliente`

```python
class Client(Base):
    __tablename__ = "cliente"

    id            = Column(Integer, primary_key=True)
    nombre        = Column(String(150), nullable=False)
    telefono      = Column(String(50))
    direccion     = Column(Text)
    email         = Column(String(120))
    ciudad        = Column(String(100))
    estado        = Column(String(100))      # Estado/Departamento del país
    observaciones = Column(Text)
    fecha_registro= Column(Date, server_default=func.current_date())
    created_at    = Column(DateTime, server_default=func.now())
    updated_at    = Column(DateTime, onupdate=func.now())
```

### Esquemas Pydantic — `schemas.py`

| Esquema | Uso | Campos |
|---------|-----|--------|
| `ClientBase` | Base compartida | `nombre`, `telefono`, `direccion`, `email`, `ciudad`, `estado`, `observaciones`, `fecha_registro` |
| `ClientCreate` | Crear cliente | Hereda `ClientBase` |
| `ClientUpdate` | Actualizar cliente | Todos los campos opcionales |
| `ClientResponse` | Respuesta al cliente | `ClientBase` + `id`, `created_at`, `updated_at` |

### Funciones CRUD — `service.py`

| Función | Qué hace |
|---------|----------|
| `get_client(db, id)` | Busca un cliente por ID |
| `get_client_by_email(db, email)` | Busca un cliente por email (para evitar duplicados) |
| `get_clients(db, skip, limit, search)` | Lista clientes con paginación y búsqueda por nombre/email/teléfono |
| `create_client(db, client)` | Crea un cliente (valida email único) |
| `update_client(db, id, data)` | Actualiza solo los campos enviados (`exclude_unset=True`) |
| `delete_client(db, id)` | Elimina el cliente de la BD (borrado físico) |

### Endpoints — todos requieren token JWT

#### `POST /api/v1/cliente/` — Crear cliente

```bash
curl -X POST http://localhost:8000/api/v1/cliente/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "nombre": "Empresa XYZ C.A.",
    "email": "contacto@xyz.com",
    "telefono": "0414-1234567",
    "ciudad": "San Cristóbal",
    "estado": "Táchira",
    "observaciones": "Cliente mayorista"
  }'
```

#### `GET /api/v1/cliente/` — Listar clientes

```bash
# Todos (máximo 100)
curl -X GET "http://localhost:8000/api/v1/cliente/" \
  -H "Authorization: Bearer $TOKEN"

# Con búsqueda y paginación
curl -X GET "http://localhost:8000/api/v1/cliente/?search=xyz&skip=0&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

#### `GET /api/v1/cliente/{id}` — Obtener un cliente

```bash
curl -X GET http://localhost:8000/api/v1/cliente/1 \
  -H "Authorization: Bearer $TOKEN"
```

#### `PUT /api/v1/cliente/{id}` — Actualizar un cliente

Solo envías los campos que quieres cambiar:

```bash
curl -X PUT http://localhost:8000/api/v1/cliente/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"telefono": "0424-7654321"}'
```

#### `DELETE /api/v1/cliente/{id}` — Eliminar un cliente

```bash
curl -X DELETE http://localhost:8000/api/v1/cliente/1 \
  -H "Authorization: Bearer $TOKEN"
# Responde 204 No Content si tuvo éxito
```

---

## 🔄 Flujo Completo: Login → Usar API

```bash
# Paso 1: Obtener el token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=carolina&password=carolina2025$" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# Paso 2: Usar el token en cualquier endpoint protegido
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"

curl -X GET "http://localhost:8000/api/v1/cliente/" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🛒 Módulo de Inventario & Compras (`/api/v1/inventario`, `/api/v1/compras`)

Este módulo maneja el control de stock de los materiales y los ingresos de materiales al almacén a través de compras a proveedores.

### Inventario (`app/modules/inventory/`)
- **Modelo (`model.py`)**:
  - `Inventario`: Almacena la `cantidad` actual de un `material_id` en una `ubicacion_id` específica.
  - `MovimientoInventario`: Bitácora o kardex de todos los movimientos de stock. Registra `tipo` (`ENTRADA`, `SALIDA`, `AJUSTE`, `DAÑO`, `DEVOLUCION`), `cantidad`, `referencia_tipo` (ej. "COMPRA", "PRODUCCION") y `referencia_id`.
- **Servicios (`service.py`)**:
  - `registrar_movimiento(db, movimiento)`: Incrementa o decrementa la cantidad en la tabla `inventario` y crea el registro de auditoría en `movimiento_inventario`. Ejecuta validaciones de stock mínimo antes de descontar.

### Compras (`app/modules/purchases/`)
- **Modelo (`model.py`)**:
  - `Compra`: Registra `proveedor_id`, `moneda_id`, `fecha`, `estado` (`BORRADOR`, `EMITIDA`, `RECIBIDA`, `CANCELADA`) y `observaciones`. Cuenta con la propiedad calculada `@property total` que suma dinámicamente el costo de sus detalles.
  - `DetalleCompra`: Líneas de compra de un `material_id` indicando `cantidad` y `costo_unitario`.
- **Servicios (`service.py`)**:
  - `crear_compra(db, compra)`: Guarda la cabecera y el detalle de la compra. Si el estado es `RECIBIDA`, genera automáticamente un movimiento de inventario de tipo `ENTRADA` en el almacén principal (`ubicacion_id = 1`).
  - `actualizar_compra(db, compra_id, compra_update)`: Actualiza la compra. Si el estado cambia a `RECIBIDA` por primera vez, dispara la entrada de stock en inventario de manera segura (evitando duplicados).

---

## 💵 Módulo de Ventas & Pagos (`/api/v1/venta`, `/api/v1/pago`)

Permite la facturación y el seguimiento de pagos/abonos de clientes.

### Ventas (`app/modules/sales/`)
- **Modelo (`model.py`)**:
  - `Venta`: Vinculado a un `pedido_id` y `cliente_id`. Registra el `total`, la `fecha`, `moneda_id` y el `estado` (`PENDIENTE`, `PAGADA`, `ANULADA`).
  - `DetalleVenta`: Registra el `producto_id`, `cantidad` y `precio` de venta.

### Pagos (`app/modules/sales/`)
- **Modelo (`model.py`)**:
  - `Pago`: Abono o pago completo para una `venta_id`. Registra `monto`, `metodo_pago` (`EFECTIVO_COP`, `EFECTIVO_USD`, `BANCOLOMBIA`, `BANCARIBE`, `ZELLE`), `referencia` y `observaciones`.

---

## 🏭 Módulo de Producción (`/api/v1/production/`)

Controla las órdenes, la evolución del Kanban y el costeo real automatizado.

### Congelamiento de Costo Histórico (`ConsumoMaterial`)
- Al registrar un consumo de material desde el Kanban, el sistema obtiene el `costo_base` actual del material y lo congela persistiendo el valor en `ConsumoMaterial.costo_unitario`.
- Esto garantiza que si los precios de catálogo aumentan en el futuro, el costo real del pedido se mantenga fiel al momento histórico en que se fabricó.

### Liquidación de Mano de Obra (`ManoObra`)
- Cada labor asociada a una etapa Kanban cuenta con un indicador `pagado` (booleano).
- Al finalizar una tarea (por ejemplo, ebanistería), se registra la mano de obra. Mediante `PUT /api/v1/production/mano-obra/{id}/pagar` se confirma el pago, lo cual dispara la afectación al reporte mensual de egresos reales.

---

## 📊 Módulo de Reportes & Dashboard (`/api/v1/reports`, `/api/v1/dashboard`)

Expone consultas consolidadas e información financiera clave.

### Reportes (`app/modules/reports/`)
- **Endpoints (`router.py`)**:
  - `GET /api/v1/reports/pnl?mes=YYYY-MM`: Retorna el balance de Pérdidas y Ganancias del mes, agrupado por moneda. **Fórmula de Egresos:** Suma de `Gasto` fijos + Compras en estado `RECIBIDA` + Mano de Obra marcada como `pagado = True`.
  - `GET /api/v1/reports/rentabilidad-producto`: Compara el costo promedio de producción (extraído de órdenes finalizadas de `CostoProduccion` utilizando el `costo_unitario` congelado de los materiales) contra el precio promedio de venta real en `DetalleVenta` para estimar el margen por producto.
  - `GET /api/v1/reports/alertas-stock`: Listado de materiales cuyo stock en cualquier ubicación está bajo un determinado umbral.

### Dashboard (`app/modules/dashboard/`)
- **Endpoints (`router.py`)**:
  - `GET /api/v1/dashboard/metrics`: Retorna métricas generales para la página de inicio (pedidos activos, órdenes de producción activas en Kanban, número de alertas de stock e ingresos totales del mes actual por moneda).

---

## 🗺️ Mapa de todos los endpoints

### 🔐 Autenticación

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `GET` | `/` | Mensaje de bienvenida | ❌ |
| `POST` | `/api/auth/register` | Registrar nuevo usuario | ❌ |
| `POST` | `/api/auth/login` | Login — devuelve `access_token` + `refresh_token` | ❌ |
| `POST` | `/api/auth/refresh` | Renovar tokens con el refresh token | ❌ |
| `GET` | `/api/auth/me` | Ver datos del usuario autenticado (incluye roles) | ✅ |
| `GET` | `/api/auth/roles` | Listar todos los roles disponibles | ✅ |
| `POST` | `/api/auth/usuario/{id}/roles/{rol_id}` | Asignar rol a usuario | ✅ Admin |
| `DELETE` | `/api/auth/usuario/{id}/roles/{rol_id}` | Quitar rol de usuario | ✅ Admin |

### 👥 Clientes

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/cliente/` | Crear cliente | ✅ |
| `GET` | `/api/v1/cliente/` | Listar clientes (con búsqueda y paginación) | ✅ |
| `GET` | `/api/v1/cliente/{id}` | Ver un cliente | ✅ |
| `PUT` | `/api/v1/cliente/{id}` | Actualizar cliente | ✅ |
| `DELETE` | `/api/v1/cliente/{id}` | Eliminar cliente | ✅ |

### 📦 Catálogos

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `GET/POST/PUT/DELETE` | `/api/v1/area/` | CRUD de áreas de producción | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/cargo/` | CRUD de cargos | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/tipo-producto/` | CRUD de tipos de producto | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/unidad-medida/` | CRUD de unidades de medida | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/moneda/` | CRUD de monedas | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/ubicacion/` | CRUD de ubicaciones | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/tipo-gasto/` | CRUD de tipos de gasto | ✅ |
| `GET/POST/PUT/DELETE` | `/api/v1/rol/` | CRUD de roles | ✅ |

### 🪑 Productos & Materiales

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/producto/` | Crear producto | ✅ |
| `GET` | `/api/v1/producto/` | Listar productos | ✅ |
| `GET` | `/api/v1/producto/{id}` | Ver producto | ✅ |
| `PUT` | `/api/v1/producto/{id}` | Actualizar producto | ✅ |
| `DELETE` | `/api/v1/producto/{id}` | Eliminar producto | ✅ |
| `POST` | `/api/v1/material/` | Crear material | ✅ |
| `GET` | `/api/v1/material/` | Listar materiales | ✅ |
| `GET` | `/api/v1/material/{id}` | Ver material | ✅ |
| `PUT` | `/api/v1/material/{id}` | Actualizar material | ✅ |
| `DELETE` | `/api/v1/material/{id}` | Eliminar material | ✅ |

### 🚚 Proveedores

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/proveedor/` | Crear proveedor | ✅ |
| `GET` | `/api/v1/proveedor/` | Listar proveedores | ✅ |
| `GET` | `/api/v1/proveedor/{id}` | Ver proveedor | ✅ |
| `PUT` | `/api/v1/proveedor/{id}` | Actualizar proveedor | ✅ |
| `DELETE` | `/api/v1/proveedor/{id}` | Eliminar proveedor | ✅ |

### 👷 Empleados

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/empleado/` | Crear empleado | ✅ |
| `GET` | `/api/v1/empleado/` | Listar empleados | ✅ |
| `GET` | `/api/v1/empleado/{id}` | Ver empleado | ✅ |
| `PUT` | `/api/v1/empleado/{id}` | Actualizar empleado | ✅ |
| `DELETE` | `/api/v1/empleado/{id}` | Eliminar empleado | ✅ |

### 📋 Cotizaciones

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/cotizacion/` | Crear cotización | ✅ |
| `GET` | `/api/v1/cotizacion/` | Listar cotizaciones | ✅ |
| `GET` | `/api/v1/cotizacion/{id}` | Ver cotización | ✅ |
| `PUT` | `/api/v1/cotizacion/{id}` | Actualizar cotización | ✅ |
| `PUT` | `/api/v1/cotizacion/{id}/estado` | Cambiar estado (`BORRADOR`, `ENVIADA`, `APROBADA`, `RECHAZADA`) | ✅ |
| `DELETE` | `/api/v1/cotizacion/{id}` | Eliminar cotización | ✅ |

### 🛍️ Pedidos

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/pedido/desde-cotizacion/{cotizacion_id}` | Convertir cotización aprobada en pedido | ✅ |
| `POST` | `/api/v1/pedido/` | Crear pedido manual | ✅ |
| `GET` | `/api/v1/pedido/` | Listar pedidos | ✅ |
| `GET` | `/api/v1/pedido/{id}` | Ver pedido con detalles | ✅ |
| `PUT` | `/api/v1/pedido/{id}/estado` | Cambiar estado del pedido | ✅ |
| `DELETE` | `/api/v1/pedido/{id}` | Eliminar pedido | ✅ |

### 🏭 Producción (Órdenes + Kanban)

| Método | Ruta | Descripción | ¿Token? |
|--------|------|-------------|---------|
| `POST` | `/api/v1/production/orden/` | Crear orden de producción | ✅ |
| `POST` | `/api/v1/production/orden/desde-pedido/{detalle_pedido_id}` | Crear orden desde detalle de pedido | ✅ |
| `GET` | `/api/v1/production/orden/` | Listar órdenes | ✅ |
| `GET` | `/api/v1/production/orden/{id}` | Ver orden con etapas y costos | ✅ |
| `PUT` | `/api/v1/production/orden/{id}` | Actualizar orden | ✅ |
| `PUT` | `/api/v1/production/orden/{id}/estado` | Cambiar estado de la orden | ✅ |
| `DELETE` | `/api/v1/production/orden/{id}` | Eliminar orden | ✅ |
| `POST` | `/api/v1/production/etapa/` | Crear etapa de producción (Kanban) | ✅ |
| `PUT` | `/api/v1/production/etapa/{id}` | Actualizar etapa | ✅ |
| `PUT` | `/api/v1/production/etapa/{id}/estado` | Mover tarjeta Kanban de estado | ✅ |
| `DELETE` | `/api/v1/production/etapa/{id}` | Eliminar etapa | ✅ |
| `POST` | `/api/v1/production/consumo/` | Registrar consumo de material | ✅ |
| `GET` | `/api/v1/production/consumo/por-orden/{orden_id}` | Listar consumos de una orden | ✅ |
| `DELETE` | `/api/v1/production/consumo/{id}` | Eliminar consumo | ✅ |
| `POST` | `/api/v1/production/mano-obra/` | Registrar mano de obra en una etapa | ✅ |
| `DELETE` | `/api/v1/production/mano-obra/{id}` | Eliminar registro de mano de obra | ✅ |
| `POST` | `/api/v1/production/costo/calcular/{orden_id}` | Calcular y guardar costo total de producción | ✅ |
| `GET` | `/api/v1/production/costo/{orden_id}` | Ver costo calculado de una orden | ✅ |

---

## 🐳 Despliegue con Docker

El proyecto tiene Dockerfiles de producción listos:

| Archivo | Descripción |
|---------|-------------|
| `backend/Dockerfile` | Multi-stage: Python 3.11-slim → instala deps → corre con Uvicorn (2 workers) |
| `frontend/Dockerfile` | Multi-stage: Node 20-alpine → `npm run build` → nginx:alpine sirve el dist |
| `frontend/nginx.conf` | SPA fallback, gzip, caché de 1 año para assets hasheados |
| `docker-compose.yml` | Orquesta DB + backend + frontend con healthchecks y variables desde `.env` |

### Levantar todo en producción

```bash
# 1. Crea el archivo de variables
cp .env.example .env
nano .env   # ← cambia SECRET_KEY y contraseñas

# 2. Construir y levantar
docker compose up --build -d

# 3. Verificar que los servicios están saludables
docker compose ps
```

Esto levanta:
- **PostgreSQL** en el puerto `5432` (con healthcheck)
- **Backend FastAPI** en el puerto `8000` (espera a que la DB esté sana)
- **Frontend React/nginx** en el puerto `80` (sirve la SPA estática)

```
http://localhost        ← Frontend
http://localhost:8000   ← Backend API
http://localhost:8000/docs  ← Swagger UI
```

> ⚠️ En la **primera ejecución** restaura el dump de la BD:
> ```bash
> docker compose exec db psql -U yeikar -d yeikar_db < backend/esquema.sql
> ```

### Desarrollo local sin Docker

```bash
# Terminal 1: Backend
cd backend && source venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## 🛠️ Errores Comunes y Soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `fe_sendauth: no password supplied` | Falta la contraseña en `DATABASE_URL` | Verifica que el `.env` tenga el formato correcto con usuario y contraseña |
| `permission denied for table usuario` | El usuario `yeikar` no tiene permisos de escritura | Ejecuta los `GRANT` como superusuario postgres (ver sección de BD) |
| `{"detail":"Not authenticated"}` | No se envió el token o está vacío | Incluye `-H "Authorization: Bearer $TOKEN"` en el curl |
| `{"detail":"No se pudieron validar las credenciales"}` | El token expiró o está mal formado | Haz login de nuevo para obtener un token fresco |
| `ModuleNotFoundError: No module named 'X'` | Falta instalar una dependencia | `pip install -r requirements.txt` con el `venv` activado |
| `AttributeError: module '...' has no attribute 'X'` | Typo en el nombre de un esquema o función | Busca el nombre exacto en `schemas.py` o `service.py` |
| `NameError: name 'jwt' is not defined` | Falta importar `jwt` de `jose` | `from jose import JWTError, jwt` |
| `Internal Server Error` en `/me` | El objeto SQLAlchemy no puede serializarse directamente | Construir `UsuarioResponse(...)` explícitamente en el router |
| `{"detail":"Not Found"}` | La URL está mal escrita | Verifica el prefijo: auth es `/api/auth/`, clientes es `/api/v1/cliente/` |

---

## 🔨 Cómo Agregar un Nuevo Módulo

El patrón es siempre el mismo. Por ejemplo, para agregar `productos`:

```bash
mkdir -p backend/app/modules/products
touch backend/app/modules/products/model.py
touch backend/app/modules/products/schemas.py
touch backend/app/modules/products/service.py
touch backend/app/modules/products/router.py
touch backend/app/modules/products/__init__.py
```

1. **`model.py`** — Define la clase que mapea a la tabla PostgreSQL.
2. **`schemas.py`** — Define los esquemas Pydantic de entrada y salida.
3. **`service.py`** — Implementa las funciones de lógica de negocio y acceso a datos.
4. **`router.py`** — Define los endpoints FastAPI, importando `get_current_user` para protegerlos.
5. **`main.py`** — Registra el nuevo router:

```python
from app.modules.products.router import router as products_router
app.include_router(products_router, prefix="/api/v1/producto", tags=["productos"])
```

---

## 📋 Estado de los Módulos

| Módulo | Modelo | Esquemas | Servicio | Router | Protegido |
|--------|--------|----------|----------|--------|-----------|
| **Usuarios / Auth** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Clientes** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Catálogos** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Productos & Materiales** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Proveedores** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Empleados** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Cotizaciones** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Pedidos** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Órdenes de Producción** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Etapas (Kanban)** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Consumo de Material** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Mano de Obra** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Costos de Producción** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Inventario & Compras** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Ventas & Pagos** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |
| **Reportes & Dashboard** | ✅ | ✅ | ✅ | ✅ | ✅ JWT |

---

## 🗺️ Próximos Pasos (Roadmap)

📦 Resumen del Backend de YEIKAR ERP
✅ Módulos Backend Completados
Módulo	Estado	Comentario
Autenticación (JWT)	✅	Login, registro, endpoint /me.
Clientes	✅	CRUD completo protegido.
Catálogos (área, cargo, tipo‑producto, unidad‑medida, moneda, ubicación, tipo‑gasto, rol)	✅	CRUD completo.
Productos & Materiales	✅	CRUD completo, relación producto‑material.
Proveedores	✅	CRUD completo.
Empleados	✅	CRUD completo.
Cotizaciones	✅	CRUD + flujo a pedido.
Pedidos	✅	CRUD + conversión desde cotización.
Producción	✅	Órdenes de producción, kanban, consumo de materiales, mano de obra, cálculo de costos.
Ventas & Pagos	✅	Facturación desde pedido entregado, abonos, cuentas por cobrar.
🛠️ Detalles Técnicos
Framework: FastAPI + Uvicorn.
ORM: SQLAlchemy 2.x con modelo declarativo.
Validación: Pydantic v2 schemas.
Autenticación: JWT vía python‑jose, get_current_user usado en todos los routers.
Base de datos: PostgreSQL 15+, esquema completo con 32 tablas, triggers para created_at/updated_at.
Pruebas de integración: Scripts scratch/test_flujo_*.py cubren flujos completos de producción y ventas.
Seguridad: Cumple reglas de mandatory-secure-web-skills (consultas parametrizadas, tokens, control de acceso).
📊 Métricas y Endpoints Clave
Clientes: /api/v1/cliente/
Cotizaciones: /api/v1/cotizacion/
Pedidos: /api/v1/pedido/
Producción: /api/v1/production/orden/, /etapa/, /consumo/, /mano-obra/, /costo/calcular/
Ventas: /api/v1/venta/, /api/v1/pago/, /api/v1/cuentas-cobrar/
Dashboard (pendiente): No existe aún endpoint consolidado.
🔎 Análisis de Próximos Pasos (según resumen del usuario)
Prioridad	Área	Por qué es importante
1	Frontend (React + TS + Tailwind)	Sin UI el ERP no es usable para Carolina y Jackson.
2	Control de Roles (autorización granular)	Permite que administradores creen/eliminan, empleados solo vean/actualicen su área.
3	Dashboard de Métricas	Vista inicial con tarjetas de órdenes activas, stock, ingresos.
4	Alertas Automáticas	Notificaciones de stock bajo o pedidos retrasados.
5	Reportes Financieros Avanzados	P&L, rentabilidad por producto, costos acumulados.
6	Manejo de Personalizaciones de Productos	Ajuste de materiales y costos en cotizaciones.
7	Migraciones Alembic	Versionado de BD para futuros cambios.
8	Tests Unitarios y CI	pytest suite para garantizar calidad continua.
9	Documentación de Usuario Final	Manuales para uso operativo.
10	Despliegue en Producción (Docker Compose, CI/CD)	Entorno productivo en la nube.
🗂️ Siguiente Acción Recomendada
Para avanzar rápidamente, sugiero iniciar con la estructura de carpetas del frontend y diseñar la pantalla de login que consuma el endpoint /api/auth/login. Podemos definir los archivos base (src/App.tsx, src/pages/Login.tsx, src/services/api.ts) y los estilos con Tailwind, sin generar código todavía.

Nota: Si deseas que el agente genere la estructura de carpetas y los archivos de esqueleto, avísame y lo haré.

Documento generado automáticamente para uso interno.

### ✅ Completado

| Módulo | Estado | Fecha |
|--------|--------|-------|
| Autenticación JWT | ✅ Completo | Jun 2026 |
| Clientes | ✅ Completo | Jun 2026 |
| Catálogos | ✅ Completo | Jun 2026 |
| Productos & Materiales | ✅ Completo | Jun 2026 |
| Proveedores | ✅ Completo | Jun 2026 |
| Empleados | ✅ Completo | Jun 2026 |
| Cotizaciones | ✅ Completo | Jun 2026 |
| Pedidos | ✅ Completo | Jun 2026 |
| Órdenes de Producción + Kanban | ✅ Completo | Jun 2026 |
| Consumo de Materiales | ✅ Completo | Jun 2026 |
| Mano de Obra | ✅ Completo | Jun 2026 |
| Costos de Producción | ✅ Completo | Jun 2026 |
| Ventas & Pagos | ✅ Completo | Jun 2026 |
| Inventario & Compras | ✅ Completo | Jun 2026 |
| Finanzas, Gastos & Tasas | ✅ Completo | Jun 2026 |
| Reportes & Dashboard | ✅ Completo | Jun 2026 |

### 🔜 Pendiente (próximas fases)

| Prioridad | Módulo | Descripción |
|-----------|--------|-------------|
| **1** | **Tests automáticos** | Configurar `pytest` en `backend/tests/` con fixtures de BD de prueba. |
| **2** | **Notificaciones push** | Alertas de stock bajo y pedidos retrasados vía WebSocket o email. |
| **3** | **CI/CD** | GitHub Actions: lint + tests + build Docker en cada PR. |
| **4** | **Módulo de Compras frontend** | Página para registrar órdenes de compra a proveedores. |
| **5** | **App móvil** | Vista simplificada para operarios de planta (React Native o PWA). |
## 🖥️ Frontend — Estructura y Componentes (React + TypeScript)

> El frontend está construido con **React 18** y **TypeScript**, usando **Vite** como bundler y **Tailwind CSS** para los estilos. La arquitectura está organizada bajo `src/` siguiendo una separación clara entre páginas (routes), componentes reutilizables y servicios de API.

### Stack Tecnológico Frontend

| Tecnología | Versión | Rol |
|------------|---------|-----|
| React | 18 | Framework de UI |
| TypeScript | 5+ | Tipado estático |
| Vite | 5+ | Bundler y dev server |
| Tailwind CSS | 3 | Utilidades de estilos |
| React Router DOM | 6 | Enrutado SPA |
| Axios | 1+ | Cliente HTTP |
| React Hook Form | 7+ | Gestión de formularios |
| Yup | — | Validación de esquemas |

---

### Árbol de Carpetas

```
frontend/src/
├── components/                   # Componentes UI reutilizables
│   ├── Layout/
│   │   ├── Sidebar.tsx           # Navegación lateral con enlaces a módulos
│   │   ├── Navbar.tsx            # Barra superior con avatar y logout
│   │   ├── DashboardLayout.tsx   # Wrapper del layout autenticado
│   │   └── PrivateRoute.tsx      # Protección de rutas basada en JWT
│   └── UI/
│       ├── DataTable.tsx         # Tabla genérica con paginación, sorting y búsqueda
│       └── Button.tsx            # Botón estilizado (primary, secondary, loading)
├── pages/                        # Vistas de la aplicación (una por ruta)
│   ├── Login.tsx                 # Formulario de autenticación
│   ├── Dashboard.tsx             # Página principal con métricas resumidas
│   ├── Clientes.tsx              # Listado, búsqueda y CRUD de clientes
│   ├── ClienteForm.tsx           # Formulario modal para crear/editar cliente
│   ├── Cotizaciones.tsx          # Vista de cotizaciones con calculadora de costos
│   ├── CotizacionForm.tsx        # Formulario de cotización con totales en tiempo real
│   ├── Pedidos.tsx               # Listado de pedidos con actualización de estado
│   ├── PedidoDetail.tsx          # Vista detallada de un pedido y sus productos
│   ├── ProduccionKanban.tsx      # Tablero Kanban drag-and-drop de órdenes
│   ├── Inventario.tsx            # Inventario con kardex, alertas y movimientos
│   ├── Productos.tsx             # Gestión de productos (solo admins)
│   └── Reportes.tsx              # P&L, rentabilidad, alertas stock con recharts
├── services/                     # Lógica de comunicación con el backend
│   ├── api.ts                    # Axios + interceptor refresh token automático
│   ├── clienteService.ts         # CRUD de clientes
│   ├── cotizacionService.ts      # CRUD de cotizaciones + conversión a pedido
│   ├── pedidoService.ts          # CRUD de pedidos + actualización de estado
│   ├── produccionService.ts      # Órdenes, etapas Kanban, consumos, mano de obra
│   ├── inventarioService.ts      # Stock, movimientos y alertas
│   ├── productosService.ts       # Productos y materiales
│   └── reportesService.ts        # P&L, rentabilidad y alertas de stock
├── types/                        # Interfaces TypeScript de entidades del dominio
│   └── index.ts                  # Cliente, Cotizacion, Pedido, Producto, etc.
├── App.tsx                       # Enrutador principal y layout global
├── main.tsx                      # Punto de entrada, monta <App/> en #root
└── index.css                     # Reset + variables CSS + clases Tailwind personalizadas
```

---

### Descripción de Archivos Clave

#### `src/App.tsx`
- Configura **React Router** con rutas protegidas mediante `<PrivateRoute>`.
- Incluye el **layout** global (`<DashboardLayout>` → `<Sidebar>` + `<Navbar>`).
- Aplica el tema oscuro usando variables CSS en el contenedor raíz.

#### `src/services/api.ts`
- Instancia **Axios** con `baseURL` apuntando al backend FastAPI (`VITE_API_URL`).
- **Interceptor de request**: agrega el token JWT al encabezado `Authorization: Bearer <token>`.
- **Interceptor de response con refresh automático**:
  1. Si el backend responde 401, intenta renovar el token usando el `refresh_token` almacenado en `localStorage` vía `POST /api/auth/refresh`.
  2. Si el refresh tiene éxito, reintenta la petición original transparentemente.
  3. Si el refresh también falla, limpia `localStorage` y redirige a `/login`.
  4. Las peticiones concurrentes que reciben 401 durante un refresh se encolan y se resuelven al obtener el nuevo token.

#### `src/components/Layout/Sidebar.tsx`
- Renderiza enlaces de navegación basados en una constante `NAV_ITEMS`.
- Usa Tailwind para efectos hover, estado activo y animaciones de colapso en móviles.
- Íconos de cada módulo para identificación visual rápida.

#### `src/components/Layout/Navbar.tsx`
- Muestra nombre de usuario, avatar y botón de **logout** (limpia `localStorage` y redirige a `/login`).
- Incluye toggle de modo oscuro/claro.

#### `src/components/Layout/PrivateRoute.tsx`
- Comprueba existencia y validez del token antes de renderizar la ruta solicitada.
- Si el token falta o es inválido, redirige automáticamente a `/login`.

#### `src/components/UI/DataTable.tsx`
- Tabla genérica con soporte para **paginación**, **ordenamiento** y **búsqueda**.
- Recibe `columns` y `data` como props → reutilizable en Clientes, Cotizaciones y Pedidos.

#### `src/pages/Login.tsx`
- Formulario con validación gestionado por **React Hook Form**.
- Al autenticarse exitosamente, guarda el JWT en `localStorage` y redirige al Dashboard.

#### `src/pages/ClienteForm.tsx`
- Formulario gestionado con **React Hook Form** + validación **Yup**.
- Invoca `clienteService.crear()` o `clienteService.actualizar()` según el contexto.
- Muestra toast de éxito/error y cierra el modal al finalizar.

#### `src/pages/Cotizaciones.tsx`
- Contiene el listado de cotizaciones y el formulario de cotización paramétrica embebido en un modal.
- **Cálculo en vivo**: Cuando se selecciona un producto modelo y dimensiones (ancho/largo), llama al endpoint paramétrico en vivo para mostrar el desglose exacto de materiales escalados y costos de producción (mano de obra, materiales, gastos).
- **Inicialización automática**: Autocompleta dimensiones basadas en las propiedades `ancho_base` y `largo_base` del producto modelo al seleccionarlo.
- **Guardado Estructurado**: Almacena la cabecera y el detalle estructurado paramétrico en la tabla `detalle_cotizacion` (dimensiones, costos desglosados y precio).
- **Conversión Directa**: Convierte cotizaciones aprobadas a pedidos de producción directamente enviando los detalles paramétricos estructurados de forma segura, eliminando análisis de expresiones regulares.

#### `src/pages/ProduccionKanban.tsx`
- Tablero Kanban **completamente funcional** con columnas por estado: `PENDIENTE`, `EN_PROCESO`, `TERMINADO`, `CANCELADO`.
- Drag-and-drop nativo (sin librerías externas) para mover órdenes entre columnas.
- Cada tarjeta muestra: nombre del producto, área, prioridad y fecha estimada.
- Al soltar una tarjeta llama a `PUT /api/v1/production/etapa/{id}/estado`.

#### `src/pages/Inventario.tsx`
- Muestra stock actual por material y ubicación.
- Panel de alertas para materiales por debajo del umbral configurable.
- Modal de registro de movimientos (ENTRADA / SALIDA / AJUSTE).

#### `src/pages/Productos.tsx`
- CRUD completo de productos y materiales.
- **Solo visible** para usuarios con rol `Dueño` o `Administrador`.

#### `src/pages/Reportes.tsx`
- Gráficas de P&L (ingresos vs gastos por moneda).
- Tabla de rentabilidad por producto.
- Alertas de stock crítico.

#### `src/types/index.ts`
- Define interfaces TypeScript para entidades del dominio: `Cliente`, `Cotizacion`, `CotizacionItem`, `Pedido`, `DetallePedido`, `Producto`, etc.
- Garantiza tipado seguro en todos los componentes y servicios.

---

### Flujo de Datos Principal

```
Usuario → Login.tsx
    → POST /api/auth/login
    → guarda JWT en localStorage

Cualquier página protegida
    → PrivateRoute valida el token
    → api.ts agrega Bearer Token al header
    → backend FastAPI responde con datos tipados
    → componente actualiza estado local (useState/useReducer)
    → UI re-renderiza con datos frescos
    → react-hot-toast muestra notificación de éxito/error
```

---

### 📐 Lógica Paramétrica de Cotización

El sistema cuenta con un motor de cálculo paramétrico en el backend que calcula las cantidades de materiales para productos personalizados (como camas de ancho y largo no estándar).

```mermaid
sequenceDiagram
    React UI->>FastAPI (Router): POST /api/v1/producto/{id}/calcular-precio?ancho=2.0&largo=1.9&ganancia=40
    FastAPI (Router)->>Productos (Service): calcular_precio_producto(ancho, largo, ganancia)
    Productos (Service)->>Receta DB: Cargar receta del producto (tipos de escala: LINEAL, AREA, ESPACIADO, FIJO)
    Receta DB-->>Productos (Service): Retornar materiales base y fórmulas de escala
    Productos (Service)->>Productos (Service): Aplicar lógica de escala por material según dimensiones dadas
    Productos (Service)-->>FastAPI (Router): Retornar desglose de costos y materiales calculados
    FastAPI (Router)-->>React UI: JSON con costos de materiales, mano obra, indirectos, total y materiales_detalle
```

1. **Tipos de Escala de Materiales**:
   - **LINEAL**: La cantidad escala en proporción directa a la variación de una dimensión (ancho o largo).
   - **AREA**: Escala según el área superficial total del producto personalizado.
   - **ESPACIADO**: La cantidad se calcula en función de un espaciamiento constante (ej. tornillos colocados cada 10 cm).
   - **FIJO**: La cantidad no varía independientemente de las dimensiones (ej. un herraje o manual de uso).

2. **Persistencia Estructurada**:
   Al guardar la cotización, se almacena de forma inmutable el cálculo resultante en `detalle_cotizacion`. Esto asegura que si los costos de materias primas cambian en el inventario o la receta base se actualiza, la cotización histórica guarde la información paramétrica exacta calculada en ese momento, facilitando su conversión exacta a pedido sin discrepancias.

---

### Estilos y Experiencia de Usuario

| Aspecto | Implementación |
|---------|---------------|
| **Framework CSS** | Tailwind CSS con paleta personalizada (`primary: '#D4AF37'` gold industrial) |
| **Tema Oscuro** | Clase `dark` en el contenedor raíz + variables CSS `--bg`, `--text` |
| **Tipografía** | Google Fonts (Inter) para lectura clara en pantallas de trabajo |
| **Micro-animaciones** | `transition-colors`, `duration-200`, hover y focus suaves |
| **Responsividad** | Grid y Flex con breakpoints `sm`, `md`, `lg` |
| **Accesibilidad** | Etiquetas `aria-*`, contraste suficiente, foco visible con outline |

---

### Módulos Frontend Implementados (jun 2026)

| Módulo | Estado | Descripción |
|--------|--------|-------------|
| Autenticación | ✅ Completo | Login, logout, token JWT + refresh token automático |
| Layout principal | ✅ Completo | Sidebar con control por rol, Navbar, DashboardLayout |
| Clientes | ✅ Completo | Listar, crear, editar, eliminar, buscar |
| Cotizaciones | ✅ Completo | Calculadora en tiempo real + flujo a pedido |
| Pedidos | ✅ Completo | Listado, detalle y actualización de estado |
| Producción (Kanban) | ✅ Completo | Drag-and-drop, mover etapas, registrar consumos |
| Inventario | ✅ Completo | Stock, movimientos, alertas, kardex |
| Productos | ✅ Completo | CRUD productos/materiales (solo admins) |
| Reportes | ✅ Completo | P&L, rentabilidad, alertas de stock con gráficas |
| Control de roles | ✅ Completo | Sidebar oculta módulos según rol del JWT |

---

### Variables de Entorno del Frontend

```env
# frontend/.env
VITE_API_URL=http://localhost:8000
```

> ⚠️ El archivo `.env` del frontend **no se sube a git**. Copia `.env.example` y ajusta la URL según el entorno (local, staging o producción).

---

## 🐛 Historial de Resoluciones Críticas (Junio 2026)

Este documento recoge **todos los cambios** realizados recientemente para solucionar los problemas de:
1. Valores `NaN` en la UI de cálculo de costos.
2. Error `422 Unprocessable Content` al crear una cotización.
3. Mensaje de error CORS que aparecía como consecuencia del fallo 500 del backend.
4. **Pedidos no visibles en Kanban de Producción** al cambiar el estado a PRODUCCION.
5. **Error de validación `updated_at: None`** (ResponseValidationError en inventarios, movimientos, tasas de cambio y gastos).
6. **Error 500 por Stock Insuficiente** en registro de consumo, convertido ahora en un controlado `400 Bad Request`.
7. **Error 405 (Method Not Allowed) en GET `/etapa/{id}`**, solucionado agregando el endpoint de consulta de etapa en el backend.
8. **Estado del pedido siempre visualizado como "Aprobado" y con fondo rojo en la UI de Pedidos**, solucionado alineando la lista de opciones y clases de estilo del select de React con los estados en mayúsculas (`APROBADO`, `PRODUCCION`, `TERMINADO`, `ENTREGADO`, `CANCELADO`) de la base de datos.
9. **Kanban de Producción vacío** cuando todas las etapas estaban `COMPLETADA` — se añadió toggle "Ver completadas" y banner de órdenes sin etapa activa.
10. **Error 422 al finalizar orden y calcular costos** — el frontend enviaba un POST sin cuerpo JSON válido; el cálculo se movió al backend dentro de `cambiar_estado_orden_produccion`.
11. **Órdenes `PENDIENTE` invisibles en el banner del Kanban** — el filtro del banner ahora incluye `PENDIENTE`, `EN_PRODUCCION` y `PAUSADA`.

Se detallan los motivos, la arquitectura involucrada, los módulos impactados y las decisiones tomadas, además de una hoja de ruta para futuros trabajos.

---

### 🛠️ Cambios en el Backend
#### Módulo afectado
- **`app/modules/productos/cost_service.py`** – Servicio que calcula los costos de un producto.
- **`app/modules/quotes/router.py`** y **`schemas.py`** – Endpoint `/api/v1/cotizacion/` que persiste la cotización.
- **`app/modules/inventory/schemas.py`**, **`app/modules/tasas_cambio/schemas.py`**, **`app/modules/gastos/schemas.py`** – Esquemas Pydantic para serializar las respuestas.
- **`app/modules/production/router.py`** – Router de producción para consumos y etapas.

#### Principales modificaciones
| Archivo | Cambio | Motivo |
|---|---|---|
| `cost_service.py` | - Se añadió **`materiales_detalle`** como alias de `materiales`.<br>- Cada elemento de material incluye ahora `nombre`, `unidad` (abreviatura de `UnidadMedida`) y `costo_subtotal` (alias de `costo_total`).<br>- Se añadieron alias top‑level: `costo_gastos_indirectos`, `costo_total`, `precio_venta`, `precio_sugerido`. | Alinear la respuesta del API con la interfaz que el frontend espera (`CalculationResult`).
| `schemas.py` (CotizacionCreate/DetalleCotizacionCreate) | No se modificó la definición, pero se verificó que los campos `estado` acepten solo **mayúsculas**. | Refuerzo del `CHECK` de la base de datos.
| `router.py` (quotes) | No se cambió lógica, pero ahora se permite crear cotizaciones con `estado='BORRADOR'` (mayúsculas). | Evitar violación del constraint `cotizacion_estado_check`.
| `inventory/schemas.py` | Se cambió el tipo de `updated_at` a `Optional[datetime] = None` en `InventarioResponse` y `MovimientoResponse`. | Evitar errores `500 ResponseValidationError` cuando un registro de inventario o movimiento tiene `updated_at = NULL` (el valor por defecto tras su creación inicial).
| `tasas_cambio/schemas.py` | Se importó `Optional` y se cambió `updated_at: datetime` a `Optional[datetime] = None` en `TasaCambioResponse`. | Evitar errores 500 en respuestas de tasas de cambio con `updated_at` nulo.
| `gastos/schemas.py` | Se cambió el tipo de `updated_at` a `Optional[datetime] = None` en `GastoResponse`. | Evitar errores 500 en respuestas de gastos con `updated_at` nulo.
| `production/router.py` | - Se envolvió la llamada a `crear_consumo_material` en un bloque `try/except ValueError` para levantar un código `400 Bad Request` en lugar de propagar un error 500.<br>- Se añadió la ruta `GET /etapa/{id}` mapeada a `service.obtener_etapa_produccion`.<br>- Se hizo opcional el body de `POST /costo/calcular/{orden_id}` con `Body(default_factory=CostoProduccionCreate)`. | - Proveer mensajes de error controlados al usuario (ej. "Stock insuficiente").<br>- Soportar la carga de tarjetas individuales en el Kanban de producción (soluciona error 405).<br>- Evitar 422 cuando se invoca el cálculo de costos sin enviar JSON.
| `production/service.py` | - `crear_etapa_produccion`: orden `PENDIENTE` → `EN_PRODUCCION` al crear primera etapa.<br>- `cambiar_estado_orden_produccion`: llama `calcular_y_guardar_costo` al pasar a `FINALIZADA`. | Centralizar la lógica de negocio de finalización y costos en el servidor.

#### Verificación en la BD
- Se confirmó que la tabla `cotizacion` tiene el `CHECK`:
```sql
CHECK (estado IN ('BORRADOR','ENVIADA','APROBADA','RECHAZADA','VENCIDA'))
```
- Se probó la inserción directa con Python (`session_local`) y se obtuvo éxito usando `'BORRADOR'` y falla con `'Borrador'`.

---

### 🎨 Cambios en el Frontend
#### Archivos modificados
- **`frontend/src/services/cotizacionService.ts`** – Servicio que llama al endpoint de cálculo y a la creación de cotizaciones.
- **`frontend/src/pages/Cotizaciones.tsx`** – UI de la lista y edición de cotizaciones.
- **`frontend/src/pages/Pedidos.tsx`** – UI para listar pedidos y actualizar su estado.
- **`frontend/src/pages/ProduccionKanban.tsx`** – Kanban de producción: finalización de órdenes, banner de órdenes pendientes y toggle de etapas completadas.

#### Modificaciones clave
1. **Mapeo robusto de la respuesta** en `cotizacionService.calculatePrice`:
   ```ts
   const result = await axios.post<RawResponse>(url, payload);
   const data = result.data;
   const mapped: CalculationResult = {
     costo_gastos_indirectos: data.costo_gastos_indirectos ?? data.costo_gastos,
     costo_total: data.costo_total ?? data.costo_produccion,
     precio_venta: data.precio_venta ?? data.precio_con_iva,
     materiales_detalle: data.materiales_detalle ?? data.materiales,
     // …fallbacks para evitar undefined → NaN
   };
   ```
   Así evitamos `undefined` y por ende `NaN` en la UI.

2. **Estado en mayúsculas**:
   - En la creación de una cotización (`estado: 'BORRADOR'`).
   - En todas las llamadas `handleUpdateStatus` ahora usan `'ENVIADA'`, `'APROBADA'`, `'RECHAZADA'`.
   - Los condicionales `quote.estado === 'X'` fueron actualizados a los valores en mayúsculas.
   - Se mantuvo una **tabla de mapeo visual** para seguir mostrando `Borrador`, `Enviada`, etc., al usuario.

3. **Corrección de dropdown de estado en Pedidos**:
   - El backend almacena los estados del pedido en mayúsculas (`APROBADO`, `PRODUCCION`, `TERMINADO`, `ENTREGADO`, `CANCELADO`), pero el select en `Pedidos.tsx` usaba opciones en title-case (`'Aprobado'`, `'En producción'`, etc.). Esto causaba que la vista nunca hiciera coincidir el valor actual, mostrando siempre la primera opción ("Aprobado") y aplicando la clase de estilo por defecto (rojo).
   - **Solución:** Se reestructuró `estadosPedido` para usar objetos `{ value, label }` donde `value` es el valor en mayúsculas de la base de datos.
   - Se actualizó el `<select>` para mapear `'COTIZADO'` a `'APROBADO'` (para pedidos recién convertidos de cotización) y comparar las clases de estilo usando los valores en mayúsculas.
   - Se removió el mapeo manual en `handleUpdateStatus` ya que el componente React ahora despacha el valor correcto y preformateado de base de datos.

---

### 🔄 Mapeo de datos entre Backend y Frontend
| Campo Frontend (`CalculationResult`) | Campo Backend (`calcular_costo_producto` response) | Comentario |
|---|---|---|
| `costo_gastos_indirectos` | `costo_gastos` (alias) | Ahora coincide.
| `costo_total` | `costo_produccion` (alias) | Alias agregado.
| `precio_venta` / `precio_sugerido` | `precio_con_iva` (alias) | Alias agregado.
| `materiales_detalle` | `materiales` (alias) | Alias agregado.
| `materiales_detalle[i].nombre` | `material_nombre` (alias) | Alias agregado.
| `materiales_detalle[i].unidad` | `material.unidad_medida.abreviatura` | Nuevo campo.
| `materiales_detalle[i].costo_subtotal` | `costo_total` (alias) | Nuevo campo.

---

### 🐞 Solución de errores existentes
| Error | Causa | Solución |
|---|---|---|
| `NaN` en la UI de cálculo | Campos inexistentes en la respuesta del API. | Se añadió alias y mapeo robusto.
| `422 Unprocessable Content` al guardar cotización | Violation del `CHECK` de `estado` (valor en title‑case). | Se enviaron valores en **UPPERCASE** y se actualizó la UI.
| `CORS` bloqueado | El backend lanzó 500 antes de aplicar el middleware CORS, por lo que el navegador nunca recibió el header. | Solución del 500 (estado) resuelve también el mensaje CORS.
| **Pedidos no visibles en Kanban de Producción** | El cambio de estado del pedido no estaba acoplado a la generación de entidades de producción. | Se inyectó lógica en `actualizar_pedido` para que, si el estado cambia a `PRODUCCION`, se generen automáticamente una `OrdenProduccion` para cada detalle y una `EtapaProduccion` inicial asignada a la primera área (`Ebanistería`).
| **`updated_at: None`** (cuelgues 500 de API) | Los esquemas requerían obligatoriamente un tipo de dato `datetime`. | Se marcó el campo como opcional con valor por defecto de `None`.
| **Error 405 GET `/etapa/{id}`** | Falta de ruta `GET` expuesta en el controlador de FastAPI. | Se implementó el endpoint llamando al servicio local.
| **Estado del pedido bloqueado en "Aprobado" y rojo** | Mismatch de capitalización entre los valores de las opciones (`Aprobado`, `Entregado`) y el valor del backend (`APROBADO`, `ENTREGADO`). | Se separó `value` de `label` en las opciones y se alineó con la base de datos.
| **422 al finalizar orden en Kanban** | El frontend hacía `POST /costo/calcular/{id}` sin body JSON; FastAPI exige body aunque los campos del schema sean opcionales. | El cálculo se movió al backend en `cambiar_estado_orden_produccion`; el frontend solo hace un `PUT` a `/estado?estado=FINALIZADA`.
| **Kanban vacío con etapas completadas** | Filtro `estado !== 'COMPLETADA'` dejaba el array vacío. | Toggle "Ver completadas" + banner de órdenes sin etapa activa.

---

### ✅ Verificación y pruebas realizadas
| Prueba | Herramienta / Comando | Resultado |
|---|---|---|
| Compilación TS | `npm run dev` (vite) | Sin errores.
| Chequeo de tipos | `npx tsc --noEmit` | ✅ OK.
| Linter Python (flake8) | `flake8` en backend | ✅ OK.
| Inserción directa en DB | Script Python con `session_local` | `'BORRADOR'` → éxito, `'Borrador'` → `CheckViolation`.
| Prueba de API con token JWT | Script HTTP (`verify_fixes.py`) | Respuestas exitosas (`200 OK` en etapa/5, `200 OK` en movimientos, `400 Bad Request` en stock insuficiente).
| Llamada al endpoint de cálculo | `cotizacionService.calculatePrice` desde UI | Valores correctos, sin `NaN`.
| Creación de cotización vía UI | UI -> backend | Cotización guardada, tabla actualizada.
| Visualización de estado en Pedidos | UI -> backend | El dropdown de estado renderiza el color del badge y valor correctos según base de datos.

---

### 🔐 Buenas prácticas de seguridad (SecureCoder)
- **Validación de entrada**: Se sigue usando Pydantic (`schemas.py`) para validar los DTOs.
- **Principio de menor privilegio**: Sólo se exponen los campos necesarios en la respuesta del cálculo.
- **CORS**: Middleware configurado con `origins` leídos del `.env` y permite solo los hosts del frontend.
- **Escapado de datos**: Los valores que se muestran en la UI se formatean con `toLocaleString` evitando inserción de HTML.
- **No se introducen nuevas dependencias** sin pasar por `scan_dependencies` (cumple política).

---

### 🚀 Propuestas y hoja de ruta futura
| Área | Acción propuesta | Prioridad |
|---|---|---|
| **Testing** | Añadir pruebas unitarias a `cost_service.calculate_costo_producto` y a los controladores FastAPI con `pytest` y `httpx`. | Alta |
| **Documentación API** | Generar OpenAPI spec y publicarla con Swagger UI (`/docs`). | Media |
| **UX** | Mostrar tooltip explicativo de los estados y de los cálculos (p.ej., desglose de costos). | Media |
| **Internacionalización** | Externalizar textos estáticos a un archivo de traducciones (i18n). | Baja |
| **Refactorización** | Crear un *mapper* centralizado (`utils/response_mapper.ts`) para que cualquier nuevo endpoint siga la misma lógica de alias. | Alta |
| **Seguridad** | Auditar los nuevos campos (`unidad`, `costo_subtotal`) para asegurarse de que no se filtren datos sensibles. | Media |
| **Performance** | Cachear resultados de cálculo cuando los parámetros no cambian (Redis o in‑memory). | Baja |

---

## 🤝 Para el Desarrollador Nuevo

Antes de tocar cualquier código:

1. **Lee esta guía de arriba a abajo.**
2. **Lee [`docs/business/flujo_de_produccion.md`](../business/flujo_de_produccion.md)** para entender el negocio.
3. **Lee [`docs/decisions/adr-001-stack-tecnologico.md`](../decisions/adr-001-stack-tecnologico.md)** para entender por qué se eligió cada tecnología.
4. **Configura tu entorno local** siguiendo la sección "Instalación Local".
5. **Verifica que funciona** haciendo login con `curl` y consultando `/api/auth/me`.
6. Antes de abrir un Pull Request, asegúrate de que el servidor arranca sin errores.

---

## 🏢 Información del Proyecto

| Campo | Valor |
|-------|-------|
| **Empresa** | Comercializadora YEIKAR |
| **Desarrollador principal** | Daniel Castellanos |
| **Inicio del proyecto** | Junio 2026 |
| **Licencia** | Propietario — Uso interno exclusivo |

---

*Última actualización: Junio 2026 — Guía escrita para que hasta un tonto lo entienda y quiera aportar 🛠️*

---

## 🐛 Historial de bugs y correcciones

### Bug #5 — Kanban de Producción aparecía completamente vacío (Junio 2026)

**Síntoma:**  
El usuario veía el dashboard con "2 EN PRODUCCIÓN" pero al entrar a la página de **Kanban de Producción** todas las columnas aparecían vacías ("Arrastra tareas aquí").

**Investigación:**  
Se ejecutó una consulta directa en la base de datos:

```python
# Diagnóstico en BD
ordenes = db.query(OrdenProduccion).all()
# Resultado:
#   Orden #1 | estado=EN_PRODUCCION — Etapas: 4 (todas COMPLETADA)
#   Orden #2 | estado=EN_PRODUCCION — Etapas: 2 (todas COMPLETADA)
```

**Causa raíz:**  
El código en `ProduccionKanban.tsx` filtraba **solo las etapas cuyo estado NO fuera `COMPLETADA`**:

```tsx
// ANTES (problemático)
if (etapa.estado !== 'COMPLETADA') {
  allStages.push(etapa);
}
```

Las 2 órdenes `EN_PRODUCCION` tenían todas sus etapas marcadas como `COMPLETADA` (se hicieron pruebas de flujo), entonces el array resultante era vacío → columnas vacías.

Adicionalmente, el **estado de la orden no se actualizó** al finalizar. Las órdenes seguían en `EN_PRODUCCION` aunque todas sus etapas estuvieran completadas. Esto es un dato inconsistente en la BD de pruebas.

**Correcciones aplicadas:**

1. **Toggle "Ver completadas"** — botón en el header que muestra u oculta las etapas en estado `COMPLETADA`. Por defecto están ocultas para ver solo el trabajo activo.
2. **Banner ámbar de órdenes sin etapa activa** — aparece cuando hay órdenes en `PENDIENTE`, `EN_PRODUCCION` o `PAUSADA` sin ninguna etapa activa. Lista las órdenes afectadas e invita a usar "Añadir Etapa" o "Ver completadas".
   - Se detecta correctamente si una orden tiene etapas pero todas están completadas, o si directamente no tiene etapas.
3. **Estilo visual diferenciado** — las etapas `COMPLETADA` tienen fondo gris claro y opacidad reducida para distinguirlas de las activas.

**Flujo correcto esperado:**

| Acción del usuario | Estado esperado de la orden | Estado esperado de las etapas |
|---|---|---|
| Se crea la orden de producción | `PENDIENTE` | (ninguna etapa aún) |
| Se asigna la primera etapa (ej. Tapizado) | `EN_PRODUCCION` | 1 etapa en `ASIGNADA` |
| El operario inicia la etapa | `EN_PRODUCCION` | 1 etapa en `EN_PROCESO` |
| El operario completa la etapa | `EN_PRODUCCION` | 1 etapa en `COMPLETADA` |
| Se crea la siguiente etapa (ej. Pintura) | `EN_PRODUCCION` | 2 etapas (1 completada, 1 activa) |
| Todas las etapas están completadas | Permanece `EN_PRODUCCION` hasta que el supervisor pulse **Finalizar Orden** | Todas `COMPLETADA` |

> **Decisión de diseño (Opción 1 — Flujo manual):** La orden **no** pasa a `FINALIZADA` automáticamente cuando todas las etapas terminan, porque no todos los productos recorren las mismas áreas. El supervisor decide cuándo la ruta ha concluido y pulsa "Finalizar Orden Completa" en el Kanban.

**Archivos modificados:**

| Archivo | Cambio |
|---|---|
| `frontend/src/pages/ProduccionKanban.tsx` | Eliminado filtro de COMPLETADA, añadido toggle, añadido banner de advertencia, estilo visual para etapas completadas |

---

### Concepto clave: Estado de las órdenes vs etapas

Las **órdenes de producción** y las **etapas** tienen sus propios estados independientes:

- **Orden:** `PENDIENTE` → `EN_PRODUCCION` → `FINALIZADA` (o `CANCELADA`)
- **Etapa:** `ASIGNADA` → `EN_PROCESO` → `COMPLETADA` (o `PAUSADA`)

El Kanban muestra **etapas**, no órdenes directamente. Una orden puede tener múltiples etapas (una por área: Ebanistería, Vidriería, Pintura, etc.). La orden pasa a `FINALIZADA` solo cuando el supervisor pulsa **Finalizar Orden Completa** — no automáticamente al completar la última etapa visible, porque la ruta de cada producto puede variar.

---

### Bug #6 — Error 422 al finalizar orden + visibilidad de órdenes PENDIENTE (Junio 2026)

**Síntomas:**
1. El Dashboard indicaba órdenes activas en producción, pero el banner del Kanban no mostraba órdenes recién creadas (estado `PENDIENTE`).
2. Al pulsar **"Finalizar Orden Completa"**, la primera petición (`PUT …/estado?estado=FINALIZADA`) respondía `200 OK`, pero la segunda (`POST …/costo/calcular/{id}`) fallaba con **`422 Unprocessable Content`** y el usuario veía una alerta de error aunque la orden sí se había cerrado.

---

#### 🔍 Cómo investigar un 422 en FastAPI (guía paso a paso)

Un **422** en FastAPI casi siempre significa: *"lo que me enviaste no cumple el contrato que definí en Pydantic"*. No es un bug de CORS ni de la base de datos; es validación de entrada.

**Paso 1 — Reproduce y abre DevTools (F12 → Network):**
- Filtra por la petición en rojo (status 422).
- Abre la pestaña **Response**. Verás algo como:

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

**Paso 2 — Lee `loc` y `msg`:**
| `loc` | Significado |
|---|---|
| `["body"]` | Falta el cuerpo JSON completo de la petición |
| `["body", "campo_x"]` | El cuerpo llegó, pero falta o es inválido el campo `campo_x` |
| `["query", "estado"]` | Falta un parámetro en la URL (`?estado=…`) |

**Paso 3 — Compara frontend vs backend:**
- **Frontend:** ¿Qué envía `axios.post(url, payload)`? Si `payload` es `undefined` o no se pasa segundo argumento, axios manda la petición **sin cuerpo**.
- **Backend:** En `router.py`, ¿el parámetro del body es obligatorio? Si la firma es `esquema: CostoProduccionCreate` sin valor por defecto, FastAPI **exige** un JSON body aunque todos los campos del schema sean opcionales.

**Paso 4 — Confirma con Swagger (`http://localhost:8000/docs`):**
- Prueba el endpoint sin body. Si devuelve 422 con `loc: ["body"]`, confirmaste la causa.

---

#### 🧠 Causa raíz (este bug concreto)

El flujo anterior en `handleFinalizarOrden` hacía **dos peticiones HTTP**:

```
1. PUT  /produccion/orden/{id}/estado?estado=FINALIZADA   → 200 OK ✅
2. POST /produccion/costo/calcular/{id}                   → 422 ❌
```

La segunda petición fallaba porque:
- El endpoint `POST /costo/calcular/{orden_id}` declaraba `esquema: CostoProduccionCreate` como parámetro de body **obligatorio**.
- El frontend llamaba `api.post(url)` **sin segundo argumento** (sin JSON), o con un body que FastAPI no interpretaba como válido.
- Aunque `CostoProduccionCreate` tiene todos sus campos opcionales (`ganancia_porcentaje`, `costo_gastos`, `precio_impuestos_base`), eso solo aplica **cuando el body existe**. Sin body → 422.

Paradoja: la orden **sí** quedaba en `FINALIZADA` (petición 1 exitosa), pero el usuario veía error por la petición 2.

**Problema adicional de visibilidad:** Las órdenes nuevas nacen en estado `PENDIENTE` (sin etapa automática en Ebanistería, por diseño). El banner del Kanban solo consideraba `EN_PRODUCCION`, así que las órdenes `PENDIENTE` eran invisibles.

---

#### ✅ Solución aplicada

**Arquitectura elegida:** Una sola petición desde el frontend; el backend orquesta estado + costos.

```
ANTES (2 peticiones, frágil):
  React → PUT FINALIZADA → POST calcular costos → ❌ 422

DESPUÉS (1 petición, transaccional en servidor):
  React → PUT FINALIZADA → Backend internamente llama calcular_y_guardar_costo()
```

| Capa | Archivo | Cambio |
|---|---|---|
| **Frontend** | `ProduccionKanban.tsx` | `handleFinalizarOrden` solo hace `PUT …/estado?estado=FINALIZADA`. Eliminada la llamada POST redundante. |
| **Frontend** | `ProduccionKanban.tsx` | Banner incluye órdenes `PENDIENTE`, `EN_PRODUCCION` y `PAUSADA` sin etapa activa. |
| **Backend** | `production/service.py` → `cambiar_estado_orden_produccion` | Si `nuevo_estado == 'FINALIZADA'`, ejecuta `calcular_y_guardar_costo(db, id_orden)` antes del commit. |
| **Backend** | `production/service.py` → `crear_etapa_produccion` | Si la orden está `PENDIENTE`, pasa a `EN_PRODUCCION` al crear la primera etapa. |
| **Backend** | `production/router.py` → `calcular_costo` | Body opcional con `Body(default_factory=CostoProduccionCreate)` para que el endpoint siga usable desde Swagger o scripts sin enviar JSON. |

**Código clave en el backend:**

```python
# production/service.py — dentro de cambiar_estado_orden_produccion
elif nuevo_estado == 'FINALIZADA':
    db_orden.fecha_fin = date.today()
    try:
        calcular_y_guardar_costo(db, id_orden)
    except Exception as e:
        print(f"Error al calcular costos automáticos al finalizar orden {id_orden}: {e}")
```

**Código clave en el frontend:**

```tsx
// ProduccionKanban.tsx — handleFinalizarOrden (versión corregida)
await api.put(`/produccion/orden/${ordenId}/estado?estado=FINALIZADA`);
// Ya no hay: await api.post(`/produccion/costo/calcular/${ordenId}`, { ... });
```

---

#### 📖 Cómo entender lo que hicimos (para el desarrollador)

1. **Separación de responsabilidades:** Finalizar una orden de producción es una **acción de negocio** que implica dos efectos (cambiar estado + calcular costos). Es mejor que el **servidor** coordine ambos en una sola operación, no que el navegador dispare dos HTTP y espere que ambos funcionen.

2. **Por qué el schema "opcional" no bastaba:** En Pydantic/FastAPI, "campos opcionales" ≠ "body opcional". Son dos niveles distintos de validación.

3. **Cómo detectarlo tú mismo la próxima vez:** Si ves 422, abre Network → Response → lee `detail[0].loc`. Si dice `["body"]`, el problema es que no llegó JSON; si dice `["body", "campo"]`, el JSON llegó pero mal formado.

4. **El endpoint POST `/costo/calcular` sigue existiendo** para recalcular costos manualmente (p. ej. desde reportes o con parámetros de ganancia personalizados). Solo dejó de ser necesario en el flujo de "Finalizar Orden" del Kanban.

---

#### 🧪 Cómo verificar que quedó bien

1. Abre Kanban → localiza una orden en el banner ámbar.
2. Pulsa **Finalizar Orden Completa**.
3. En DevTools → Network: debe aparecer **solo un** `PUT` con status `200`.
4. Consulta costos: `GET /api/v1/produccion/costo/{orden_id}` debe devolver el registro calculado.
5. La orden ya no debe aparecer en el banner (estado `FINALIZADA`).

---

### Bug #7 — Prevención de Caída por Integridad Referencial al Eliminar Cotizaciones (Junio 2026)

**Síntoma:**
Intentar eliminar una cotización que ya había sido aprobada y convertida a pedido fallaba con una excepción `ForeignKeyViolation` (HTTP 500) en el backend.

**Investigación y Causa Raíz:**
La tabla `pedido` mantiene una clave foránea que referencia a `cotizacion(id)` con una restricción de eliminación `ON DELETE RESTRICT` en la base de datos de PostgreSQL. Al invocar la eliminación directa de la cotización, la BD rechazaba la consulta lanzando una violación de clave foránea no controlada en el código.

**Solución aplicada:**
1. **Backend (`quotes/service.py`):** Se inyectó una validación en `eliminar_cotizacion` que consulta de forma preventiva si existe un `Pedido` asociado al ID de la cotización antes de proceder a la eliminación. Si se detecta un pedido, lanza un error de lógica de negocio controlado (`ValueError`).
2. **Backend (`quotes/router.py`):** Se envolvió el método de eliminación en un bloque `try/except ValueError` para interceptar la excepción y retornar un código `HTTP 400 Bad Request` con un mensaje descriptivo y amigable para el usuario final en lugar de una caída 500 del servidor.



---

## Feature #1 — Módulo de Ventas y Cobros (Junio 2026)

### Contexto y motivación

El sistema tenía todo el backend de ventas (`/api/v1/venta/`, `/api/v1/pago/`) implementado pero **ninguna pantalla en el frontend** lo exponía al usuario. Como consecuencia, el reporte de P&L en Reportes siempre mostraba ingresos en cero, aunque el negocio estuviera operando.

El flujo financiero real de YEIKAR es:
```
Cotización → Pedido (APROBADO) → pagos durante fabricación → entrega → saldo final
```

### Cambios realizados

#### Backend — `backend/app/modules/sales/service.py`

**Problema 1:** La validación original solo permitía crear una `Venta` cuando el pedido estaba en estado `ENTREGADO`. Esto impedía registrar anticipos o cobros durante la producción.

```python
# Antes (restrictivo)
if pedido.estado != "ENTREGADO":
    raise ValueError("El pedido debe estar en estado ENTREGADO para poder ser facturado.")

# Después (flexible)
estados_facturables = ["APROBADO", "PRODUCCION", "TERMINADO", "ENTREGADO"]
if pedido.estado not in estados_facturables:
    raise ValueError(
        f"El pedido debe estar en estado {', '.join(estados_facturables)} para poder ser facturado. "
        f"Estado actual: {pedido.estado}"
    )
```

**Problema 2:** `EFECTIVO_VES` no estaba en la lista de métodos de pago válidos.

```python
# Lista extendida con bolivares venezolanos
metodos_validos = ['EFECTIVO_COP', 'EFECTIVO_USD', 'EFECTIVO_VES', 'BANCOLOMBIA', 'BANCARIBE', 'ZELLE']
```

#### Frontend — nuevos archivos

**`frontend/src/services/ventaService.ts`** — Servicio con `ventaService` y `pagoService`. También exporta `METODOS_PAGO` para uso consistente en la UI.

**`frontend/src/pages/Ventas.tsx`** — Página con dos pestañas:
1. **Facturas Emitidas:** tabla filtrable por estado con modal de detalle (resumen, progreso de cobro, historial de pagos, formulario de nuevo abono).
2. **Pedidos sin Factura:** pedidos en estados facturables sin factura aún; botón para crear factura eligiendo moneda.

**`Sidebar.tsx` / `App.tsx`** — Ruta `/ventas` y enlace "Ventas y Cobros" en el menú lateral.

### Cómo entender el flujo completo

```
Cotización → Pedido (APROBADO) → Venta (se crea aquí) → Pagos sucesivos → P&L
```

El `estado` de la `Venta` se actualiza automáticamente:
- Sin pagos → `PENDIENTE`
- Pagado parcialmente → `ABONADA`
- Total cubierto → `PAGADA`

### Decisión de diseño: una moneda por factura

Cada `Venta` tiene una sola moneda. Los pagos deben usar esa misma moneda. Esto simplifica el P&L que agrupa ingresos/egresos por moneda (USD / COP / VES).

---

## Feature #2 — Nombre de Producto en Tarjetas del Kanban (Junio 2026)

### Contexto y motivación
Originalmente, las tarjetas del tablero Kanban de producción sólo mostraban "Orden de Producción #ID" en lugar del nombre real del mueble. Para mejorar la usabilidad, se deseaba anidar la información detallada del producto para mostrarla directamente en la tarjeta Kanban.

### Cambios realizados

#### Backend — `app/modules/production/schemas.py`
- Se modificó `DetalleDePedidoBasico` para heredar de `BaseModel` directamente y se reemplazó el campo plano `nombre_producto` con el esquema anidado `producto: Optional[ProductoResponse] = None`.
- Se añadió la relación `orden: Optional['OrdenProduccionResponse'] = None` en `EtapaProduccionResponse` para permitir que las etapas del Kanban expongan toda la información de la orden relacionada, incluido su detalle de pedido y el producto.
- Se ejecutó `EtapaProduccionResponse.model_rebuild()` para resolver referencias circulares/futuras de Pydantic.

#### Backend — `app/modules/production/service.py`
- Se actualizaron las funciones `obtener_orden_produccion` y `obtener_ordenes_produccion` añadiendo `options(joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto))` para evitar el problema de "N+1 select queries" y cargar de forma eager toda la jerarquía de datos.

#### Frontend — `frontend/src/services/produccionService.ts`
- Se definió la interfaz `ProductoBasico` y se actualizó `DetallePedidoBasico` para anidar `producto?: ProductoBasico` en lugar de una propiedad string simple.
- Se añadió la propiedad opcional `orden?: OrdenProduccion` a la interfaz `EtapaProduccion`.

#### Frontend — `frontend/src/pages/ProduccionKanban.tsx`
- Se actualizó el título de la tarjeta en `KanbanCard` para pintar dinámicamente el nombre real del mueble: `stage.orden?.detalle_pedido?.producto?.nombre`. Si no está presente, se usa como fallback `"Orden de Producción #ID"`.

---

## Feature #3 — Cotizaciones con Múltiples Productos (Junio 2026)

### Contexto y motivación
Originalmente, el formulario de creación de cotizaciones estaba restringido a cotizar un único producto/mueble modelo a la vez. Para habilitar que una misma Orden de Producción / Pedido contenga múltiples productos relacionados y fabricar de forma conjunta, se requería rediseñar el formulario de cotizaciones permitiendo registrar múltiples renglones de productos en una única cotización.

### Cambios realizados

#### Frontend — `frontend/src/pages/Cotizaciones.tsx`
- Se implementó la interfaz `CotizacionItemForm` para encapsular las variables de cada renglón cotizado (modelo, dimensiones, ganancia, cantidad, resultado de cálculo local y estado de carga).
- Se modificó la estructura del formulario en el Modal para listar los items agregados dinámicamente usando un array en el estado (`items`).
- Se añadió el botón **"+ Añadir Mueble"** que inserta dinámicamente un renglón nuevo al array.
- Se implementaron botones individuales para **"Eliminar"** cada renglón si se agregan por error.
- Se programó la lógica de cálculo individual asíncrona: cuando cambian las dimensiones, ganancia o modelo de cualquier fila, se calcula el subtotal de manera independiente enviando el llamado a `cotizacionService.calculatePrice`.
- Se recalculan automáticamente en el lateral derecho de la vista los totales globales sumados (Costo total de producción, materiales, mano de obra y el precio de venta final sugerido).
- Al guardar la cotización, se construye el DTO con el array de `detalles` para ser procesado por el backend y crear la cotización con múltiples items, la cual puede posteriormente convertirse directamente a un pedido multi-mueble.


---

## Feature #4 — Control de Acceso por Roles (Julio 2026)

### Contexto y motivación
Carolina (dueña) necesitaba que cada empleado viera solo las secciones relevantes a su función. Un operario de fletes no debería ver Producción, y un operario de producción no debería ver Inventario ni Cotizaciones.

### Roles implementados

| Rol              | Rutas visibles                                                  |
|------------------|-----------------------------------------------------------------|
| `Dueño`          | Todo el sistema                                                 |
| `Administrador`  | Todo el sistema (equivalente a Dueño)                           |
| `Fletes`         | `/dashboard`, `/pedidos`, `/envios`                             |
| `Producción`     | `/dashboard`, `/produccion`                                     |
| `Inventario`     | `/dashboard`, `/inventario`, `/productos`                       |
| `Ventas`         | `/dashboard`, `/clientes`, `/cotizaciones`, `/pedidos`, `/ventas` |

### Cambios realizados

#### Frontend — `frontend/src/components/Layout/Sidebar.tsx`
- Se añadió el mapa `rolePaths` que asocia cada nombre de rol con la lista de rutas que le son accesibles.
- El sidebar filtra dinámicamente `menuItems` conservando solo los ítems cuyo `path` está permitido para el rol del usuario autenticado.
- Se añadió el ítem **"Gestión de Usuarios"** (`/usuarios`) visible únicamente para `Dueño` y `Administrador`.

#### Frontend — `frontend/src/pages/Dashboard.tsx`
- Las tarjetas KPI, botones de acceso rápido y alertas de stock/retrasos se renderizan condicionalmente según el rol del usuario:
  - `Fletes`: ve solo métricas de envíos y pedidos pendientes.
  - `Producción`: ve el estado del Kanban y alertas de órdenes retrasadas.
  - `Inventario`: ve niveles de stock y alertas de producto bajo mínimo.
  - `Dueño` / `Administrador` / `Ventas`: ven el panel completo.

---

## Feature #5 — Filtros Históricos en Cotizaciones y Pedidos (Julio 2026)

### Contexto y motivación
"Que desaparezcan mensualmente y se vayan a una caja de almacenamiento": el panel activo debía mostrar solo el mes en curso, pero conservar el historial consultable con filtros de mes y año.

### Comportamiento por defecto
Todos los endpoints de lista usan `solo_mes_actual=True` por defecto: solo devuelven registros del mes y año actuales según `date.today()`.

### Parámetros de query añadidos

| Parámetro         | Tipo   | Default | Descripción                                              |
|-------------------|--------|---------|----------------------------------------------------------|
| `solo_mes_actual` | `bool` | `true`  | Limita al mes en curso                                   |
| `mes`             | `int`  | `null`  | Mes específico (1–12); tiene prioridad sobre `solo_mes_actual` |
| `anio`            | `int`  | `null`  | Año específico (2000–2100)                               |

### Lógica de filtrado (Backend)

```python
# En quotes/service.py y orders/service.py
if mes is not None or anio is not None:
    if mes is not None:
        query = query.filter(extract('month', Model.fecha) == mes)
    if anio is not None:
        query = query.filter(extract('year', Model.fecha) == anio)
elif solo_mes_actual:
    today = date.today()
    query = query.filter(
        extract('month', Model.fecha) == today.month,
        extract('year', Model.fecha) == today.year
    )
# Si solo_mes_actual=False y sin mes/anio → devuelve todo
```

### Cambios realizados

#### Backend
- `backend/app/modules/quotes/router.py` — parámetros `solo_mes_actual`, `mes`, `anio` añadidos al endpoint `GET /cotizacion/`.
- `backend/app/modules/quotes/service.py` — lógica de filtrado con `extract()` de SQLAlchemy.
- `backend/app/modules/orders/router.py` — mismos parámetros para `GET /pedido/`.
- `backend/app/modules/orders/service.py` — misma lógica.

#### Frontend
- `frontend/src/services/cotizacionService.ts` — método `getAll` extendido con `soloMesActual`, `mes`, `anio`.
- `frontend/src/services/pedidoService.ts` — ídem para pedidos.
- `frontend/src/pages/Cotizaciones.tsx` — checkbox "Historial Completo" + selectores de mes/año que se activan al marcarlo.
- `frontend/src/pages/Pedidos.tsx` — misma interfaz de filtros.

---

## Feature #6 — Panel de Gestión de Usuarios y Roles (Julio 2026)

### Contexto y motivación
Carolina necesitaba poder crear cuentas para su equipo, asignarles roles, activarlas/desactivarlas, y ver cuándo fue el último acceso de cada usuario, todo desde una pantalla administrativa sin tocar la base de datos directamente.

### Endpoints de administración añadidos

Todos requieren rol `Dueño` o `Administrador`. Se registraron en `backend/app/modules/users/router.py`.

| Método   | Ruta                                    | Descripción                         |
|----------|-----------------------------------------|-------------------------------------|
| `GET`    | `/api/auth/users`                       | Lista todos los usuarios            |
| `POST`   | `/api/auth/users`                       | Crea un nuevo usuario               |
| `PUT`    | `/api/auth/users/{id}/status`           | Activa o desactiva un usuario       |
| `DELETE` | `/api/auth/users/{id}`                  | Elimina un usuario                  |
| `POST`   | `/api/auth/usuario/{id}/roles/{rol_id}` | Asigna un rol a un usuario          |
| `DELETE` | `/api/auth/usuario/{id}/roles/{rol_id}` | Revoca un rol de un usuario         |
| `GET`    | `/api/auth/roles`                       | Lista todos los roles del sistema   |

> **Seguridad:** Un usuario no puede desactivar ni eliminar su propio perfil. El campo email usa `EmailStr` de Pydantic (valida TLDs reales; `.test` es rechazado correctamente).

### Cambios realizados

#### Backend — `backend/app/modules/users/router.py`
- Corrección del typo `service.create_user` → `service.crear_usuario` en el endpoint público `/register`.
- Nuevos endpoints de administración de usuarios (ver tabla arriba).

#### Frontend — `frontend/src/pages/Usuarios.tsx` *(archivo nuevo)*
- Grid premium de usuarios con indicadores de estado (activo/inactivo), último acceso y badge de roles.
- Modal de creación de usuario con validación de campos.
- Pills de roles clickeables para asignar/revocar permisos sin recargar la página.
- Botón de toggle activo/inactivo por usuario.
- Botón de eliminación con confirmación.

#### Frontend — `frontend/src/App.tsx`
- Import de `Usuarios` añadido.
- Ruta `/usuarios` registrada dentro de `<PrivateRoute>` + `<DashboardLayout>`.

---

## Suite de Pruebas de Integración (Julio 2026)

Se creó `backend/test/test_integracion_api.py` con **19 casos de prueba automáticos** que cubren:

1. **Autenticación** — health check, login correcto, `/me`, login incorrecto → 401, refresh token.
2. **Gestión de usuarios** — listar usuarios, listar roles, crear usuario de prueba, desactivar, reactivar, asignar rol, revocar rol, eliminar.
3. **Filtros históricos** — cotizaciones del mes actual, historial completo, filtro por mes/año; lo mismo para pedidos.

### Cómo ejecutar

```bash
cd backend

# El servidor debe estar corriendo en otro terminal:
# uvicorn app.main:app --port 8000 --reload

./venv/bin/python test/test_integracion_api.py
```

### Resultado esperado

```
═══════════════════════════════════════════════════════
  RESULTADO FINAL: 19 pruebas ejecutadas
  ✅  Aprobadas : 19
  ❌  Fallidas  : 0
═══════════════════════════════════════════════════════
```

---

## Historial de Cambios

| Fecha    | Versión | Cambio                                                       |
|----------|---------|--------------------------------------------------------------|
| Jun 2026 | —       | Kanban nombre real del producto en tarjeta                   |
| Jun 2026 | —       | Cotizaciones multi-producto                                  |
| Jul 2026 | —       | Control de acceso por roles (Sidebar + Dashboard adaptativo) |
| Jul 2026 | —       | Filtros históricos mensuales en Cotizaciones y Pedidos       |
| Jul 2026 | —       | Panel de Gestión de Usuarios y Roles (`/usuarios`)           |
| Jul 2026 | —       | API de administración de usuarios (CRUD + roles)             |
| Jul 2026 | —       | Suite de pruebas de integración (19 tests)                   |
| Jul 2026 | —       | Motor de Cotización Inteligente (IQE) — MVP                  |

---

## 🤖 Motor de Cotización Inteligente (IQE)

> **Módulo:** `backend/app/modules/quotes/intelligent_*`  
> **Estado:** MVP funcional (Jul 2026)  
> **Objetivo:** Reducir el tiempo de cotización de 1-3 días a 10-30 minutos.

### Filosofía del sistema

```
La IA interpreta.   →   El ERP calcula.   →   El vendedor decide.
```

**La IA NUNCA calcula costos, cantidades, IVA ni márgenes.**  
Solo extrae atributos visuales del mueble y devuelve un JSON estricto.  
Todo cálculo financiero lo sigue haciendo `cost_service.py` con precios del inventario actual.

---

### Flujo completo

```
1. Vendedor sube foto del mueble
          ↓
2. VisionProvider (GPT-4o) → analiza imagen → devuelve JSON de atributos
          ↓
3. PAUSA OBLIGATORIA: vendedor revisa y confirma/corrige atributos
          ↓
4. SimilarityEngine (Python puro) → cosine similarity → Top 3 camas históricas
          ↓
5. Vendedor selecciona la más parecida
          ↓
6. cost_service.py → escala cantidades → precios del inventario actual → borrador editable
          ↓
7. Vendedor ajusta cantidades/opcionales → recálculo en tiempo real
          ↓
8. Genera cotización final
```

---

### Estructura de archivos del módulo

```
backend/app/modules/quotes/
├── vision_provider.py          ← Interfaz abstracta VisionProvider + FurnitureAttributes (GENÉRICO)
├── gpt_vision_provider.py      ← Implementación concreta con OpenAI GPT-4o
├── similarity_engine.py        ← Motor de similitud coseno para CUALQUIER tipo de mueble
├── intelligent_schemas.py      ← Schemas Pydantic de entrada/salida del IQE
├── intelligent_router.py       ← 5 endpoints FastAPI del IQE
├── prompts/
│   └── vision_prompt.md        ← System prompt (editable sin tocar código, soporta todos los tipos)
│
│── model.py                    ← Modelos existentes + CotizacionAnalisisIA + CotizacionDetalleMaterial
backend/app/modules/productos/
│── model.py                    ← Modelos existentes + CamaHistoricaAtributos (legacy) + MuebleAtributos (genérico) + MaterialSinonimo
backend/scripts/
├── importar_atributos_historicos.py   ← Clasifica las 63 camas históricas (legacy, solo camas)
├── importar_sinonimos_materiales.py   ← Carga sinónimos de materiales
```

---

### Tablas de base de datos creadas

| Tabla | Propósito |
|---|---|
| `cama_historica_atributos` | **LEGACY**: 63 camas históricas importadas. Solo camas. Mantenida por compatibilidad. |
| `mueble_atributos` | **GENÉRICA**: Atributos para CUALQUIER tipo de mueble. Nueva tabla desde Jul 2026. |
| `cotizacion_analisis_ia` | Registro de cada análisis de imagen (trazabilidad completa) |
| `material_sinonimo` | Normalización del catálogo: mapea variantes de nombres al material canónico |
| `cotizacion_detalle_material` | Receta editable por cotización (editar cantidades sin tocar receta maestra) |

Migraciones aplicadas:
- `530ad3bcdb72_intelligent_quotes.py` — tablas originales
- `a1b2c3d4e5f6_add_mueble_atributos.py` — tabla genérica (Jul 2026)

---

### Endpoints disponibles

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/v1/intelligent-quotation/health` | Estado del módulo y configuración activa |
| `POST` | `/api/v1/intelligent-quotation/analyze-image` | Sube imagen → extrae atributos con IA |
| `POST` | `/api/v1/intelligent-quotation/find-similar` | Atributos validados → Top 3 estructuras similares |
| `POST` | `/api/v1/intelligent-quotation/create-draft` | Estructura seleccionada → borrador editable con costos actuales |
| `POST` | `/api/v1/intelligent-quotation/recalculate` | Borrador modificado → recálculo instantáneo |

---

### Configuración de entorno (.env)

```bash
# Motor de Cotización Inteligente (IQE)
OPENAI_API_KEY=sk-...           # API Key de OpenAI
OPENAI_VISION_MODEL=gpt-4o      # Modelo de visión (gpt-4o, gpt-4o-mini, etc.)
IQE_VISION_PROVIDER=gpt         # 'gpt' | 'gemini' (desacoplado por diseño)
IQE_CONFIANZA_MINIMA=0.70       # Si la IA tiene < 70% confianza, se pide revisión humana
```

> [!IMPORTANT]
> Nunca poner la `OPENAI_API_KEY` real en el `.env.example` ni en Git.  
> El `.env` está en `.gitignore`. Usar el `.env.example` como plantilla.

---

### Cambiar el proveedor de IA

El sistema está completamente desacoplado del proveedor. Para cambiar de GPT a Gemini:

1. Cambiar en el `.env`:
   ```
   IQE_VISION_PROVIDER=gemini
   ```
2. Implementar `GeminiVisionProvider(VisionProvider)` en `gemini_vision_provider.py`.
3. Registrarlo en `_get_vision_provider()` de `intelligent_router.py`.

El ERP, la base de datos y el motor de costeo no se tocan.

---

### Cómo el motor de similitud decide el Top 3

Cada cama histórica se representa como un vector de 6 dimensiones:

```python
[tapiceria, nocheros, espejo, luces, patas, estilo]
# Ejemplo: cama tapizada moderna con nocheros, sin espejo, sin luces, patas madera:
[1.0, 1.0, 0.0, 0.0, 0.5, 0.0]
```

El score es la **similitud de coseno** entre el vector del mueble nuevo y cada histórico.  
No usa IA. No usa embeddings. Solo matemáticas básicas → resultado en milisegundos.

Si el score más alto es `< 0.40`, el sistema muestra de todas formas las más cercanas y marca la cotización como **"estructura nueva"** para que el vendedor construya la receta manualmente.

---

### Scripts de datos

#### Poblar atributos históricos

```bash
cd backend
venv/bin/python3 scripts/importar_atributos_historicos.py
```

Clasifica automáticamente las camas existentes en la BD usando sus materiales y nombre.  
**Debe correr cada vez que se importan nuevas camas.**

#### Poblar sinónimos de materiales

```bash
cd backend
venv/bin/python3 scripts/importar_sinonimos_materiales.py
```

Carga las variantes de nombres de materiales (ej. "MDF DE 9", "LAM MDF 9", "lamina de 9 mdf" → mismo material canónico).  
**Agregar nuevas variantes directamente en el script antes de correrlo.**

---

### Reglas de negocio del IQE

| Regla | Descripción |
|---|---|
| **R-001** | La IA no puede calcular precios ni cantidades. Nunca. |
| **R-002** | Si `nivel_confianza < 0.70`, el sistema pide revisión humana obligatoria. |
| **R-003** | Los precios históricos son ignorados. Solo se reutiliza la receta (materiales + tipo_escala). |
| **R-004** | El vendedor puede desactivar materiales opcionales (tapicería, gavetas, luces) sin eliminar la receta. |
| **R-005** | Si ninguna estructura supera 40% de similitud, se muestran las más cercanas igual y se registra como "estructura nueva". |
| **R-006** | Cada análisis de imagen queda guardado en `cotizacion_analisis_ia` para auditoría. |

---

### Tipos de mueble soportados

El sistema soporta análisis y cotización de CUALQUIER mueble que fabrica YEIKAR:

| tipo_mueble | Descripción | Histórico disponible |
|---|---|---|
| `cama` | Camas de todos los tamaños y estilos | ✅ 63 registros |
| `nochero` | Mesas de noche | ⬜ Agregar con script |
| `closet` | Closets y roperos | ⬜ Agregar con script |
| `tocador` | Tocadores | ⬜ Agregar con script |
| `armario` | Armarios y alacenas | ⬜ Agregar con script |
| `sala` | Juegos de sala | ⬜ Agregar con script |
| `comedor` | Juegos de comedor | ⬜ Agregar con script |
| `escritorio` | Escritorios y estaciones de trabajo | ⬜ Agregar con script |
| `rack_tv` | Muebles para TV / rack | ⬜ Agregar con script |
| `libreria` | Librerías y estanterías | ⬜ Agregar con script |
| `mueble_bano` | Muebles de baño | ⬜ Agregar con script |
| `otro` | Cualquier mueble no clasificado | ⬜ |

> [!IMPORTANT]
> Para los tipos sin histórico, cuando el vendedor busca similares el sistema responde
> `hay_resultados: false` y el mensaje explica que debe construir la receta manualmente.
> Esto es el comportamiento correcto y esperado.

---

### Cómo agregar históricos de un nuevo tipo de mueble

Cuando YEIKAR tenga productos de otro tipo (ej. closets) en la BD con sus recetas definidas:

```bash
cd backend
venv/bin/python3 -c "
from app.db.session import session_local
from app.modules.productos.model import Producto, MuebleAtributos
from app.modules.quotes.vision_provider import FurnitureAttributes

db = session_local()
closets = db.query(Producto).join(Producto.tipo_producto).filter(...).all()

for prod in closets:
    attrs = FurnitureAttributes(
        tipo_mueble='closet',
        familia_probable='melamina',
        estilo_general='moderno',
        tipo_patas='sin_patas',
        tiene_tapiceria=False,
        tiene_luces=False,
        atributos_extra={'tiene_espejo': False, 'tiene_cajones': True},
        nivel_confianza=1.0,
        observaciones=None,
    )
    row = MuebleAtributos(
        producto_id=prod.id,
        tipo_mueble='closet',
        familia_probable=attrs.familia_probable,
        estilo_general=attrs.estilo_general,
        tipo_patas=attrs.tipo_patas,
        tiene_tapiceria=attrs.tiene_tapiceria,
        tiene_luces=attrs.tiene_luces,
        atributos_extra=attrs.atributos_extra,
        vector_similitud=attrs.to_vector(),
    )
    db.add(row)

db.commit()
print('Closets cargados exitosamente')
"
```

---

### Próximas fases del IQE

| Fase | Contenido | Estado |
|---|---|---|
| **Fase 1-5 (MVP)** | Análisis imagen + similitud + borrador editable + recálculo + persistencia | ✅ Completado |
| **Generalización** | Soporte para cualquier tipo de mueble (closets, comedores, salas...) | ✅ Completado |
| **Fase siguiente** | Script de importación masiva para nuevos tipos de mueble | ⬜ Pendiente |
| **Fase siguiente** | WhatsApp Business API integration | ⬜ Requiere cuenta aprobada |
| **Fase siguiente** | GeminiVisionProvider + benchmark GPT vs Gemini | ⬜ Requiere 300+ cotizaciones |
| **Futuro** | Modelo propio fine-tuned con muebles de YEIKAR | ⬜ Requiere 500+ imágenes |





---

## 🧾 Módulo de Ventas, Facturación Fiscal (SENIAT) y Despachos

> **Última actualización:** Julio 2026

### 📌 Contexto

La Comercializadora Yeikar opera en Venezuela bajo la normativa del **SENIAT** (Servicio Nacional Integrado de Administración Aduanera y Tributaria). Toda factura emitida debe cumplir con los requisitos de forma y fondo establecidos para documentos fiscales válidos.

Dado que las ventas se pueden cotizar y cobrar en distintas monedas (USD, COP, Bs.), el sistema implementa una **capa de conversión a Bolívares (VES)** para la generación de la factura fiscal imprimible, sin alterar la moneda base de la venta interna.

---

### 🏗️ Arquitectura del Módulo de Ventas

| Archivo | Propósito |
|---|---|
| `backend/app/modules/sales/model.py` | Modelos ORM: `Venta`, `DetalleVenta`, `Pago` |
| `backend/app/modules/sales/schemas.py` | Schemas Pydantic para entrada/salida |
| `backend/app/modules/sales/service.py` | Lógica de negocio: crear venta desde pedido, calcular saldos, registrar pagos |
| `backend/app/modules/sales/router.py` | Endpoints REST: `/venta/`, `/pago/`, `/venta/{id}`, `/venta/cuentas-por-cobrar/` |
| `frontend/src/pages/Ventas.tsx` | Página principal: lista facturas, gestiona cobros, genera PDF |
| `frontend/src/services/ventaService.ts` | Tipos TypeScript + funciones de llamada a la API |

---

### 💡 Flujo de Facturación

```
Pedido aprobado
    │
    ▼
[Tab "Pedidos sin Factura"] ──► ModalCrearFactura
    │  • Seleccionar moneda base de la venta
    │  • El backend crea Venta + DetalleVenta desde el pedido
    ▼
Factura PENDIENTE
    │
    ▼
[Tab "Facturas Emitidas"] ──► ModalDetalle
    │  • Ver resumen financiero (Total, Pagado, Saldo)
    │  • Registrar cobros (multi-moneda con TRM)
    │  • Ingresar Tasa de Cambio Bs. para PDF fiscal
    │  • Descargar PDF (Factura Fiscal SENIAT)
    ▼
Estado: ABONADA / PAGADA
```

---

### 📄 Plantilla PDF — Factura Fiscal Oficial SENIAT

El PDF se genera **en el cliente** usando `jsPDF` + `html2canvas` sobre un contenedor HTML oculto (`#pdf-factura-container-{id}`).

#### Estructura del documento:

1. **Encabezado** — Logo, razón social, RIF, dirección, teléfonos, redes sociales (`@mueblesyeikar.fabricantes` / `Muebles Yeikar`)
2. **Recuadro de control** — Tipo de documento ("FACTURA DE VENTA"), N° y N° de Control, fecha de emisión
3. **Datos del Cliente** (SENIAT-conforme):
   - Nombre y Apellido o Razón Social
   - Identificación: `RIF ( )  C.I. ( )` ← **Sin Pasaporte**
   - Domicilio Fiscal y Teléfono
   - Forma de Pago: `Efectivo / Tarjeta de Débito / Tarjeta de Crédito / Otros` ← **Sin Cheque**
4. **Tabla de Productos** — `Cant.` | `Concepto o Descripción` | `P. Unitario (Bs.)` | `Monto Total (Bs.)` ← precios convertidos via `tasaBs`
5. **Desglose Fiscal (pie)** — Cálculos SENIAT en Bs.:
   - Base Imponible al IVA (16%)
   - IVA 16%
   - Monto Total de la Venta
   - IGTF 3%
   - **Total a Pagar (Bs.)**

#### Cálculo de impuestos (en `ModalDetalle`):

```typescript
const tasaBs = parseFloat(tasaBsInput) || 1;          // Tasa ingresada manualmente
const totalBs = Number(detalle.total) * tasaBs;        // Total en Bs.
const baseImponibleBs = totalBs / 1.16;               // Base imponible (sin IVA)
const iva16Bs = totalBs - baseImponibleBs;            // IVA 16%
const totalVentaBs = totalBs;                         // = Base + IVA
const igtf3Bs = totalVentaBs * 0.03;                 // IGTF 3%
const totalAPagarBs = totalVentaBs + igtf3Bs;        // Total final
```

> **Importante:** La tasa de cambio (`tasaBs`) se ingresa manualmente desde la interfaz. Si la moneda base de la venta ya es VES, el sistema auto-establece `tasaBs = 1`.

---

### 💳 Sistema de Pagos Multi-Moneda

Un pedido puede tener cobros en distintas monedas. El sistema maneja la conversión con la **Tasa de Cambio (TRM)**:

| Campo | Descripción |
|---|---|
| `moneda_id` | Moneda en que se realiza el pago |
| `tasa_cambio` | Tasa de conversión respecto a la moneda base de la venta |
| `monto_en_moneda_base` | `monto × tasa_cambio` — el valor normalizado para calcular saldos |

El `saldo_pendiente` se calcula en el backend al consultar `GET /venta/{id}`:

```python
total_pagado = sum(float(p.monto_en_moneda_base) for p in db_obj.pagos)
db_obj.saldo_pendiente = float(db_obj.total) - total_pagado
```

---

### 🚚 Guía de Despacho (Despachos.tsx)

El módulo de despachos también genera PDFs (`#pdf-guia-container-{id}`) con:

1. Encabezado institucional idéntico al de la factura
2. Datos del destinatario / cliente y dirección de entrega
3. Recuadro de transporte (conductor, responsable)
4. Tabla de productos a trasladar (desde `pedido.detalles`)
5. **Resumen de saldo** ← Nuevo bloque:
   - Pedido vinculado (#)
   - Nombre del cliente
   - Estado del pedido
   - Aviso: *"Verificar factura antes de entregar"*
6. Firmas: Conductor / Cliente Conforme / Comercializadora Yeikar

---

### 🔧 Tipos TypeScript relevantes

**`ventaService.ts`**
```typescript
export interface ClienteInfo {
  id: number;
  nombre: string;
  telefono?: string;   // Usado en la plantilla fiscal del PDF
  direccion?: string;  // Domicilio Fiscal en el PDF
}
```

**`pedidoService.ts`** — `Order` tiene `cotizacion_id` (número) pero **no** un objeto `cotizacion` embebido. Para acceder al total estimado, se necesita una llamada separada o enriquecer el schema de `Order` en el backend.

---

### ✅ Checklist para agregar un nuevo tipo de documento fiscal

- [ ] Definir la plantilla HTML oculta con `id="pdf-{tipo}-container-{id}"`
- [ ] Implementar `handleGeneratePdf` con `html2canvas` + `jsPDF`
- [ ] Asegurarse de que el contenedor tenga `width: '215.9mm'` (carta US)
- [ ] Incluir siempre: encabezado oficial, RIF, dirección, redes sociales
- [ ] Para facturas: incluir el bloque de desglose fiscal SENIAT
- [ ] Para guías de despacho: incluir el bloque de resumen de saldo

---

## 🏗️ Rediseño de Estructuras de Costos y Recetas por Secciones (En Diseño)

> **Principio de Negocio Central:** *Adaptar el ERP a la estructura real de los Excel de YEIKAR, no forzar los Excel al ERP.*

### 1. Contexto y Problema Detectado

Históricamente el ERP importaba el Excel como una lista plana de insumos y trataba todas las filas como si fueran materiales con precios fijos. Esto ocasionaba dos grandes fallas:
1. **Precios Congelados y Desactualizados:** Se persistían los costos históricos del Excel, impidiendo que el costo del producto se actualice cuando los insumos suben en el Inventario.
2. **Mezcla de Rubros Heterogéneos:** Se trataba igual a un pliego de MDF que a un costo de mano de obra (hechura) o a un recargo porcentual (gastos indirectos o liquidación de mano de obra).
3. **Pérdida de la Jerarquía de Fabricación:** Cada producto en la práctica está dividido en bloques o áreas productivas (`EBANISTERÍA`, `PINTURA`, `TERMINACIÓN`, `TENDIDO`, `TAPICERÍA`, `NOCHEROS EN CRUDO`, etc.).

### 2. Arquitectura de Datos Propuesta

La estructura del producto se organiza jerárquicamente:

```
                          PRODUCTO (ej. Cama Chamber 2x2)
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        ▼                                                                 ▼
SECCIÓN: EBANISTERÍA                                             SECCIÓN: NOCHEROS EN CRUDO
 ├── Insumos Físicos (MDF 3, Colbón, Grapas)                      ├── Insumos Físicos (Lam MDF 9, Colbón, Grapas)
 ├── Mano de Obra Base (ej. $315.000 incluye M.O + % liquidación) ├── Hechura por Par (ej. $157.500)
 └── Recargo de Gastos Sección (ej. 10% sobre materiales)         └── Recargo de Gastos Sección (ej. 5% sobre materiales)
```

#### Entidades Principales

1. **`seccion_producto`**: Define los bloques productivos pertenecientes a un mueble (`producto_id`, `nombre`, `orden`).
2. **`elemento_seccion`** (Insumos Físicos):
   - `nombre_insumo_original`: Descripción tal cual viene del Excel.
   - `material_id_normalizado`: FK opcional al catálogo de inventario (`NULL` en fase inicial de receta).
   - `cantidad`, `unidad_medida`, `observaciones`.
   - `precio_unitario` y `costo_subtotal`: Permanecen `NULL` / desactivados en la fase de receta pura.
3. **`politica_seccion`** (Reglas de Mano de Obra y Gastos de Sección):
   - `mano_obra_base`: Monto fijo o tarifa asignada a la mano de obra del operario en esa área.
   - `pct_liquidacion_mo`: Porcentaje acumulativo para liquidación del trabajador (ej. 5% sobre M.O. base). *Nota: No es un porcentaje fijo global, varía según el acuerdo o área.*
   - `pct_gastos_seccion`: Porcentaje de recargo de indirectos aplicado exclusivamente sobre la suma de materia prima de esa sección (ej. 10% en Ebanistería Cama, 5% en Nocheros).

### 3. Fases del Plan de Implementación

- **Fase 1: Preparación del Modelo de Datos Interno (DB) [✅ COMPLETADO]**
  - Creadas las tablas `seccion_producto`, `elemento_seccion` y `politica_seccion` en SQLAlchemy (`backend/app/modules/productos/model.py`).
  - Aplicada migración Alembic (`f1dcdf808d98_add_seccion_producto_elemento_seccion_...py`).
- **Fase 2: Motor de Importación Estructurado (Sin Precios Fijos) [✅ COMPLETADO]**
  - Creado script `backend/scripts/importar_recetas_secciones.py`.
  - Importadas exitosamente todas las recetas del Excel histórico hacia el nuevo esquema por secciones.
  - Se desvincularon los precios unitarios e importes fijos del Excel, dejando `precio_unitario = NULL` y extrayendo las políticas reales de mano de obra y porcentajes por área.
- **Fase 3: API & Endpoints Backend [✅ COMPLETADO]**
  - Creados esquemas Pydantic (`PoliticaSeccionResponse`, `ElementoSeccionResponse`, `SeccionProductoResponse`).
  - Endpoints implementados:
    - `GET /api/v1/producto/{producto_id}/receta-estructurada`: Devuelve el árbol completo por secciones.
    - `PUT /api/v1/seccion/{seccion_id}/politica`: Permite editar mano de obra base o porcentajes de recargo por área.
- **Fase 4: Rediseño de la Interfaz Frontend [⏳ EN PROGRESO]**
  - Presentación por tarjetas / bloques de sección en lugar de una lista plana.
  - Separación visual de Materiales Físicos vs. Mano de Obra y Gastos Indirectos.
- **Fase 5: Conexión con Inventario (Valuación Dinámica Futura)**
  - Mapeo de `material_id_normalizado` con el módulo de Inventario para calcular costos en tiempo real en función de los precios vigentes.

---


