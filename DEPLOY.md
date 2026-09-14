# 🚀 YEIKAR en VPS — Guía paso a paso (modo primera vez)

Esta guía te lleva de cero a tener el API de YEIKAR corriendo en tu propio
servidor, con HTTPS y backups diarios contra pérdida de datos y ransomware.

> **Filosofía de la guía:** ningún comando se corre sin entenderlo. Cada paso
> dice *qué es*, *por qué* y *qué hacer*. Si algo falla, no avances: copia el
> error y pregúntale a tu agente IA de confianza (o a Google) hasta entenderlo.

---

## 0. El mapa: qué vamos a montar y por qué

```
 Teléfono/PC del equipo
        │
        ▼
 Vercel (GRATIS) ──────────────  el sitio web (React) con CDN global
        │  llama al API por HTTPS
        ▼
 https://api.tudominio.com
        │
        ▼
 ┌─────────────── VPS Contabo ($5.28/mes) ───────────────┐
 │  Caddy  ──── puerta de entrada: candadito 🔒 automático │
 │  Backend ─── tu API FastAPI (Docker)                    │
 │  Postgres ── la base de datos (Docker, sin acceso       │
 │               público: solo el backend la ve)           │
 │  backup ──── pg_dump diario a las 3:00 a. m.            │
 │  offsite-sync ── copia los backups FUERA del servidor   │
 └────────────────────────┬────────────────────────────────┘
                          ▼ cada hora
              Cloudflare R2 (GRATIS, 10 GB)
              los backups viven aquí, fuera del VPS 🔐
```

**Por qué así:**
- **Vercel** ya funciona y es gratis: el frontend se queda ahí (menos cosas que administrar).
- **El VPS** te da control total del API + BD por una fracción del costo serverless.
- **Backups 3-2-1**: 3 copias (BD en vivo, dump local, dump offsite), 2 medios
  (disco del VPS, bucket externo), 1 fuera del servidor. Si te secuestran el
  VPS (ransomware), el atacante **no puede** borrar el bucket: la credencial
  del VPS solo sabe escribir datos nuevos, nunca destruir versiones viejas.

