from sqlalchemy import (
    Column, String, Boolean, DateTime, BigInteger, Numeric, ForeignKey, Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# Importar cargo para la relacion
from app.modules.catalogos.model import Cargo

class Empleado(Base):
    __tablename__ = "empleado"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    # Cargo PRINCIPAL (se conserva para nómina, orden y compatibilidad).
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
    cargos_asignados = relationship(
        "EmpleadoCargo",
        back_populates="empleado",
        cascade="all, delete-orphan",
        order_by="EmpleadoCargo.orden",
    )

    @property
    def cargos(self):
        """Cargos del empleado, principal primero (para la API y la UI)."""
        return [a.cargo for a in self.cargos_asignados if a.cargo is not None]


class EmpleadoCargo(Base):
    """Cargo adicional de un empleado (el principal sigue en `empleado.cargo_id`)."""

    __tablename__ = "empleado_cargo"
    __table_args__ = (
        UniqueConstraint("empleado_id", "cargo_id", name="uq_empleado_cargo"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    empleado_id = Column(
        BigInteger,
        ForeignKey("empleado.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cargo_id = Column(
        BigInteger,
        ForeignKey("cargo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden = Column(Integer, nullable=False, default=0)

    empleado = relationship("Empleado", back_populates="cargos_asignados")
    cargo = relationship("Cargo")
