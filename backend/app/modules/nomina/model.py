from sqlalchemy import Column, Date, String, Text, BigInteger, Numeric, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Nomina(Base):
    """Nómina semanal: cabecera con el periodo y el estado."""

    __tablename__ = "nomina"

    id = Column(BigInteger, primary_key=True, index=True)
    periodo_desde = Column(Date, nullable=False)
    periodo_hasta = Column(Date, nullable=False)
    estado = Column(String(20), nullable=False, default="BORRADOR")  # BORRADOR | PAGADA | ANULADA
    descripcion = Column(String(200), nullable=True)
    total_nomina = Column(Numeric(15, 2), nullable=False, default=0)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    detalles = relationship("NominaDetalle", back_populates="nomina", cascade="all, delete-orphan")
    conceptos_varios = relationship("NominaConceptoVario", back_populates="nomina", cascade="all, delete-orphan")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None


class NominaDetalle(Base):
    """Bloque de un empleado dentro de una nómina."""

    __tablename__ = "nomina_detalle"
    __table_args__ = (Index("ix_nomina_detalle_nomina_empleado", "nomina_id", "empleado_id"),)

    id = Column(BigInteger, primary_key=True, index=True)
    nomina_id = Column(BigInteger, ForeignKey("nomina.id", ondelete="CASCADE"), nullable=False, index=True)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="RESTRICT"), nullable=False)
    tipo_pago = Column(String(20), nullable=False)  # DESTAJO | FIJO
    total_produccion = Column(Numeric(15, 2), nullable=False, default=0)
    bono_aguinaldo = Column(Numeric(15, 2), nullable=False, default=0)
    monto_a_pagar = Column(Numeric(15, 2), nullable=False, default=0)
    # Snapshot del sueldo semanal en el momento de crear la nómina: editar el
    # sueldo del empleado después NO debe revalorizar nóminas ya emitidas
    # (antes _actualizar_totales_detalle re-leía el sueldo actual).
    sueldo_snapshot = Column(Numeric(15, 2), nullable=True)
    metodo_caja_id = Column(BigInteger, ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=True)
    gasto_id = Column(BigInteger, ForeignKey("gasto.id", ondelete="SET NULL"), nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    nomina = relationship("Nomina", back_populates="detalles")
    empleado = relationship("Empleado")
    lineas = relationship("NominaLinea", back_populates="detalle", cascade="all, delete-orphan")
    metodo_caja = relationship("MetodoCaja")
    gasto = relationship("Gasto")

    @property
    def empleado_nombre(self):
        return self.empleado.nombre if self.empleado else None

    @property
    def cargo_nombre(self):
        return self.empleado.cargo.nombre if self.empleado and self.empleado.cargo else None

    @property
    def metodo_caja_nombre(self):
        return self.metodo_caja.nombre if self.metodo_caja else None


class NominaLinea(Base):
    """Línea de producción (automática desde la etapa) o manual de un empleado."""

    __tablename__ = "nomina_linea"

    id = Column(BigInteger, primary_key=True, index=True)
    detalle_id = Column(BigInteger, ForeignKey("nomina_detalle.id", ondelete="CASCADE"), nullable=False, index=True)
    origen = Column(String(20), nullable=False, default="MANUAL")  # ETAPA | MANUAL
    etapa_id = Column(BigInteger, nullable=True)
    descripcion = Column(String(250), nullable=False)
    area_id = Column(BigInteger, ForeignKey("area.id", ondelete="SET NULL"), nullable=True)
    cliente_nombre = Column(String(150), nullable=True)
    cantidad = Column(Numeric(10, 2), nullable=False, default=1)
    precio_unitario = Column(Numeric(15, 2), nullable=False, default=0)
    total = Column(Numeric(15, 2), nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())

    detalle = relationship("NominaDetalle", back_populates="lineas")
    area = relationship("Area")


class NominaConceptoVario(Base):
    """Conceptos no asociados a empleados (CARMEN MANILLAS, ALMUERZOS, PRÉSTAMOS...)."""

    __tablename__ = "nomina_concepto_vario"

    id = Column(BigInteger, primary_key=True, index=True)
    nomina_id = Column(BigInteger, ForeignKey("nomina.id", ondelete="CASCADE"), nullable=False, index=True)
    descripcion = Column(String(200), nullable=False)
    monto = Column(Numeric(15, 2), nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())

    nomina = relationship("Nomina", back_populates="conceptos_varios")


class NominaAreaConfig(Base):
    """Porcentaje de aguinaldo que acumula cada área de producción."""

    __tablename__ = "nomina_area_config"

    id = Column(BigInteger, primary_key=True, index=True)
    area_id = Column(BigInteger, ForeignKey("area.id", ondelete="CASCADE"), nullable=False, unique=True)
    porcentaje_aguinaldo = Column(Numeric(5, 2), nullable=False, default=5)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    area = relationship("Area")
