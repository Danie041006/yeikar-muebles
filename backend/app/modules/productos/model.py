from sqlalchemy import Column, String, Boolean, DateTime, Text, BigInteger, Numeric, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# Importar catalogos para que SQLAlchemy los registre y resuelva las relaciones
from app.modules.catalogos.model import TipoProducto, UnidadMedida, Moneda


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
    # --- Precio fijo importado del Excel (estructura de costos) ---
    precio_costo_base   = Column(Numeric(15, 2), nullable=True)   # TOTAL COSTO DE PRODUCCIÓN del Excel
    precio_venta_base   = Column(Numeric(15, 2), nullable=True)   # Precio de Venta sin IVA (con ganancia)
    precio_venta_con_iva= Column(Numeric(15, 2), nullable=True)   # Total a Pagar (con IVA 16%)
    hoja_excel          = Column(String(150), nullable=True)       # Nombre de la hoja fuente en el Excel
    stock_minimo        = Column(Numeric(10, 2), nullable=False, server_default="8")
    es_reventa          = Column(Boolean, default=False, nullable=False)  # True = se revende (colchón, nevera...); False = se fabrica
    # Moneda de los precios de referencia (costo/venta). Base del ERP: COP (id=1).
    # Los productos de reventa suelen comprarse en USD; la conversión a COP se
    # hace con la tasa vigente al USAR el precio, nunca congelada.
    moneda_id           = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=True, server_default="1")
    # --------------------------------------------------------------
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, onupdate=func.now())

    tipo_producto   = relationship("TipoProducto")
    moneda          = relationship("Moneda")
    materiales      = relationship("ProductoMaterial", back_populates="producto", cascade="all, delete-orphan")
    secciones       = relationship("SeccionProducto", back_populates="producto", cascade="all, delete-orphan")

    @property
    def fotos(self):
        """Fotos de referencia del mueble (adjuntos tipo PRODUCTO)."""
        from sqlalchemy.orm import object_session
        from app.modules.adjuntos.service import adjuntos_info
        s = object_session(self)
        if s is None:
            return []
        return adjuntos_info(s, "PRODUCTO", self.id)


class Material(Base):
    __tablename__ = "material"

    id              = Column(BigInteger, primary_key=True, index=True)
    nombre          = Column(String(150), nullable=False)
    unidad_medida_id= Column(BigInteger, ForeignKey("unidad_medida.id"), nullable=False)
    costo_base      = Column(Numeric(15, 2), nullable=False)
    stock_minimo    = Column(Numeric(10, 2), nullable=False, server_default="8")
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
    seccion               = Column(String(30), nullable=False, default="EBANISTERIA")  # EBANISTERIA | TENDIDO | COLA_DE_PATO | TAPICERIA | PINTURA | TERMINACION | NOCHEROS | MANO_DE_OBRA

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


class ReglaGastoSeccion(Base):
    """
    Reglas globales de % de recargo/gasto indirecto por sección del mueble.
    Ej: EBANISTERIA -> 10.00%, NOCHEROS -> 5.00%, TAPICERIA -> 0.00%
    """
    __tablename__ = "regla_gasto_seccion"

    id               = Column(BigInteger, primary_key=True, index=True)
    seccion          = Column(String(30), unique=True, nullable=False)
    porcentaje_gasto = Column(Numeric(5, 2), nullable=False)



class CamaHistoricaAtributos(Base):
    """
    DEPRECATED: Tabla original solo para camas.
    Mantenida para compatibilidad con los 63 registros históricos importados.
    Para nuevos productos de CUALQUIER tipo, usar MuebleAtributos.
    """
    __tablename__ = "cama_historica_atributos"

    id                  = Column(BigInteger, primary_key=True, index=True)
    producto_id         = Column(BigInteger, ForeignKey("producto.id", ondelete="CASCADE"), unique=True, nullable=False)
    tiene_tapiceria     = Column(Boolean, default=False, nullable=False)
    tiene_nocheros      = Column(Boolean, default=False, nullable=False)
    tiene_espejo        = Column(Boolean, default=False, nullable=False)
    tiene_luces         = Column(Boolean, default=False, nullable=False)
    tipo_patas          = Column(String(50), nullable=True)
    estilo_general      = Column(String(50), nullable=True)
    vector_similitud    = Column(JSON, nullable=True)

    producto = relationship("Producto")


class MuebleAtributos(Base):
    """
    Tabla GENÉRICA de atributos para CUALQUIER tipo de mueble.

    Reemplaza a CamaHistoricaAtributos para todos los tipos nuevos.
    Usa tres campos JSON para máxima flexibilidad:
      - atributos_comunes : campos que aplican a cualquier mueble
      - atributos_extra   : campos específicos del tipo (nocheros para camas,
                            cantidad_puertas para closets, etc.)
      - vector_similitud  : vector numérico de 8 posiciones para cosine similarity

    Cómo se usa:
      1. Cuando se importa un producto histórico (de cualquier tipo), se crea
         un registro aquí con sus atributos y su vector.
      2. El motor de similitud consulta esta tabla para encontrar el Top N.
      3. Si el usuario valida un análisis de imagen, los atributos confirmados
         se guardan también aquí para enriquecer el histórico.
    """
    __tablename__ = "mueble_atributos"

    id                  = Column(BigInteger, primary_key=True, index=True)
    producto_id         = Column(BigInteger, ForeignKey("producto.id", ondelete="CASCADE"), unique=True, nullable=False)
    tipo_mueble         = Column(String(50), nullable=False, index=True)   # cama, closet, comedor...
    familia_probable    = Column(String(50), nullable=True)
    estilo_general      = Column(String(50), nullable=True)
    tipo_patas          = Column(String(50), nullable=True)
    tiene_tapiceria     = Column(Boolean, default=False, nullable=False)
    tiene_luces         = Column(Boolean, default=False, nullable=False)
    atributos_extra     = Column(JSON, nullable=True)   # {tiene_nocheros, tiene_espejo, ...}
    vector_similitud    = Column(JSON, nullable=True)   # [float x 8]
    created_at          = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, onupdate=func.now())

    producto = relationship("Producto")


