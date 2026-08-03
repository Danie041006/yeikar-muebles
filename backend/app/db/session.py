from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=4,
    max_overflow=2,
    pool_pre_ping=True,
    pool_timeout=5,
    connect_args={"options": "-c statement_timeout=30000"},
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