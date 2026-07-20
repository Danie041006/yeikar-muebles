from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.clients.model import Client
from app.modules.productos.model import Producto

class Cotizacion(Base):
    __tablename__ = "cotizacion"

    id = Column(BigInteger, primary_key=True, index=True)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), nullable=False)
    total_estimado = Column(Numeric(15, 2), default=0.0, nullable=False)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    cliente = relationship("Client")
    detalles = relationship("DetalleCotizacion", back_populates="cotizacion", cascade="all, delete-orphan")

class DetalleCotizacion(Base):
    __tablename__ = "detalle_cotizacion"

    id = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id = Column(BigInteger, ForeignKey("cotizacion.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id"), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    alto = Column(Numeric(10, 2), nullable=True)
    ancho = Column(Numeric(10, 2), nullable=True)
    largo = Column(Numeric(10, 2), nullable=True)
    observaciones = Column(Text, nullable=True)
    costo_materiales = Column(Numeric(15, 2), nullable=True)
    costo_mano_obra = Column(Numeric(15, 2), nullable=True)
    costo_gastos = Column(Numeric(15, 2), nullable=True)
    costo_total = Column(Numeric(15, 2), nullable=True)

    cotizacion = relationship("Cotizacion", back_populates="detalles")
    producto = relationship("Producto")
    materiales = relationship("CotizacionDetalleMaterial", back_populates="detalle_cotizacion", cascade="all, delete-orphan")

class CotizacionAnalisisIA(Base):
    __tablename__ = "cotizacion_analisis_ia"

    id                  = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id       = Column(BigInteger, ForeignKey("cotizacion.id", ondelete="SET NULL"), nullable=True)
    foto_url            = Column(Text, nullable=False)
    tipo_mueble         = Column(String(50), default="cama", nullable=False)
    familia_probable    = Column(String(50), nullable=True)
    tiene_tapiceria     = Column(Boolean, default=False, nullable=False)
    tiene_nocheros      = Column(Boolean, default=False, nullable=False)
    tiene_espejo        = Column(Boolean, default=False, nullable=False)
    tiene_luces         = Column(Boolean, default=False, nullable=False)
    tipo_patas          = Column(String(50), nullable=True)
    estilo_general      = Column(String(50), nullable=True)
    nivel_confianza     = Column(Numeric(5, 2), nullable=True)
    observaciones       = Column(Text, nullable=True)
    created_at          = Column(DateTime, server_default=func.now())

    cotizacion = relationship("Cotizacion")

class CotizacionDetalleMaterial(Base):
    __tablename__ = "cotizacion_detalle_material"

    id                    = Column(BigInteger, primary_key=True, index=True)
    detalle_cotizacion_id = Column(BigInteger, ForeignKey("detalle_cotizacion.id", ondelete="CASCADE"), nullable=False)
    material_id           = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=False)
    cantidad_base         = Column(Numeric(14, 4), nullable=False)
    cantidad_calculada    = Column(Numeric(14, 4), nullable=False)
    tipo_escala           = Column(String(20), nullable=False)  # FIJO | LINEAL | AREA | ESPACIADO | POR_RANGO | FORMULA
    distancia_pauta_cm    = Column(Numeric(8, 2), nullable=True)
    tornillos_por_pieza   = Column(Integer, nullable=True)
    formula_personalizada = Column(Text, nullable=True)
    activo                = Column(Boolean, default=True, nullable=False)
    observaciones         = Column(Text, nullable=True)

    detalle_cotizacion = relationship("DetalleCotizacion", back_populates="materiales")
    material = relationship("Material")

