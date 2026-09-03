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
    cantidad = Column(Numeric(12, 4), nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    material = relationship("Material")
    ubicacion = relationship("Ubicacion")


class SobranteLamina(Base):
    """
    Retazo de un material laminar (MDF, melamina, espuma...) con dimensiones
    reales, disponible para satisfacer cortes futuros.

    Los sobrantes NO viven en `inventario` (que cuenta solo láminas enteras):
    se crean al abrir una lámina nueva para un corte (lámina - corte = pedazo
    restante) o se registran a mano. Un corte que le quepa a un sobrante lo
    consume sin tocar el stock de láminas.
    """
    __tablename__ = "sobrante_lamina"

    id = Column(BigInteger, primary_key=True, index=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False, index=True)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False, default=1)
    largo_cm = Column(Numeric(10, 2), nullable=False)
    ancho_cm = Column(Numeric(10, 2), nullable=False)
    estado = Column(String(20), nullable=False, default="DISPONIBLE", index=True)  # DISPONIBLE | CONSUMIDO | DESECHADO
    # Consumo que CREÓ este sobrante (al abrir una lámina nueva). Permite la
    # reversa exacta: eliminar el consumo re pone la lámina y borra el sobrante.
    consumo_origen_id = Column(BigInteger, nullable=True, index=True)
    consumo_origen_tipo = Column(String(30), nullable=True)  # "produccion" | "produccion_crudo"
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    material = relationship("Material")
    ubicacion = relationship("Ubicacion")

    @property
    def area_cm2(self):
        from decimal import Decimal
        return Decimal(str(self.largo_cm)) * Decimal(str(self.ancho_cm))


class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False)
    tipo = Column(String(50), nullable=False)   # ENTRADA, SALIDA, AJUSTE, DAÑO, DEVOLUCION
    cantidad = Column(Numeric(12, 4), nullable=False)
    costo_unitario = Column(Numeric(15, 2), nullable=True)  # precio del material en el movimiento (entrada)
    # "La llevada": flete/aduana pagado además de la compra (opcional, solo entradas)
    llevada = Column(Numeric(15, 2), nullable=True)
    # Proveedor (dónde se compró) y cliente (material comprado para un cliente específico) — opcionales, solo entradas
    proveedor_id = Column(BigInteger, ForeignKey("proveedor.id", ondelete="RESTRICT"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=True)
    fecha = Column(DateTime, server_default=func.now())
    referencia_tipo = Column(String(100), nullable=True)
    referencia_id = Column(BigInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    proveedor = relationship("Proveedor")
    cliente = relationship("Client")


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
    # "La llevada": flete/aduana pagado además de la compra (opcional)
    llevada = Column(Numeric(15, 2), nullable=True)
    # Proveedor (dónde se compró) y cliente (comprado para un cliente específico) — opcionales, solo entradas
    proveedor_id = Column(BigInteger, ForeignKey("proveedor.id", ondelete="RESTRICT"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=True)
    fecha = Column(DateTime, server_default=func.now())
    referencia_tipo = Column(String(100), nullable=True)   # VENTA, COMPRA, PRODUCCION, AJUSTE...
    referencia_id = Column(BigInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    producto = relationship("Producto")
    ubicacion = relationship("Ubicacion")
    proveedor = relationship("Proveedor")
    cliente = relationship("Client")