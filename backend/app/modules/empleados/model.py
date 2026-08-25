from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# Importar cargo para la relacion
from app.modules.catalogos.model import Cargo

class Empleado(Base):
    __tablename__ = "empleado"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    cargo_id = Column(BigInteger, ForeignKey("cargo.id"), nullable=False)
    telefono = Column(String(50), nullable=True)
    activo = Column(Boolean, default=True)
    # Campos de nómina
    en_nomina = Column(Boolean, nullable=False, default=False)
    tipo_pago = Column(String(20), nullable=True)  # DESTAJO | FIJO
    sueldo_semanal = Column(Numeric(15, 2), nullable=True)
    saldo_aguinaldo = Column(Numeric(15, 2), nullable=False, default=0)
    porcentaje_aguinaldo = Column(Numeric(5, 2), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    cargo = relationship("Cargo")
