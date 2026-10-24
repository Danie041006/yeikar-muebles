from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Envio(Base):
    __tablename__ = "envio"
    id = Column(BigInteger, primary_key=True, index=True)
    # Varios despachos por pedido: el cliente puede llevarse lo que ya está
    # terminado aunque el resto siga en producción (entrega parcial).
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True)
    asignado_por_usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha_salida = Column(DateTime, nullable=True)
    fecha_entrega = Column(DateTime, nullable=True)
    estado = Column(String(50), nullable=False)  # 'PREPARADO', 'EN_TRANSITO', 'ENTREGADO', 'FALLIDO'
    direccion_entrega = Column(Text, nullable=True)
    guia_despacho = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)
    # Costo REAL pagado por el flete/traslado del pedido (opcional). Se usa para
    # conocer el margen real del pedido (cobrado − costos de producción − flete).
    costo_flete = Column(Numeric(15, 2), nullable=True)
    moneda_flete_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=True)
    tasa_cambio_flete = Column(Numeric(15, 6), nullable=True)
    costo_flete_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    pedido = relationship("Pedido", back_populates="envios")
    empleado = relationship("Empleado")
    moneda_flete = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])
    asignado_por = relationship("Usuario", foreign_keys=[asignado_por_usuario_id])
    # Ítems que van en ESTE despacho (uno o varios renglones/piezas del pedido).
    detalles = relationship("EnvioDetalle", back_populates="envio", cascade="all, delete-orphan")
    ubicaciones = relationship("EnvioUbicacion", back_populates="envio", cascade="all, delete-orphan")
    asignaciones = relationship("EnvioAsignacion", back_populates="envio", cascade="all, delete-orphan")

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def asignado_por_nombre(self):
        return (self.asignado_por.nombre or self.asignado_por.nombre_usuario) if self.asignado_por else None


class EnvioDetalle(Base):
    """Ítem (renglón o pieza) que viaja en un despacho.

    `cantidad` es la parte de ese renglón/pieza que se entrega en ESTE envío.
    Si el renglón se abrió en órdenes por pieza, `orden_produccion_id` dice cuál
    pieza es; si es un renglón normal (o reventa/insumo), queda NULL.
    """

    __tablename__ = "envio_detalle"

    id = Column(BigInteger, primary_key=True, index=True)
    envio_id = Column(
        BigInteger,
        ForeignKey("envio.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    detalle_pedido_id = Column(
        BigInteger,
        ForeignKey("detalle_pedido.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Pieza concreta cuando el renglón-juego tiene una orden por pieza.
    orden_produccion_id = Column(
        BigInteger,
        ForeignKey("orden_produccion.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cantidad = Column(Numeric(14, 4), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    envio = relationship("Envio", back_populates="detalles")
    detalle_pedido = relationship("DetallePedido")
    orden = relationship("OrdenProduccion")

    __table_args__ = (
        # Una misma pieza no puede repetirse dentro del mismo envío.
        UniqueConstraint(
            "envio_id",
            "detalle_pedido_id",
            "orden_produccion_id",
            name="uq_envio_detalle_item",
        ),
        # El UNIQUE anterior permite varios NULL (renglones sin pieza); este
        # índice parcial garantiza una sola fila por renglón cuando no hay orden.
        Index(
            "uq_envio_detalle_sin_orden",
            "envio_id",
            "detalle_pedido_id",
            unique=True,
            postgresql_where=text("orden_produccion_id IS NULL"),
        ),
        CheckConstraint("cantidad > 0", name="ck_envio_detalle_cantidad_positiva"),
    )

    @property
    def pieza_nombre(self):
        return self.orden.pieza_nombre if self.orden else None

    @property
    def tipo_item(self):
        return self.detalle_pedido.tipo_item if self.detalle_pedido else None

    @property
    def producto_id(self):
        return self.detalle_pedido.producto_id if self.detalle_pedido else None

    @property
    def material_id(self):
        return self.detalle_pedido.material_id if self.detalle_pedido else None

    @property
    def descripcion(self) -> str:
        det = self.detalle_pedido
        if det is None:
            return "Ítem del pedido"
        base = None
        if det.producto is not None:
            base = det.producto.nombre
        elif det.material is not None:
            base = det.material.nombre
        base = base or det.descripcion_especifica or det.observaciones or "Servicio"
        if self.orden and self.orden.pieza_nombre:
            return f"{base} — {self.orden.pieza_nombre}"
        return base


class EnvioAsignacion(Base):
    __tablename__ = "envio_asignacion"

    id = Column(BigInteger, primary_key=True, index=True)
    envio_id = Column(BigInteger, ForeignKey("envio.id", ondelete="CASCADE"), nullable=False, index=True)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True)
    asignado_por_usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    asignado_en = Column(DateTime, server_default=func.now(), nullable=False)
    desasignado_en = Column(DateTime, nullable=True)
    motivo = Column(Text, nullable=True)

    envio = relationship("Envio", back_populates="asignaciones")
    empleado = relationship("Empleado")
    asignado_por = relationship("Usuario", foreign_keys=[asignado_por_usuario_id])


class EnvioUbicacion(Base):
    __tablename__ = "envio_ubicacion"

    id = Column(BigInteger, primary_key=True, index=True)
    envio_id = Column(BigInteger, ForeignKey("envio.id", ondelete="CASCADE"), nullable=False, index=True)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True, index=True)
    reportado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    latitud = Column(Numeric(10, 7), nullable=False)
    longitud = Column(Numeric(10, 7), nullable=False)
    precision_m = Column(Numeric(10, 2), nullable=True)
    velocidad = Column(Numeric(10, 2), nullable=True)
    rumbo = Column(Numeric(6, 2), nullable=True)
    capturada_en = Column(DateTime, nullable=True)
    recibida_en = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    fuente = Column(String(30), nullable=False, default="web")
    secuencia = Column(BigInteger, nullable=True)

    envio = relationship("Envio", back_populates="ubicaciones")
    empleado = relationship("Empleado")
    reportado_por = relationship("Usuario", foreign_keys=[reportado_por_id])

    @property
    def reportado_por_nombre(self) -> str | None:
        return self.reportado_por.display_name if self.reportado_por else None

    __table_args__ = (
        UniqueConstraint("envio_id", "reportado_por_id", "secuencia", name="uq_envio_ubicacion_secuencia"),
        Index("ix_envio_ubicacion_envio_recibida", "envio_id", "recibida_en"),
    )
