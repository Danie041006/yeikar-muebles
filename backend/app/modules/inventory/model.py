from sqlalchemy import Column, Integer, BigInteger, Numeric, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class Inventario(Base):
    __tablename__ = "inventario"
    __table_args__ = (
        UniqueConstraint("material_id", "ubicacion_id", name="uq_inventario_material_ubicacion"),
    )

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    material = relationship("Material")
    ubicacion = relationship("Ubicacion")


class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    tipo = Column(String(50), nullable=False)   # ENTRADA, SALIDA, AJUSTE, DAÑO, DEVOLUCION
    cantidad = Column(Numeric(12, 2), nullable=False)
    fecha = Column(DateTime, server_default=func.now())
    referencia_tipo = Column(String(100), nullable=True)
    referencia_id = Column(BigInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class ProductoInventario(Base):
    """
    Stock actual de PRODUCTOS terminados / de reventa (colchones, neveras,
    electrodomésticos, muebles en bodega) por ubicación.

    Un producto puede ser:
      - Fabricado por YEIKAR y terminado en producción.
      - Comprado para reventa directa (colchones, neveras, etc.).
    """
    __tablename__ = "producto_inventario"
    __table_args__ = (
        UniqueConstraint("producto_id", "ubicacion_id", name="uq_producto_inventario_producto_ubicacion"),
    )

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False, server_default="0")
    costo_promedio = Column(Numeric(15, 2), nullable=True)  # costo unitario actual (promedio ponderado)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    producto = relationship("Producto")
    ubicacion = relationship("Ubicacion")


class MovimientoProductoInventario(Base):
    __tablename__ = "movimiento_producto_inventario"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    tipo = Column(String(50), nullable=False)   # ENTRADA, SALIDA, AJUSTE, DAÑO, DEVOLUCION
    cantidad = Column(Numeric(12, 2), nullable=False)
    costo_unitario = Column(Numeric(15, 2), nullable=True)  # costo del movimiento (entrada)
    fecha = Column(DateTime, server_default=func.now())
    referencia_tipo = Column(String(100), nullable=True)   # VENTA, COMPRA, PRODUCCION, AJUSTE...
    referencia_id = Column(BigInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    producto = relationship("Producto")
    ubicacion = relationship("Ubicacion")