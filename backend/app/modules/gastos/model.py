from sqlalchemy import Column, Integer, BigInteger, Numeric, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class Gasto(Base):
    __tablename__ = "gasto"

    id = Column(Integer, primary_key=True, index=True)
    tipo_gasto_id = Column(BigInteger, ForeignKey("tipo_gasto.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(Date, nullable=False)
    descripcion = Column(Text, nullable=True)
    monto = Column(Numeric(15,2), nullable=False)
    tasa_cambio = Column(Numeric(15,6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15,2), nullable=False, default=0.0)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    tipo_gasto = relationship("TipoGasto")
    moneda = relationship("Moneda")