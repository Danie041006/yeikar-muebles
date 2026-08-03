from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class Client(Base):
    __tablename__ = "cliente"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(50), nullable=False)
    direccion = Column(Text)
    email = Column(String(120))
    ciudad = Column(String(100))
    estado = Column(String(100))
    observaciones = Column(Text)
    fecha_registro = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())