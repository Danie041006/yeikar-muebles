from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.clients.model import Client
from app.modules.orders.model import Pedido
from app.modules.catalogos.model import Moneda


class Venta(Base):
    __tablename__ = "venta"

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="RESTRICT"), unique=True, nullable=False)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(Date, nullable=False)
    total = Column(Numeric(15, 2), nullable=False)
    estado = Column(String(50), nullable=False, default="PENDIENTE")
    # Tasa de cambio al momento de la facturación (COP por 1 unidad de moneda de la venta).
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Total convertido a moneda base (COP) con la tasa del día de facturación.
    total_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relaciones
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="venta")
    cliente = relationship("Client")
    pedido = relationship("Pedido")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return self.creador.nombre_usuario if self.creador else None


from app.modules.productos.model import Producto, Material


class DetalleVenta(Base):
    __tablename__ = "detalle_venta"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=True)
    tipo_item = Column(String(20), nullable=False, server_default="FABRICADO")  # FABRICADO | REVENTA | INSUMO
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    # Snapshot de costos al momento de facturar (para Control Interno de Ingresos)
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    porcentaje_ganancia = Column(Numeric(5, 2), nullable=True)
    utilidad = Column(Numeric(15, 2), nullable=True)
    # Descuento otorgado (opcional, precio ya refleja el descuento; este campo lo documenta)
    descuento = Column(Numeric(15, 2), nullable=True, default=0.0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")
    material = relationship("Material")


class Pago(Base):
    __tablename__ = "pago"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(DateTime, nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    # Tasa de cambio usada para convertir a la moneda base de la venta.
    # Si la moneda del pago es igual a la de la venta, tasa_cambio = 1.0
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Monto equivalente en la moneda base (moneda de la venta) ya convertido.
    # Es el valor que realmente se descuenta del saldo pendiente.
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False)
    # EFECTIVO_COP | EFECTIVO_USD | EFECTIVO_VES | BANCOLOMBIA | BANCARIBE | ZELLE | BINANCE
    metodo_pago = Column(String(50), nullable=False)
    referencia = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="pagos")
    moneda = relationship("Moneda")

    @property
    def recibos(self):
        """Comprobantes digitales del pago (adjuntos tipo PAGO)."""
        from sqlalchemy.orm import object_session
        from app.modules.adjuntos.service import adjuntos_info
        s = object_session(self)
        if s is None:
            return []
        return adjuntos_info(s, "PAGO", self.id)
