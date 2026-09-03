from fastapi import HTTPException
import os
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Opciones de conexión: permite sobrescribir search_path u otras opciones
# libpq vía la variable PGOPTIONS (p. ej. aislamiento de esquema en E2E).
_extra_options = os.environ.get("PGOPTIONS", "").strip()

# Pooler serverless (PgBouncer de Neon: la URL contiene "-pooler"): no acepta
# parámetros de startup arbitrarios como `options` → statement_timeout se
# configura en Neon (ALTER ROLE ... SET statement_timeout) y aquí se omite.
_url_bd = settings.DATABASE_URL
_es_pooler = "-pooler" in _url_bd or "pgbouncer" in _url_bd
_opciones_finales = _extra_options if _extra_options else (
    None if _es_pooler else "-c statement_timeout=30000"
)
_conn_args = {"options": _opciones_finales} if _opciones_finales else {}

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=4,
    max_overflow=2,
    pool_pre_ping=True,  # crítico con autosuspend (Neon): descarta conexiones muertas
    pool_timeout=5,
    connect_args=_conn_args,
)
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = session_local()
    try:
        try:
            yield db
        except TimeoutError:
            raise HTTPException(status_code=503, detail="Servicio ocupado, reintenta en unos segundos")
    finally:
        db.close()