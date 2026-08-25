from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# SQLAlchemy resuelve los relationships por string ("Material", "DetallePedido", etc.)
# al momento de la primera consulta. No es necesario importar los modelos aquí,
# ya que hacerlo causa registros duplicados en el MetaData cuando el módulo que
# define la clase ya fue importado por otra ruta.
from app.modules.catalogos.model import Area
from app.modules.empleados.model import Empleado
from app.modules.orders.model import DetallePedido

class OrdenProduccion(Base):
    __tablename__ = "orden_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    detalle_pedido_id = Column(BigInteger, ForeignKey("detalle_pedido.id"), unique=True, nullable=False)
    fecha_inicio = Column(Date, nullable=True)
    fecha_fin = Column(Date, nullable=True)
    estado = Column(String(50), nullable=False)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    detalle_pedido = relationship("DetallePedido")
    etapas = relationship("EtapaProduccion", back_populates="orden", cascade="all, delete-orphan")
    costo = relationship("CostoProduccion", back_populates="orden", uselist=False, cascade="all, delete-orphan")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return self.creador.nombre_usuario if self.creador else None

class EtapaProduccion(Base):
    __tablename__ = "etapa_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    orden_produccion_id = Column(BigInteger, ForeignKey("orden_produccion.id", ondelete="CASCADE"), nullable=False)
    area_id = Column(BigInteger, ForeignKey("area.id"), nullable=False)
    empleado_responsable_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    estado = Column(String(50), nullable=False)
    observaciones = Column(Text, nullable=True)
    # Retrabajo: etapa creada en un área que YA tiene una COMPLETADA para la
    # misma orden. La nómina destajo las ignora (evita doble pago del mismo
    # trabajo).
    es_retrabajo = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    orden = relationship("OrdenProduccion", back_populates="etapas")
    area = relationship("Area")
    empleado_responsable = relationship("Empleado", foreign_keys=[empleado_responsable_id])
    consumos = relationship("ConsumoMaterial", back_populates="etapa", cascade="all, delete-orphan")
    mano_obras = relationship("ManoObra", back_populates="etapa", cascade="all, delete-orphan")
    asignados_adicionales = relationship("EtapaAsignadoAdicional", back_populates="etapa", cascade="all, delete-orphan")

class ConsumoMaterial(Base):
    __tablename__ = "consumo_material"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(BigInteger, ForeignKey("etapa_produccion.id", ondelete="CASCADE"), nullable=False)
    material_id = Column(BigInteger, ForeignKey("material.id"), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False)
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    seccion = Column(String(50), nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha = Column(DateTime, nullable=False)
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    etapa = relationship("EtapaProduccion", back_populates="consumos")
    material = relationship("Material")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return self.creador.nombre_usuario if self.creador else None

class ManoObra(Base):
    __tablename__ = "mano_obra"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(BigInteger, ForeignKey("etapa_produccion.id", ondelete="CASCADE"), nullable=False)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    porcentaje_recargo = Column(Numeric(5, 2), default=0.0, nullable=False)
    pagado = Column(Boolean, default=False, nullable=False)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    etapa = relationship("EtapaProduccion", back_populates="mano_obras")
    empleado = relationship("Empleado")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return self.creador.nombre_usuario if self.creador else None

class CostoProduccion(Base):
    __tablename__ = "costo_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    orden_produccion_id = Column(BigInteger, ForeignKey("orden_produccion.id", ondelete="CASCADE"), unique=True, nullable=False)
    costo_material = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_mano_obra = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_gastos = Column(Numeric(15, 2), default=0.0, nullable=False)
    precio_impuestos_base = Column(Numeric(15, 2), default=0.0, nullable=False)
    ganancia_porcentaje = Column(Numeric(5, 2), default=0.0, nullable=False)
    precio_venta_calculado = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_total = Column(Numeric(15, 2), default=0.0, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    orden = relationship("OrdenProduccion", back_populates="costo")


class EtapaAsignadoAdicional(Base):
    """Empleados adicionales asignados a una etapa de producción (opcional, multi-empleado)."""
    __tablename__ = "etapa_asignado_adicional"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(
        BigInteger,
        ForeignKey("etapa_produccion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    etapa = relationship("EtapaProduccion", back_populates="asignados_adicionales")
    empleado = relationship("Empleado")
