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
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relaciones
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="venta")
    cliente = relationship("Client")
    pedido = relationship("Pedido")
    moneda = relationship("Moneda")


from app.modules.productos.model import Producto


class DetalleVenta(Base):
    __tablename__ = "detalle_venta"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")


class Pago(Base):
    __tablename__ = "pago"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(DateTime, nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    # EFECTIVO_COP | EFECTIVO_USD | BANCOLOMBIA | BANCARIBE | ZELLE
    metodo_pago = Column(String(50), nullable=False)
    referencia = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="pagos")
    moneda = relationship("Moneda")
