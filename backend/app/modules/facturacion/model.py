from sqlalchemy import Column, Date, DateTime, Text, BigInteger, Numeric, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Factura(Base):
    """Documento fiscal (SENIAT) emitido para un pedido pagado al 100%.

    Independiente de la `venta` (registro de cobros): la factura es el
    documento, la venta es el flujo de dinero. Montos en USD decididos por
    la dueña y convertidos a Bs. con `tasa_usd_ves`.
    """

    __tablename__ = "factura"

    id = Column(BigInteger, primary_key=True, index=True)
    # Sin UNIQUE a nivel de modelo: tras ANULAR una factura el pedido puede
    # volver a facturarse (corrección), conservando la anulada en el historial.
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="RESTRICT"), nullable=False)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=False)
    fecha_emision = Column(Date, nullable=False)
    total_usd = Column(Numeric(15, 2), nullable=False, default=0.0)
    # 1 USD = X Bs. (tasa decidida al emitir la factura).
    tasa_usd_ves = Column(Numeric(15, 6), nullable=False, default=1.0)
    base_imponible_bs = Column(Numeric(15, 2), nullable=False, default=0.0)
    iva_bs = Column(Numeric(15, 2), nullable=False, default=0.0)
    igtf_bs = Column(Numeric(15, 2), nullable=False, default=0.0)
    total_bs = Column(Numeric(15, 2), nullable=False, default=0.0)
    estado = Column(String(50), nullable=False, default="EMITIDA")  # EMITIDA, ANULADA
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    detalles = relationship("DetalleFactura", back_populates="factura", cascade="all, delete-orphan")
    cliente = relationship("Client")
    pedido = relationship("Pedido")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return self.creador.nombre_usuario if self.creador else None


class DetalleFactura(Base):
    """Línea de la factura: cantidad del pedido (fija) + precio en USD decidido por la dueña.

    `tipo_item` replica el discriminador de pedido/venta: FABRICADO/REVENTA
    apuntan a `producto_id`; INSUMO apunta a `material_id` (insumo vendido
    suelto, sin producto asociado).
    """

    __tablename__ = "detalle_factura"

    id = Column(BigInteger, primary_key=True, index=True)
    factura_id = Column(BigInteger, ForeignKey("factura.id", ondelete="CASCADE"), nullable=False)
    tipo_item = Column(String(20), nullable=False, default="FABRICADO")  # FABRICADO, REVENTA, INSUMO
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=True)
    descripcion = Column(String(250), nullable=True)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio_usd = Column(Numeric(15, 2), nullable=False)
    subtotal_usd = Column(Numeric(15, 2), nullable=False)
    subtotal_bs = Column(Numeric(15, 2), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    factura = relationship("Factura", back_populates="detalles")
    producto = relationship("Producto")
    material = relationship("Material")


class TasaImpuesto(Base):
    """Tasas fiscales configurables (IVA, IGTF). Porcentaje: 16.0 = 16%."""

    __tablename__ = "tasa_impuesto"

    id = Column(BigInteger, primary_key=True, index=True)
    clave = Column(String(20), nullable=False, unique=True)  # IVA, IGTF
    nombre = Column(String(100), nullable=False)
    tasa = Column(Numeric(6, 4), nullable=False)
    vigente = Column(Boolean, nullable=False, default=True)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
