from sqlalchemy import Column, String, Boolean, DateTime, Text, BigInteger, Numeric, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# Importar catalogos para que SQLAlchemy los registre y resuelva las relaciones
from app.modules.catalogos.model import TipoProducto, UnidadMedida


class Producto(Base):
    __tablename__ = "producto"

    id              = Column(BigInteger, primary_key=True, index=True)
    nombre          = Column(String(150), nullable=False)
    codigo          = Column(String(50), nullable=True)
    tipo_producto_id= Column(BigInteger, ForeignKey("tipo_producto.id"), nullable=False)
    descripcion     = Column(Text, nullable=True)
    activo          = Column(Boolean, default=True)
    # --- Dimensiones base para costeo paramétrico ---
    ancho_base      = Column(Numeric(10, 2), default=1.60, nullable=True)
    largo_base      = Column(Numeric(10, 2), default=1.90, nullable=True)
    alto_base       = Column(Numeric(10, 2), nullable=True)
    # -------------------------------------------------
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, onupdate=func.now())

    tipo_producto   = relationship("TipoProducto")
    materiales      = relationship("ProductoMaterial", back_populates="producto", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "material"

    id              = Column(BigInteger, primary_key=True, index=True)
    nombre          = Column(String(150), nullable=False)
    unidad_medida_id= Column(BigInteger, ForeignKey("unidad_medida.id"), nullable=False)
    costo_base      = Column(Numeric(15, 2), nullable=False)
    activo          = Column(Boolean, default=True)
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, onupdate=func.now())

    unidad_medida   = relationship("UnidadMedida")


class ProductoMaterial(Base):
    """
    Receta paramétrica de un producto.
    Cada fila indica qué material se usa y cómo escala su cantidad
    cuando las dimensiones del producto cambian.

    Tipos de escala:
      FIJO       → cantidad siempre igual a cantidad_base
      LINEAL     → escala proporcionalmente con el largo
      AREA       → escala proporcionalmente con el área (ancho × largo)
      ESPACIADO  → se colocan a distancias fijas a lo largo del perímetro
      POR_RANGO  → la cantidad salta en valores discretos según rangos JSON
      FORMULA    → expresión matemática personalizada (campo formula_personalizada)
    """
    __tablename__ = "producto_material"

    id                    = Column(BigInteger, primary_key=True, index=True)
    producto_id           = Column(BigInteger, ForeignKey("producto.id", ondelete="CASCADE"), nullable=False)
    material_id           = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False)
    cantidad_base         = Column(Numeric(14, 4), nullable=False)
    tipo_escala           = Column(String(20), nullable=False)  # FIJO | LINEAL | AREA | ESPACIADO | POR_RANGO | FORMULA

    # Solo para ESPACIADO
    distancia_pauta_cm    = Column(Numeric(8, 2), nullable=True)
    tornillos_por_pieza   = Column(Integer, nullable=True)

    # Condición de activación: {"campo": "nuevo_largo", "op": ">", "valor": 2.0}
    condicion_activacion  = Column(JSON, nullable=True)

    # Para POR_RANGO: [{"max": 1.8, "cantidad": 2}, {"max": 2.2, "cantidad": 4}]
    rangos                = Column(JSON, nullable=True)

    # Fórmula personalizada (para tipo_escala = 'FORMULA')
    formula_personalizada = Column(Text, nullable=True)

    # Override: si True, ignora tipo_escala y usa siempre cantidad_base
    es_fijo_override      = Column(Boolean, default=False)

    observaciones         = Column(Text, nullable=True)
    created_at            = Column(DateTime, server_default=func.now())
    updated_at            = Column(DateTime, onupdate=func.now())

    producto  = relationship("Producto", back_populates="materiales")
    material  = relationship("Material")
