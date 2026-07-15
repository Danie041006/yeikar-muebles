from sqlalchemy import Column, String, DateTime, Text, BigInteger
from sqlalchemy.sql import func
from app.db.base import Base

class Proveedor(Base):
    __tablename__ = "proveedor"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(50), nullable=True)
    email = Column(String(150), nullable=True)
    direccion = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
