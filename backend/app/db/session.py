from fastapi import HTTPException
import os
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Opciones de conexión: permite sobrescribir search_path u otras opciones
# libpq vía la variable PGOPTIONS (p. ej. aislamiento de esquema en E2E).
_extra_options = os.environ.get("PGOPTIONS", "").strip()
_conn_options = " ".join(filter(None, [_extra_options, "-c statement_timeout=30000"]))

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=4,
    max_overflow=2,
    pool_pre_ping=True,
    pool_timeout=5,
    connect_args={"options": _conn_options},
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