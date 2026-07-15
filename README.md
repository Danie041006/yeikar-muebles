# 🏭 YEIKAR ERP

Sistema de gestión empresarial para **Comercializadora YEIKAR**, especializada en fabricación y venta de muebles, camas, colchones y electrodomésticos en Venezuela.

> **¿Quieres contribuir o entender el proyecto?** → Lee la [Guía del Desarrollador](docs/development/guia-desarrollador.md). Está escrita para que cualquiera la entienda.

---

## 🚦 Estado del Proyecto

🚧 **En desarrollo activo**

| Módulo | Estado |
|--------|--------|
| Base de datos PostgreSQL (32 tablas) | ✅ Funcionando |
| Backend FastAPI | ✅ Funcionando |
| Autenticación JWT (login, /me) | ✅ Completado |
| CRUD de Clientes (protegido con token) | ✅ Completado |
| Productos, Proveedores, Empleados | ⏳ Próximamente |
| Órdenes de Producción | ⏳ Próximamente |
| Frontend React + TypeScript | ⏳ Próximamente |

---

## ⚡ Inicio Rápido

```bash
# 1. Clonar
git clone <repo-url> && cd YEIKAR

# 2. Entorno virtual e instalar dependencias
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
nano .env   # Completa DATABASE_URL y SECRET_KEY

# 4. Iniciar servidor
uvicorn app.main:app --reload
```

API disponible en **http://localhost:8000** · Documentación interactiva en **http://localhost:8000/docs**

---

## 🔧 Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.13 + FastAPI 0.115.6 |
| ORM | SQLAlchemy 2.0 + Alembic |
| Base de Datos | PostgreSQL 15+ |
| Autenticación | JWT (python-jose) + bcrypt (passlib) |
| Frontend (futuro) | React + TypeScript + Vite + Tailwind |
| Contenedores | Docker + Docker Compose |

---

## 📚 Documentación

| Documento | Contenido |
|-----------|-----------|
| [Guía del Desarrollador](docs/development/guia-desarrollador.md) | **Empieza aquí.** Todo lo que necesitas para levantar el proyecto y entender el código. |
| [Flujo de Producción](docs/business/flujo_de_produccion.md) | Cómo funciona el negocio: cotización → pedido → producción → venta. |
| [Esquema de Base de Datos](docs/architecture/database-schema.md) | Las 32 tablas y su propósito. |
| [Diagrama ERD](docs/architecture/erd.md) | Relaciones entre tablas. |
| [Decisión de Stack](docs/decisions/adr-001-stack-tecnologico.md) | Por qué se eligió cada tecnología. |
| [Variables de Entorno](docs/setup/variables_de_desarrollo.md) | Configuración del entorno de desarrollo. |

---

## 🗺️ Endpoints Disponibles

| Método | Ruta | Descripción | Token |
|--------|------|-------------|-------|
| `POST` | `/api/auth/login` | Obtener token JWT | ❌ |
| `POST` | `/api/auth/register` | Registrar usuario | ❌ |
| `GET` | `/api/auth/me` | Ver usuario autenticado | ✅ |
| `POST` | `/api/v1/cliente/` | Crear cliente | ✅ |
| `GET` | `/api/v1/cliente/` | Listar clientes | ✅ |
| `GET` | `/api/v1/cliente/{id}` | Ver cliente | ✅ |
| `PUT` | `/api/v1/cliente/{id}` | Actualizar cliente | ✅ |
| `DELETE` | `/api/v1/cliente/{id}` | Eliminar cliente | ✅ |

---

## 📄 Licencia

Propiedad de **Comercializadora YEIKAR** — Uso interno exclusivo.  
Desarrollador: Daniel Castellanos