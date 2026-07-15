from sqlalchemy import Column, Integer, BigInteger, Numeric, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base import Base

class TasaCambio(Base):
    __tablename__ = "tasa_cambio"

    id = Column(Integer, primary_key=True, index=True)
    moneda_origen_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    moneda_destino_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    valor = Column(Numeric(15,6), nullable=False)
    fecha = Column(Date, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())