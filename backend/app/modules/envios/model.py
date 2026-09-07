from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
class Envio(Base):
    __tablename__ = "envio"
    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="CASCADE"), unique=True, nullable=False)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True)
    asignado_por_usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha_salida = Column(DateTime, nullable=True)
    fecha_entrega = Column(DateTime, nullable=True)
    estado = Column(String(50), nullable=False)  # 'PREPARADO', 'EN_TRANSITO', 'ENTREGADO', 'FALLIDO'
    direccion_entrega = Column(Text, nullable=True)
    guia_despacho = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    pedido = relationship("Pedido")
    empleado = relationship("Empleado")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])
    asignado_por = relationship("Usuario", foreign_keys=[asignado_por_usuario_id])
    ubicaciones = relationship("EnvioUbicacion", back_populates="envio", cascade="all, delete-orphan")
    asignaciones = relationship("EnvioAsignacion", back_populates="envio", cascade="all, delete-orphan")

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def asignado_por_nombre(self):
        return (self.asignado_por.nombre or self.asignado_por.nombre_usuario) if self.asignado_por else None


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

    __table_args__ = (
        UniqueConstraint("envio_id", "reportado_por_id", "secuencia", name="uq_envio_ubicacion_secuencia"),
        Index("ix_envio_ubicacion_envio_recibida", "envio_id", "recibida_en"),
    )
