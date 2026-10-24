from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.clients.model import Client
from app.modules.productos.model import Producto, Material

class Cotizacion(Base):
    __tablename__ = "cotizacion"

    id = Column(BigInteger, primary_key=True, index=True)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), nullable=False)
    total_estimado = Column(Numeric(15, 2), default=0.0, nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id"), nullable=False, default=1)
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    total_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    cliente = relationship("Client")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None
    detalles = relationship("DetalleCotizacion", back_populates="cotizacion", cascade="all, delete-orphan")

class DetalleCotizacion(Base):
    __tablename__ = "detalle_cotizacion"

    id = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id = Column(BigInteger, ForeignKey("cotizacion.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=True)
    tipo_item = Column(String(20), nullable=False, server_default="FABRICADO")  # FABRICADO | REVENTA | INSUMO | REPARACION | SERVICIO
    cantidad = Column(Numeric(14, 4), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    # Captura flexible del insumo: la cantidad/precio del renglón se guardan
    # en la unidad que ve el cliente (p. ej. 1128 cm × 160 COP/cm) y
    # `cantidad_base` guarda la equivalencia en la unidad del inventario
    # (0,1128 m³) para costos, stock y reportes. NULL = captura en la unidad
    # base del material (comportamiento histórico).
    unidad_captura = Column(String(4), nullable=True)  # 'M' | 'CM'
    cantidad_base = Column(Numeric(14, 4), nullable=True)
    alto = Column(Numeric(10, 2), nullable=True)
    ancho = Column(Numeric(10, 2), nullable=True)
    largo = Column(Numeric(10, 2), nullable=True)
    descripcion_especifica = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    # Promo obsequio: línea del plástico de regalo (precio 0, 1 por colchón)
    es_obsequio = Column(Boolean, nullable=False, server_default="false")
    costo_materiales = Column(Numeric(15, 2), nullable=True)
    costo_mano_obra = Column(Numeric(15, 2), nullable=True)
    costo_gastos = Column(Numeric(15, 2), nullable=True)
    costo_total = Column(Numeric(15, 2), nullable=True)
    receta_personalizada = Column(JSON, nullable=True)

    cotizacion = relationship("Cotizacion", back_populates="detalles")
    producto = relationship("Producto")
    material = relationship("Material")
    materiales = relationship("CotizacionDetalleMaterial", back_populates="detalle_cotizacion", cascade="all, delete-orphan")
    # Piezas que componen un juego (mesa, sillas, sillones…). El renglón sigue
    # siendo UNO con precio global; las piezas solo abren la producción y el
    # costo por dentro. Se copian al pedido al convertir la cotización.
    piezas = relationship(
        "DetalleCotizacionPieza",
        back_populates="detalle",
        cascade="all, delete-orphan",
        order_by="DetalleCotizacionPieza.orden",
    )


class DetalleCotizacionPieza(Base):
    """Pieza declarada de un renglón-juego (sin precio propio).

    `cantidad` es por UNIDAD del renglón (por juego). Al crear las órdenes de
    producción se multiplica por la cantidad de juegos del detalle del pedido.
    """

    __tablename__ = "detalle_cotizacion_pieza"

    id = Column(BigInteger, primary_key=True, index=True)
    detalle_cotizacion_id = Column(
        BigInteger,
        ForeignKey("detalle_cotizacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = Column(String(150), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False, server_default="1", default=1)
    notas = Column(Text, nullable=True)
    # Orden de aparición en el renglón (Mesa, Sillas, Sillones…).
    orden = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    detalle = relationship("DetalleCotizacion", back_populates="piezas")


class CotizacionAnalisisIA(Base):
    __tablename__ = "cotizacion_analisis_ia"

    id                  = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id       = Column(BigInteger, ForeignKey("cotizacion.id", ondelete="SET NULL"), nullable=True)
    producto_id         = Column(BigInteger, ForeignKey("producto.id", ondelete="SET NULL"), nullable=True)
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
    producto = relationship("Producto")

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
