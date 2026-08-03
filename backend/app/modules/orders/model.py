from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.clients.model import Client
from app.modules.quotes.model import Cotizacion
from app.modules.productos.model import Producto

class Pedido(Base):
    __tablename__ = "pedido"

    id = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id = Column(BigInteger, ForeignKey("cotizacion.id"), unique=True, nullable=False)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), nullable=False)
    observaciones = Column(Text, nullable=True)
    fecha_entrega_estimada = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    cliente = relationship("Client")
    cotizacion = relationship("Cotizacion")
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")

class DetallePedido(Base):
    __tablename__ = "detalle_pedido"

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id"), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    # Snapshot de costos al convertir cotización → pedido
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    porcentaje_ganancia = Column(Numeric(5, 2), nullable=True)
    alto = Column(Numeric(10, 2), nullable=True)
    ancho = Column(Numeric(10, 2), nullable=True)
    largo = Column(Numeric(10, 2), nullable=True)
    color = Column(String(100), nullable=True)
    acabado = Column(String(100), nullable=True)
    descripcion_especifica = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto")