**Costos totales:** dominio ~$10/**año** + VPS $5.28/**mes** + R2 $0.
**Pérdida máxima ante un desastre:** lo del último día (el dump de las 3 a. m.).

### Glosario express

| Término | Qué es |
|---|---|
| **VPS** | Una computadora alquilada que nunca se apaga, en un datacenter |
| **SSH** | "Entrar" a esa computadora escribiendo desde tu terminal |
| **Docker** | Cajitas empaquetadas con apps ya configuradas (ya lo usan tu `docker-compose.yml`) |
| **DNS** | El directorio telefónico de internet: `api.tudominio.com` → IP de tu VPS |
| **HTTPS/TLS** | El candadito 🔒 — Caddy lo consigue solo, gratis, y lo renueva solo |
| **R2** | Depósito de archivos de Cloudflare, gratis hasta 10 GB |

---

## Paso 0 — Las compras (~30 min)

### 0.1 El dominio (en Cloudflare)

1. Crea cuenta gratis en [dash.cloudflare.com](https://dash.cloudflare.com)
2. **Domain Registration → Register Domains** → busca uno libre (ej. `yeikar.com`, `.com` ≈ $10/año)
3. Paga. En ~5 min el dominio es tuyo. **Todo lo demás (DNS, R2) vive en esta misma cuenta** — por eso Cloudflare y no otro registrador.

### 0.2 El VPS (en Contabo)

1. Crea cuenta en [contabo.com](https://contabo.com)
2. **Cloud VPS 4** ($5.28/mes): 4 vCPU, 8 GB RAM, 100 GB SSD — **sobra** para este ERP.
   - ❌ **NO** actives el toggle "VPS con Auto Backup" (nosotros hacemos backups mejores y gratis)
   - ⚠️ El precio publicitado es con descuento los primeros meses; renueva un poco más caro. Aún así es el mejor precio/hardware.
3. **Región/Datacenter: US East** (la menor latencia desde Venezuela)
4. **SO: Ubuntu 24.04**
5. Te llegará un email con:
   - **IP del VPS** (ej. `207.244.xxx.xxx`) → 📝 anótala
   - **Password de root** → 📝 anótala (la vamos a eliminar en el Paso 1)

> ⏳ El VPS tarda ~10-30 min en aprovisionarse. Perfecto tiempo para un café.

---

## Paso 1 — Primer contacto: SSH y blindaje del VPS (~45 min)

### 1.1 Entrar por primera vez

Desde tu terminal (PowerShell en Windows, o Terminal en Mac/Linux):

```bash
ssh root@TU_IP_DEL_VPS
# La primera vez pregunta "fingerprint... yes/no" → escribe yes
# Luego pide el password del email de Contabo (al escribir no se ve nada, es normal)
```

Ya estás DENTRO de una computadora en un datacenter. Todo lo que escribas ahí se ejecuta allá.

### 1.2 Crear tu usuario (no trabajar como root)

`root` es el usuario todopoderoso: un typo y puedes borrar el sistema. Se crea un usuario normal y se usa `sudo` (poder con permiso explícito) cuando hace falta.

```bash
# Crea el usuario (cámbialo por el nombre que quieras)
adduser daniel          # te pide password nuevo (guárdalo bien)
adduser daniel sudo     # le da permisos de admin
```

### 1.3 Llave SSH (entrar sin password, y más seguro)

Desde TU PC (no en el VPS), genera tu llave:

```bash
ssh-keygen -t ed25519
# Enter, Enter, Enter (valores por defecto están bien)

# Copia tu llave al VPS:
type "$env:USERPROFILE\.ssh\id_ed25519.pub" | ssh root@TU_IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
# (Windows PowerShell) — en Mac/Linux: ssh-copy-id daniel@TU_IP
```

Prueba: `ssh daniel@TU_IP` → debe entrar **sin pedir password**. ✅

### 1.4 Cerrar la puerta abierta (prohibir password y root por SSH)

En el VPS:

```bash
sudo nano /etc/ssh/sshd_config
```

(Nano = editor de texto en terminal. Flechas para moverte, Ctrl+O guardar, Ctrl+X salir.)

Busca y deja así estas líneas (quita el `#` si lo tienen, cambia `yes` por `no`):

```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Reinicia SSH: `sudo systemctl restart ssh`

> ⚠️ **No cierres esta terminal todavía.** Abre una NUEVA y prueba `ssh daniel@TU_IP`. Solo si entra bien, cierra la vieja. (Si te quedas fuera, Contabo tiene consola web de rescate en el panel.)

### 1.5 Firewall: cerrar todo menos lo necesario

```bash
sudo apt update && sudo apt upgrade -y   # actualiza el sistema
sudo apt install -y ufw fail2ban          # firewall + anti-fuerza-bruta

sudo ufw allow OpenSSH     # no cierres SSH o te quedas fuera
sudo ufw allow 80/tcp      # HTTP (Caddy lo usa para pedir el certificado)
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 443/udp     # HTTP/3
sudo ufw enable            # y actívalo
sudo ufw status            # debe listar solo esas reglas
```

`fail2ban` ya queda activo: banea IPs que intentan adivinar contraseñas.

### 1.6 Actualizaciones de seguridad automáticas

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades   # elige "Yes"
```

---

## Paso 2 — Instalar Docker (~10 min)

Docker corre cada pieza de YEIKAR como una "cajita" aislada. Misma receta que ya tienes en `docker-compose.yml`, ahora en el servidor.

```bash
# Instalación oficial de Docker (copiar las 4 líneas juntas)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # permite usar docker sin sudo

# Cierra sesión y vuelve a entrar para que el grupo aplique:
exit
# (vuelves a tu PC) → reconecta:
ssh daniel@TU_IP

# Prueba:
docker run --rm hello-world      # debe decir "Hello from Docker!"
docker compose version           # debe imprimir una versión
```

---

## Paso 3 — Traer YEIKAR y configurar (~30 min)

### 3.1 Clonar el repositorio

```bash
# En el VPS:
cd ~
git clone https://github.com/TU-USUARIO/YEIKAR.git
cd YEIKAR
```

(Si el repo es privado, GitHub te pedirá autenticación: usa un *Personal Access Token* como password — [github.com/settings/tokens](https://github.com/settings/tokens).)

### 3.2 Crear el `.env` de producción

```bash
cp .env.example .env
nano .env
```

Edita estas líneas (genera los secretos con los comandos indicados):

```ini
# Password de la BD — genera uno:  openssl rand -hex 24
DB_PASSWORD=pega-aqui-el-valor-generado

# Clave JWT — genera otro:        openssl rand -hex 32
SECRET_KEY=pega-aqui-otro-valor-distinto

DEBUG=false

# El frontend vive en Vercel: permite SU origen
ALLOWED_ORIGINS=https://yeikar-web.vercel.app

# Primera ronda: SIN dominio, prueba en HTTP simple:
API_DOMAIN=:80
# (Cuando el dominio apunte aquí — Paso 5 — lo cambias a:
#  API_DOMAIN=api.tudominio.com)

FORWARDED_ALLOW_IPS=10.200.0.10
```

> 💡 `openssl rand -hex 24` imprime un string aleatorio; cópialo y pégalo. Los valores de `DB_PASSWORD` y `SECRET_KEY` deben ser **distintos entre sí**.

### 3.3 Levantar el stack

```bash
docker compose --profile backup up -d --build db backend caddy backup offsite-sync
```

(Este comando: construye las imágenes, arranca BD + backend + Caddy + backups. Tarda la primera vez, ~3-5 min.)

Verifica:

```bash
docker compose ps                    # todo debe estar "running/healthy"
curl http://localhost/               # debe responder JSON o HTML del backend
docker compose logs backup           # debe decir el cron instalado (o el dump del arranque)
docker compose logs offsite-sync     # debe decir "Sin credenciales R2 — inactivo" (normal por ahora)
```

🎉 **Tu API ya está vivo en el VPS.** Pruébalo desde tu PC: `http://TU_IP/` (responde lo mismo).

---

## Paso 4 — Conectar el dominio y encender el candado 🔒 (~15 min + espera)

1. En Cloudflare → tu dominio → **DNS → Add record**:
   - Type: `A` · Name: `api` · IPv4: `TU_IP_DEL_VPS`
   - **Proxy status: DNS only** (nube GRIS ⚠️ — si está naranja, el TLS de Caddy se rompe porque Cloudflare intermedia)
2. En el VPS, cambia el dominio en `.env` y recrea Caddy:

```bash
nano .env            # API_DOMAIN=api.tudominio.com
docker compose up -d caddy
```

3. Espera ~2 min y prueba en tu PC:

```bash
curl https://api.tudominio.com/
```

Si responde **sin errores de certificado**, el candado está puesto. Caddy lo
renueva solo, para siempre, sin que vuelvas a tocar nada. 🔒

> Si Caddy no arranca: `docker compose logs caddy`. Casi siempre es que el
> dominio aún no apunta a la IP (el DNS tarda unos minutos en propagarse).

---

## Paso 5 — Migrar la base de datos de Neon al VPS (~15 min)

Tu BD actual vive en Neon (se usa para el backend de Vercel). La copiamos entera:

1. Copia tu *connection string* de Neon: Console → tu proyecto `yeikar` → **Dashboard → Connection Details → copia la URL** (empieza con `postgresql://...neon.tech/...`)

2. En el VPS, exporta y restaura:

```bash
cd ~/YEIKAR

# A) Descarga el dump desde Neon (contenedor desechable con cliente postgres)
docker run --rm -v $(pwd):/tmp postgres:15-alpine \
  pg_dump "postgresql://USUARIO:PASSWORD@ep-xxxx.neon.tech/yeikar?sslmode=require" \
  -Fc -f /tmp/neon.dump

ls -lh neon.dump    # debe pesar ~unos MB (tu BD hoy pesa 22 MB)

# B) Cárgalo en el Postgres del VPS
docker compose exec -T db pg_restore -U yeikar -d yeikar_db \
  --clean --if-exists --no-owner < neon.dump

# Los errores "role does not exist" o "extension" son ignorables.
# Verifica (los números deben coincidir con Neon):
docker compose exec db psql -U yeikar -d yeikar_db -c \
  "SELECT count(*) FROM cotizacion;"
```

3. **No apagues Neon todavía.** Queda como copia histórica y plan B durante 1-2 semanas.

---

## Paso 6 — Apuntar Vercel al nuevo API (~5 min)

1. GitHub → repo → `frontend` → verifica que no haya URL hardcodeada (usa `VITE_API_URL`)
2. Vercel → proyecto **yeikar-web** → Settings → **Environment Variables**:
   - `VITE_API_URL` = `https://api.tudominio.com`
3. **Deployments → … → Redeploy** (para que tome la variable)
4. Abre `https://yeikar-web.vercel.app` → login → todo debe funcionar igual que antes.

> Si el login falla con error de CORS: revisa `ALLOWED_ORIGINS` en el `.env` del
> VPS (debe incluir el dominio exacto de Vercel, con `https://` y sin `/` final),
> luego `docker compose up -d backend`.

5. Cuando todo lleve 1-2 semanas estable: Vercel → proyecto **yeikar-api** → Settings → **pause deployments** (o bórralo). Neon queda solo como archivo histórico.

---

## Paso 7 — Backups offsite contra ransomware 🔐 (~20 min)

### 7.1 Crear el bucket en R2

1. Cloudflare Dashboard → **R2 Object Storage** (primera vez: te pide activar R2, requiere tarjeta pero **10 GB gratis** — tu BD cabe ahí por años)
2. **Create bucket** → nombre: `yeikar-backups` → Create
3. Entra al bucket → **Settings → Object Lifecycle Rules → Add rule**:
   - Apply to: Entire bucket
   - Condition: **Age in days = 90** → Action: **Delete objects**
   - (Los backups viejos se borran solos a los 90 días)
4. Misma pantalla: **Versions: On** ← 🔑 *esto es lo anti-ransomware: aunque alguien borre/reescriba con tu credencial, las versiones anteriores sobreviven 90 días*

### 7.2 Crear la credencial (mínimo privilegio)

1. R2 → **Account API Tokens → Create API Token**
2. Permissions: **Object Read & Write** (NADA más)
3. Specify bucket(s): **Apply to specific buckets only → yeikar-backups**
4. Te muestra 3 valores — copia los 3 AHORA (no se vuelven a mostrar):
   - **Access Key ID** → será `R2_ACCESS_KEY_ID`
   - **Secret Access Key** → será `R2_SECRET_ACCESS_KEY`
   - **Account ID** (arriba de la página R2) → será `R2_ACCOUNT_ID`

> ⚠️ Esta credencial solo sirve para ESCRIBIR y LEER ese bucket. Ni con el VPS
> secuestrado pueden: borrar el bucket, cambiar la regla de lifecycle, ni
> tocar otros buckets.

### 7.3 Activar el sincronizador

En el VPS:

```bash
cd ~/YEIKAR
nano .env    # pega los 3 valores R2_* del paso anterior

docker compose --profile backup up -d offsite-sync

# Debe loggear "sincronizado OK" en ≤1 min:
docker compose logs offsite-sync
```

Verifica en Cloudflare (bucket → Browse Objects): deben aparecer tus dumps. 🎉

### 7.4 Ver que el backup diario funciona

El dump corre a las **3:00 a. m. (hora Venezuela)**. Al día siguiente:

```bash
ls -lh ~/YEIKAR/backups/         # debe existir yeikar_YYYYMMDD_030000.dump
cat ~/YEIKAR/backups/backup.log  # debe decir "OK — dump verificable"
```

---

## Paso 8 — Simulacro de restauración (hazlo HOY y luego cada mes) 🧯

Un backup que nunca se restauró es teoría. Practícalo:

```bash
cd ~/YEIKAR

# 1) Restaura el dump más reciente en una BD desechable
LATEST=$(ls -t backups/yeikar_*.dump | head -1)
docker compose exec -T db psql -U yeikar -d yeikar_db -c "CREATE DATABASE prueba_restore;"
docker compose exec -T db pg_restore -U yeikar -d prueba_restore --no-owner < "$LATEST"

# 2) Verifica que los datos están
docker compose exec db psql -U yeikar -d prueba_restore -c \
  "SELECT count(*) FROM cotizacion; SELECT count(*) FROM usuario;"

# 3) Borra la prueba
docker compose exec db psql -U yeikar -d yeikar_db -c "DROP DATABASE prueba_restore;"
```

✅ Si los conteos coinciden con la BD real: tu red de seguridad funciona.

### 🚨 Si un día pasa lo peor (ransomware / VPS muerto / borrón accidental)

1. Contabo panel → **reinstalar Ubuntu** o crear VPS nuevo
2. Repite Pasos 1-3 de esta guía (30 min)
3. Restaura la BD: descarga el dump del bucket R2 y corre el `pg_restore` del Paso 5-B
4. Pérdida máxima: lo hecho **después de las 3:00 a. m.**

### Snapshot semanal del VPS completo

Contabo panel → tu VPS → **Snapshots → Take snapshot** (tienes 2 gratis).
Házlo los **domingos** (recordatorio en tu celular): captura el sistema entero
(certificados, configuración, docker) y te ahorra repetir los pasos 1-3 en un desastre.

---

## Mantenimiento diario

| Quiero... | Comando (en `~/YEIKAR` del VPS) |
|---|---|
| Actualizar la app (tras `git pull`) | `docker compose up -d --build backend` |
| Ver logs del backend | `docker compose logs -f backend` |
| Ver logs de Caddy (HTTPS) | `docker compose logs -f caddy` |
| Estado de todos los servicios | `docker compose ps` |
| Espacio en disco | `df -h` |
| Ver el log de backups | `cat backups/backup.log` |
| Forzar un backup AHORA | `docker compose exec backup /bin/sh /usr/local/bin/backup.sh` |
| Reiniciar todo | `docker compose --profile backup restart` |

**Regla de oro:** antes de actualizar en producción, `git pull` en tu PC, corre
los tests (`pytest test/ -v`) y `npm run build`. Si pasan, actualiza el VPS.

---

## Checklist final

- [ ] Dominio comprado (Cloudflare) — `api.tudominio.com` apunta al VPS (nube gris)
- [ ] VPS: usuario no-root, SSH con llave, password/root deshabilitados
- [ ] UFW activo (solo 22/80/443) + fail2ban + actualizaciones automáticas
- [ ] `https://api.tudominio.com/` responde con candado 🔒
- [ ] BD migrada desde Neon (conteos coinciden)
- [ ] `VITE_API_URL` en Vercel apunta al API del VPS y el ERP funciona completo
- [ ] Backups locales diarios verificados en `backups/backup.log`
- [ ] Bucket R2 con **versiones ON** + lifecycle 90 días + credencial de solo ese bucket
- [ ] `docker compose logs offsite-sync` dice "sincronizado OK"
- [ ] Simulacro de restauración exitoso (y repetir cada mes)
- [ ] Snapshot Contabo los domingos (recordatorio en el celular)

---

*¿Dudas con un paso? Copia el error completo y pregúntale a tu agente. Entender el error ES el curso.*