class MaterialSinonimo(Base):
    __tablename__ = "material_sinonimo"

    id          = Column(BigInteger, primary_key=True, index=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="CASCADE"), nullable=False)
    sinonimo    = Column(String(150), unique=True, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())

    material = relationship("Material")


class SeccionProducto(Base):
    """
    Sección / Área productiva dentro de un producto (ej: EBANISTERÍA, PINTURA, TERMINACIÓN, TAPICERÍA, NOCHEROS EN CRUDO).
    """
    __tablename__ = "seccion_producto"

    id          = Column(BigInteger, primary_key=True, index=True)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre      = Column(String(100), nullable=False)
    orden       = Column(Integer, default=1, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, onupdate=func.now())

    producto    = relationship("Producto", back_populates="secciones")
    elementos   = relationship("ElementoSeccion", back_populates="seccion", cascade="all, delete-orphan")
    politica    = relationship("PoliticaSeccion", uselist=False, back_populates="seccion", cascade="all, delete-orphan")
    costos_produccion = relationship("CostoProduccionSeccion", back_populates="seccion", cascade="all, delete-orphan")


class ElementoSeccion(Base):
    """
    Insumo físico perteneciente a una sección específica del producto.
    Mantiene aislados los insumos por sección y desconectados de los precios unitarios históricos.
    """
    __tablename__ = "elemento_seccion"

    id                      = Column(BigInteger, primary_key=True, index=True)
    seccion_id              = Column(BigInteger, ForeignKey("seccion_producto.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre_insumo_original  = Column(String(150), nullable=False)
    material_id_normalizado = Column(BigInteger, ForeignKey("material.id", ondelete="SET NULL"), nullable=True)
    estado_resolucion       = Column(String(30), default="PENDIENTE", nullable=False)  # PENDIENTE | MAPEADO | AMBIGUO
    cantidad                = Column(Numeric(14, 4), nullable=False, default=1.0)
    unidad_medida           = Column(String(50), nullable=True)
    observaciones           = Column(Text, nullable=True)
    precio_unitario         = Column(Numeric(15, 2), nullable=True)  # Desactivado en receta pura
    costo_subtotal          = Column(Numeric(15, 2), nullable=True)  # Desactivado en receta pura
    created_at              = Column(DateTime, server_default=func.now())
    updated_at              = Column(DateTime, onupdate=func.now())

    seccion               = relationship("SeccionProducto", back_populates="elementos")
    material_normalizado  = relationship("Material")


class PoliticaSeccion(Base):
    """
    Reglas específicas de Mano de Obra y Porcentajes de Gastos para una sección del mueble.
    Permite variación de % por área y por producto (ej. 10% en Ebanistería, 5% en Nocheros).
    """
    __tablename__ = "politica_seccion"

    id                  = Column(BigInteger, primary_key=True, index=True)
    seccion_id          = Column(BigInteger, ForeignKey("seccion_producto.id", ondelete="CASCADE"), unique=True, nullable=False)
    mano_obra_base      = Column(Numeric(15, 2), default=0.0, nullable=False)
    pct_liquidacion_mo  = Column(Numeric(5, 2), default=5.00, nullable=False)     # % de liquidación sobre la mano de obra
    pct_gastos_seccion  = Column(Numeric(5, 2), default=10.00, nullable=False)    # % de gastos sobre materiales de la sección

    # --- Costos avanzados por sección (todo opcional) ---
    costo_fabricacion   = Column(Numeric(15, 2), nullable=True)   # Costo base de fabricación (de la hoja Excel)
    pct_trabajadores    = Column(Numeric(5, 2), nullable=True)    # % extra que cobran los trabajadores sobre costo_fabricacion
    pct_negocio         = Column(Numeric(5, 2), nullable=True)    # % de decisión del negocio sobre el subtotal de la sección

    created_at          = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, onupdate=func.now())

    seccion             = relationship("SeccionProducto", back_populates="politica")


class CostoProduccionSeccion(Base):
    """
    Costos de producción específicos de una sección.
    Cada sección puede tener N costos (ej: PREPARADO CAMA, PINTURA CAMA, etc.)
    con su propio costo_base y porcentaje opcional.
    """
    __tablename__ = "costo_produccion_seccion"

    id          = Column(BigInteger, primary_key=True, index=True)
    seccion_id  = Column(BigInteger, ForeignKey("seccion_producto.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre      = Column(String(200), nullable=False)
    porcentaje  = Column(Numeric(5, 2), nullable=True)
    costo_base  = Column(Numeric(15, 2), default=0.0, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, onupdate=func.now())

    seccion     = relationship("SeccionProducto", back_populates="costos_produccion")

