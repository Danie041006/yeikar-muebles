# Configuración del Entorno de Desarrollo

Este documento describe paso a paso cómo configurar el entorno para contribuir al proyecto YEIKAR ERP.

## Sistema Operativo

El proyecto se desarrolla en **WSL2 con Debian** (probado) o cualquier distribución Linux. También funciona en macOS y Windows (con WSL2).

## 1. Instalar Python

```bash
# En Debian/Ubuntu
sudo apt update
sudo apt install python3.13 python3.13-venv python3-pip -y

# Verificar
python3 --version  # Debe mostrar 3.13.x

#para instalar Postgresql
sudo apt install postgresql postgresql-contrib -y
sudo service postgresql start


# Crear base de datos
sudo -u postgres psql -c "CREATE DATABASE yeikar;"
sudo -u postgres psql -c "CREATE USER yeikar WITH PASSWORD 'yeikar123';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE yeikar TO yeikar;"

# Restaurar dump
psql -U yeikar -d yeikar -h localhost < ruta/al/dump.sql


para clonar y configurar backend
git clone <repo-url>
cd YEIKAR-ERP/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

#para las variables de entorno
cat > .env << EOF
DATABASE_URL=postgresql://yeikar:yeikar123@localhost:5432/yeikar_db
SECRET_KEY=desarrollo-clave-temporal-123
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
EOF

#para verificar conexión
python -c "from app.db.session import engine; print('OK')"

#ejecutar el servidor
uvicorn app.main:app --reload




#8. Verificar API
Abrir http://localhost:8000/docs en el navegador.

Solución de Problemas Comunes
Error: fe_sendauth: no password supplied
Asegurar que .env contiene la contraseña correcta.

Error: role "yeikar" does not exist
Crear el usuario en PostgreSQL (ver paso 3).

Error: ModuleNotFoundError: No module named 'pydantic_settings'
bash
pip install pydantic-settings
Error de importación circular
Verificar que app/db/base.py declare Base antes de importar modelos.

Herramientas Recomendadas
Editor: VS Code o Antigravity o Windsurf o Cursor con extensiones Python, Pylance, SQLAlchemy

Cliente PostgreSQL: DBeaver, pgAdmin, o psql

Pruebas API: Postman, Insomnia, o curl

Control de versiones: Git con commits convencionales


#Verificar Conexión a la Base de Datos
python -c "from app.db.session import engine; from app.db.base import Base; print('Conexión exitosa')"