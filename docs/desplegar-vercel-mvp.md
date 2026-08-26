# Despliegue MVP — Vercel (frontend + backend) y Neon (base de datos)

Guía clic-a-clic para dejar YEIKAR accesible en línea en ~45 minutos.
Pensada para un MVP temporal (< 1 semana). Al final hay sección de **teardown**.

```
Navegador → yeikar-web.vercel.app (Vite estático)
                 └─ rewrite /api/* → yeikar-api.vercel.app (Python/FastAPI)
                                          └─ Neon Postgres (cadena POOLED)
```

---

## 0. Prerrequisitos (5 min)

- Cuenta en [neon.tech](https://neon.tech) y [vercel.com](https://vercel.com)
- Repo conectado: `github.com/Danie041006/yeikar-muebles` (rama `main` al día)
- `pg_dump`/`psql` instalados localmente (ya los tienes)

Genera la SECRET_KEY nueva y guárdala:

```sh
openssl rand -hex 32
```

---

## 1. Neon — base de datos (10 min)

1. neon.tech → **New Project** → nombre `yeikar-mvp`, región cercana (ej. AWS US East), Postgres 17.
2. Dashboard → **Connection string** → pestaña **Pooled** → copiar. Se ve así:
   `postgresql://usuario:pass@ep-x-x-pooler.region.aws.neon.tech/neondb?sslmode=require`
3. Migrar tus datos locales (incluye fotos, usuarios, estructuras):

```sh
chmod +x scripts/deploy/migrar_a_neon.sh
./scripts/deploy/migrar_a_neon.sh "PEGA_AQUI_LA_CADENA_POOLED"
```

Debe terminar mostrando `tablas: ~130`, tus usuarios y `alembic: <head>`.

> Guarda esa cadena: es la `DATABASE_URL` del paso 2.

---

## 2. Vercel — backend "yeikar-api" (15 min)

1. vercel.com → **Add New… → Project** → importa `yeikar-muebles`.
2. **ANTES de Deploy**, configura:
   - **Project Name**: `yeikar-api`
   - **Root Directory**: `backend`
   - **Framework Preset**: `Other`
   - **Build Command**: *(vacío)* · **Output**: *(vacío)* · **Install Command**: *(vacío)*
3. **Environment Variables** (Production):
   | Nombre | Valor |
   |---|---|
   | `DATABASE_URL` | cadena pooled de Neon (`?sslmode=require`) |
   | `SECRET_KEY` | la que generaste con openssl |
   | `DEBUG` | `false` |
   | `ALGORITHM` | `HS256` |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` |
   | `REFRESH_TOKEN_EXPIRE_DAYS` | `7` |
   | `ALLOWED_ORIGINS` | `https://yeikar-web.vercel.app` |
4. **Deploy** → espera el build (~2 min). Anota la URL: `https://yeikar-api.vercel.app`
5. Prueba: abre `https://yeikar-api.vercel.app/api/v1/pedido/` → debe responder `401 {"detail":"Not authenticated"}`.

---

## 3. Vercel — frontend "yeikar-web" (10 min)

1. **Add New… → Project** → mismo repo.
2. Configura:
   - **Project Name**: `yeikar-web`
   - **Root Directory**: `frontend`
   - Framework: detecta **Vite** automáticamente (build `npm run build`, output `dist`)
3. Environment Variables: *ninguna obligatoria* (usa `/api` relativo).
4. **Deploy**.
5. ⚠️ **Una sola línea a editar**: abre `frontend/vercel.json` y reemplaza
   `https://yeikar-api.vercel.app` si tu API quedó con otro nombre. Haz el cambio,
   `git commit` + `git push`, y Vercel redespliega solo.

Prueba: abre `https://yeikar-web.vercel.app`, inicia sesión y navega.

---

## 4. Checklist de humo (5 min)

- [ ] Login con tu usuario real
- [ ] Crear/editar cliente y cotización (con tabla de costos)
- [ ] Kanban de producción carga etapas; abrir una etapa muestra tarifario de MO
- [ ] Nómina → "Ver producción de la semana" trae piezas
- [ ] Subir una foto de producto (adjunto en BD) y verla en el expediente
- [ ] Descargar PDF de cotización/factura (se genera en tu navegador)

---

## Mantenimiento diario

- **Cambios de código**: `git push` → ambos proyectos se redespliegan solos.
- **Cambios que incluyan migración de BD**: correr desde tu PC
  `DATABASE_URL="<neon>" alembic upgrade head` ANTES de hacer push.

## Teardown (< 1 semana)

- Vercel: Settings → Delete Project (en cada uno)
- Neon: Delete Project
- Nada queda facturado; los datos originales siguen intactos en tu PC.

## Riesgos aceptados del MVP

- Cold start ~2–5 s tras inactividad (+ autosuspend de Neon similar)
- Timeout 30 s por request: reportes muy pesados podrían cortarse
- IP compartida tras el proxy: bloqueo de login aplica por igual a todos
- Fotos > 4.5 MB rechazadas (límite body de Vercel; las tuyas se comprimen en cliente)
