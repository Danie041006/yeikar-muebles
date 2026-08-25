from sqlalchemy import Column, BigInteger, String, Integer, Boolean, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class PrecioProduccion(Base):
    """Precio de producción por área (EBANISTERÍA, PREPARACIÓN, PINTURA, TAPICERÍA).

    Es el catálogo del LISTADO DE PRECIOS Y CATEGORÍAS DE MUEBLES: el valor que
    suma cada pieza producida al empleado que la fabricó (base de la nómina).
    """

    __tablename__ = "precio_produccion"
    __table_args__ = (Index("ix_precio_produccion_area_activo", "area_id", "activo"),)

    id = Column(BigInteger, primary_key=True, index=True)
    area_id = Column(BigInteger, ForeignKey("area.id", ondelete="RESTRICT"), nullable=False, index=True)
    descripcion = Column(String(200), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="SET NULL"), nullable=True)
    precio = Column(Numeric(15, 2), nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    area = relationship("Area")
    producto = relationship("Producto")
