from decimal import Decimal
from sqlalchemy import JSON, Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

# SQLAlchemy resuelve los relationships por string ("Material", "DetallePedido", etc.)
# al momento de la primera consulta. No es necesario importar los modelos aquí,
# ya que hacerlo causa registros duplicados en el MetaData cuando el módulo que
# define la clase ya fue importado por otra ruta.
from app.modules.catalogos.model import Area
from app.modules.empleados.model import Empleado
from app.modules.orders.model import DetallePedido

# Tipo de orden de producción: define el DESTINO de lo fabricado.
# PEDIDO → línea de pedido (al finalizar dispara pedido TERMINADO + envío).
# EXHIBICION → pieza de showroom (producto es_exhibicion): al finalizar entra
#   al stock de la ubicación EXHIBICIÓN con su costo real; nunca hay envío.
# STOCK → fabricación sin pedido de un producto del catálogo (destino manual).
TIPO_PEDIDO = "PEDIDO"
TIPO_EXHIBICION = "EXHIBICION"
TIPO_STOCK = "STOCK"
TIPOS_ORDEN = (TIPO_PEDIDO, TIPO_EXHIBICION, TIPO_STOCK)


class OrdenProduccion(Base):
    __tablename__ = "orden_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    # nullable=True: una orden puede ser de tipo STOCK/EXHIBICION (sin pedido
    # de por medio). Postgres permite varios NULLs pese al UNIQUE.
    detalle_pedido_id = Column(BigInteger, ForeignKey("detalle_pedido.id"), unique=True, nullable=True)
    # producto_id solo se usa en órdenes sin pedido (tipo STOCK/EXHIBICION):
    # dice qué mueble se está fabricando sin depender de un detalle de pedido.
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="SET NULL"), nullable=True, index=True)
    # Pedidos/órdenes de exhibición se fabrican igual (mismas etapas, consumos
    # y mano de obra); solo cambia el destino al finalizar. `tipo` hace
    # explícito ese destino (es_stock queda como alias heredado de STOCK).
    tipo = Column(String(20), nullable=False, server_default=TIPO_PEDIDO, default=TIPO_PEDIDO)
    # Dimensiones objetivo SOLO para órdenes de stock (el detalle de pedido trae
    # las propias). Se copian al crudo generado.
    ancho = Column(Numeric(12, 2), nullable=True)
    largo = Column(Numeric(12, 2), nullable=True)
    alto = Column(Numeric(12, 2), nullable=True)
    fecha_inicio = Column(Date, nullable=True)
    fecha_fin = Column(Date, nullable=True)
    estado = Column(String(50), nullable=False)
    # es_stock: alias heredado de tipo STOCK/EXHIBICION (orden sin pedido).
    # Se mantiene por compatibilidad con la API; la fuente de verdad es `tipo`.
    # Al finalizar una EXHIBICION NO dispara pedido->TERMINADO ni envío; en su
    # lugar suma stock a la ubicación EXHIBICIÓN. Una STOCK no tiene destino
    # automático.
    es_stock = Column(Boolean, default=False, nullable=False, server_default="false")
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    detalle_pedido = relationship("DetallePedido")
    producto = relationship("Producto", foreign_keys=[producto_id])
    etapas = relationship("EtapaProduccion", back_populates="orden", cascade="all, delete-orphan")
    costo = relationship("CostoProduccion", back_populates="orden", uselist=False, cascade="all, delete-orphan")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

class EtapaProduccion(Base):
    __tablename__ = "etapa_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    orden_produccion_id = Column(BigInteger, ForeignKey("orden_produccion.id", ondelete="CASCADE"), nullable=False)
    area_id = Column(BigInteger, ForeignKey("area.id"), nullable=False)
    # Nullable: las etapas pre-marcadas como COMPLETADA al asignar un producto en
    # crudo no tienen responsable en esta orden (la labor ya se pagó al fabricar
    # el crudo en su orden de stock de origen).
    empleado_responsable_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    estado = Column(String(50), nullable=False)
    observaciones = Column(Text, nullable=True)
    # Retrabajo: etapa creada en un área que YA tiene una COMPLETADA para la
    # misma orden. La nómina destajo las ignora (evita doble pago del mismo
    # trabajo).
    es_retrabajo = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    orden = relationship("OrdenProduccion", back_populates="etapas")
    area = relationship("Area")
    empleado_responsable = relationship("Empleado", foreign_keys=[empleado_responsable_id])
    consumos = relationship("ConsumoMaterial", back_populates="etapa", cascade="all, delete-orphan")
    mano_obras = relationship("ManoObra", back_populates="etapa", cascade="all, delete-orphan")
    asignados_adicionales = relationship("EtapaAsignadoAdicional", back_populates="etapa", cascade="all, delete-orphan")

class ConsumoMaterial(Base):
    __tablename__ = "consumo_material"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(BigInteger, ForeignKey("etapa_produccion.id", ondelete="CASCADE"), nullable=False)
    material_id = Column(BigInteger, ForeignKey("material.id"), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False)
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    seccion = Column(String(50), nullable=True)
    # --- Confirmación de uso de láminas ---
    # Modo "lámina completa": se piden N láminas enteras (SALIDA inmediata,
    # costo provisional) y quedan PENDIENTE hasta que el trabajador dice cuánto
    # se usó (confirmación por cortes recalcula costo real, ajusta láminas y
    # genera el sobrante). Default CONFIRMADO = flujo inmediato tradicional.
    estado = Column(String(20), nullable=False, server_default="CONFIRMADO", default="CONFIRMADO", index=True)
    # --- Pedido de material (entrega hoy, uso real después) ---
    # `cantidad` = lo que se USÓ (costo final); `cantidad_pedida` conserva lo
    # que se ENTREGÓ al pedir (unidad base). NULL = registro directo de uso
    # (flujo inmediato tradicional, sin pedido previo). Permite que el registro
    # diga cuánto pidieron y cuánto usaron de verdad.
    cantidad_pedida = Column(Numeric(12, 2), nullable=True)
    # --- Consumo por CORTE (materiales laminares) ---
    # Si ancho_corte_cm/largo_corte_cm están definidos, `cantidad` = NÚMERO de
    # cortes de ese tamaño y costo_unitario = costo proporcional al área del
    # corte (no el precio de la lámina completa).
    ancho_corte_cm = Column(Numeric(10, 2), nullable=True)
    largo_corte_cm = Column(Numeric(10, 2), nullable=True)
    # Sobrante del que salieron los cortes (None = láminas nuevas del depósito).
    origen_sobrante_id = Column(BigInteger, ForeignKey("sobrante_lamina.id", ondelete="SET NULL"), nullable=True, index=True)
    # Láminas enteras descontadas del inventario (para reversa exacta).
    laminas_consumidas = Column(Numeric(12, 2), nullable=True)
    # --- Captura flexible de madera (cm/mts, pieza volumétrica) ---
    # `cantidad` guarda SIEMPRE la unidad base (m o m³). Estos campos conservan
    # CÓMO se digitó, para trazabilidad y para mostrarlo en la UI.
    # La conversión vive en app/modules/production/unidades.py.
    unidad_captura = Column(String(5), nullable=True)  # 'M' | 'CM' (None = tal cual)
    pieza_largo = Column(Numeric(10, 2), nullable=True)
    pieza_ancho = Column(Numeric(10, 2), nullable=True)
    pieza_espesor = Column(Numeric(10, 2), nullable=True)
    # --- Componente y consumo extra (alimentan la estructura de costes) ---
    # componente: pieza del mueble a la que se destinó el material (CAMA,
    # NOCHERO, CABECERA...) → genera secciones "SECCIÓN (COMPONENTE)" en la
    # estructura de costes generada desde producción.
    componente = Column(String(50), nullable=True)
    # es_excedente: material usado de MÁS (daño/desperdicio). Cuenta en el
    # costo real de la orden pero se EXCLUYE de la estructura de costes.
    es_excedente = Column(Boolean, default=False, nullable=False, server_default="false")
    motivo_exceso = Column(String(100), nullable=True)
    # Quién PIDE el material (empleado), distinto de creado_por_id (usuario que
    # digita). Obligatorio a nivel de API para trazabilidad/honestidad.
    solicitante_empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=True, index=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha = Column(DateTime, nullable=False)
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    etapa = relationship("EtapaProduccion", back_populates="consumos")
    material = relationship("Material")
    sobrante_origen = relationship("SobranteLamina", foreign_keys=[origen_sobrante_id])
    solicitante = relationship("Empleado", foreign_keys=[solicitante_empleado_id])
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def solicitante_nombre(self):
        return self.solicitante.nombre if self.solicitante else None

class ManoObra(Base):
    __tablename__ = "mano_obra"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(BigInteger, ForeignKey("etapa_produccion.id", ondelete="CASCADE"), nullable=False)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    porcentaje_recargo = Column(Numeric(5, 2), default=0.0, nullable=False)
    pagado = Column(Boolean, default=False, nullable=False)
    listo_nomina = Column(Boolean, default=True, nullable=False)
    observaciones = Column(Text, nullable=True)
    # Tarifario de costos de producción del que salió el monto (trazabilidad).
    precio_produccion_id = Column(BigInteger, ForeignKey("precio_produccion.id", ondelete="SET NULL"), nullable=True, index=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    etapa = relationship("EtapaProduccion", back_populates="mano_obras")
    empleado = relationship("Empleado")
    # Import directo (no string) porque PrecioProduccion vive en otro módulo y
    # puede no estar registrado en el registry al configurar los mappers.
    from app.modules.costos_produccion.model import PrecioProduccion
    precio_produccion = relationship(PrecioProduccion)
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def precio_produccion_descripcion(self):
        return self.precio_produccion.descripcion if self.precio_produccion else None

class CostoProduccion(Base):
    __tablename__ = "costo_produccion"

    id = Column(BigInteger, primary_key=True, index=True)
    orden_produccion_id = Column(BigInteger, ForeignKey("orden_produccion.id", ondelete="CASCADE"), unique=True, nullable=False)
    # Estimado del costo de la orden: precio_costo_base del producto × unidades
    # del detalle. Se congela al calcular el costo para la comparativa vs real.
    costo_estimado = Column(Numeric(15, 2), nullable=True)
    costo_material = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_mano_obra = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_gastos = Column(Numeric(15, 2), default=0.0, nullable=False)
    precio_impuestos_base = Column(Numeric(15, 2), default=0.0, nullable=False)
    ganancia_porcentaje = Column(Numeric(5, 2), default=0.0, nullable=False)
    precio_venta_calculado = Column(Numeric(15, 2), default=0.0, nullable=False)
    costo_total = Column(Numeric(15, 2), default=0.0, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    orden = relationship("OrdenProduccion", back_populates="costo")


class EtapaAsignadoAdicional(Base):
    """Empleados adicionales asignados a una etapa de producción (opcional, multi-empleado)."""
    __tablename__ = "etapa_asignado_adicional"

    id = Column(BigInteger, primary_key=True, index=True)
    etapa_produccion_id = Column(
        BigInteger,
        ForeignKey("etapa_produccion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    etapa = relationship("EtapaProduccion", back_populates="asignados_adicionales")
    empleado = relationship("Empleado")


class ProductoCrudoInventario(Base):
    """Ítem de "inventario en crudo": pieza/semi-elaborado con nombre LIBRE que
    elige el usuario (ej. "esqueleto de cama", "estructura", etc.), sin estar
    atado al catálogo de productos. Usualmente resultado de ebanistería.

    Una sola tabla lleva el catálogo + stock: cada fila es un ítem con su
    `cantidad` disponible. Se fabrica mediante `ProduccionCrudo` (segunda
    producción) y al agotarse su cantidad se puede desactivar.
    """

    __tablename__ = "producto_crudo_inventario"

    id = Column(BigInteger, primary_key=True, index=True)
    # Nombre libre, lo que el usuario quiera.
    nombre = Column(String(200), nullable=False)
    # Área principal del crudo (default EBANISTERÍA). Seleccionable.
    area_id = Column(BigInteger, ForeignKey("area.id"), nullable=True, index=True)
    ubicacion_id = Column(BigInteger, ForeignKey("ubicacion.id", ondelete="RESTRICT"), nullable=False, default=1)
    cantidad = Column(Numeric(12, 2), nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True)
    # La foto de referencia se guarda como adjunto de tipo CRUDO.

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    area = relationship("Area")
    ubicacion = relationship("Ubicacion")
    producciones = relationship(
        "ProduccionCrudo",
        back_populates="crudo",
        cascade="all, delete-orphan",
    )


class MovimientoCrudo(Base):
    """Kardex de un ítem en crudo: cada ENTRADA/SALIDA/AJUSTE/DAÑO/DEVOLUCION
    manual, más las automáticas (ENTRADA al completar una producción,
    SALIDA al asignar a un pedido). Misma semántica que el kardex de
    productos: ENTRADA/DEVOLUCION suman, SALIDA/DAÑO restan (validando
    stock), AJUSTE fija el stock al valor dado.

    El crudo vive en una sola ubicación y no lleva costeo por movimiento,
    así que el formulario es el mismo pero sin ubicación ni precio.
    """

    __tablename__ = "movimiento_crudo"

    id = Column(BigInteger, primary_key=True, index=True)
    crudo_id = Column(BigInteger, ForeignKey("producto_crudo_inventario.id", ondelete="RESTRICT"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)  # ENTRADA | SALIDA | AJUSTE | DAÑO | DEVOLUCION
    cantidad = Column(Numeric(12, 2), nullable=False)
    # Vínculo opcional con lo que originó el movimiento automático.
    referencia_tipo = Column(String(100), nullable=True)  # PRODUCCION | ASIGNACION
    referencia_id = Column(BigInteger, nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    fecha = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())

    crudo = relationship("ProductoCrudoInventario")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None


class ProduccionCrudo(Base):
    """Segunda producción: fabricación de un ítem en crudo. Al marcarla como
    COMPLETADA se suma stock al `ProductoCrudoInventario` correspondiente.
    Los consumos de material se registran con solicitante + quién lo registró,
    igual que la producción por pedidos."""

    __tablename__ = "produccion_crudo"

    id = Column(BigInteger, primary_key=True, index=True)
    crudo_id = Column(
        BigInteger, ForeignKey("producto_crudo_inventario.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    estado = Column(String(50), nullable=False, default="PENDIENTE")  # PENDIENTE | EN_PRODUCCION | COMPLETADA | CANCELADA
    cantidad = Column(Numeric(12, 2), nullable=False, default=1)  # cuántas piezas suma al finalizar
    # Costo acumulado de la producción (suma de consumos de material).
    costo_total = Column(Numeric(15, 2), nullable=False, default=0)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    crudo = relationship("ProductoCrudoInventario", back_populates="producciones")
    consumos = relationship(
        "ProduccionCrudoConsumo",
        back_populates="produccion",
        cascade="all, delete-orphan",
    )
    mano_obras = relationship(
        "ProduccionCrudoManoObra",
        back_populates="produccion",
        cascade="all, delete-orphan",
    )
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def crudo_nombre(self):
        return self.crudo.nombre if self.crudo else None

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def mano_obra_total(self):
        """Suma de la mano de obra con su recargo (monto × (1 + recargo/100))."""
        total = Decimal("0")
        for mo in self.mano_obras or []:
            recargo = Decimal(str(mo.porcentaje_recargo or 0)) / Decimal("100")
            total += Decimal(str(mo.monto)) * (Decimal("1") + recargo)
        return total

    @property
    def costo_mano_obra(self):
        return self.mano_obra_total


class ProduccionCrudoConsumo(Base):
    """Consumo de material en una producción de crudo. Registra quién lo PIDIÓ
    (solicitante_empleado_id) y quién lo REGISTRÓ (creado_por_id), igual que los
    consumos de la producción por pedidos. Al registrar se descuenta del stock
    de material."""

    __tablename__ = "produccion_crudo_consumo"

    id = Column(BigInteger, primary_key=True, index=True)
    produccion_crudo_id = Column(
        BigInteger, ForeignKey("produccion_crudo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id = Column(BigInteger, ForeignKey("material.id"), nullable=False)
    cantidad = Column(Numeric(12, 4), nullable=False)
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    seccion = Column(String(50), nullable=True)
    # --- Consumo por CORTE (materiales laminares), igual que ConsumoMaterial ---
    ancho_corte_cm = Column(Numeric(10, 2), nullable=True)
    largo_corte_cm = Column(Numeric(10, 2), nullable=True)
    origen_sobrante_id = Column(BigInteger, ForeignKey("sobrante_lamina.id", ondelete="SET NULL"), nullable=True, index=True)
    laminas_consumidas = Column(Numeric(12, 2), nullable=True)
    # --- Captura flexible de madera, igual que ConsumoMaterial ---
    unidad_captura = Column(String(5), nullable=True)  # 'M' | 'CM' (None = tal cual)
    pieza_largo = Column(Numeric(10, 2), nullable=True)
    pieza_ancho = Column(Numeric(10, 2), nullable=True)
    pieza_espesor = Column(Numeric(10, 2), nullable=True)
    # --- Componente y consumo extra, igual que ConsumoMaterial ---
    componente = Column(String(50), nullable=True)
    es_excedente = Column(Boolean, default=False, nullable=False, server_default="false")
    motivo_exceso = Column(String(100), nullable=True)
    # Quién PIDE el material (empleado), distinto de creado_por_id (usuario que digita).
    solicitante_empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=True, index=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha = Column(DateTime, nullable=False)
    observaciones = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    produccion = relationship("ProduccionCrudo", back_populates="consumos")
    material = relationship("Material")
    sobrante_origen = relationship("SobranteLamina", foreign_keys=[origen_sobrante_id])
    solicitante = relationship("Empleado", foreign_keys=[solicitante_empleado_id])
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def material_nombre(self):
        return self.material.nombre if self.material else None

    @property
    def solicitante_nombre(self):
        return self.solicitante.nombre if self.solicitante else None

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None


class ProduccionCrudoUso(Base):
    """Trazabilidad de cuándo una pieza de crudo se asigna a un detalle de pedido.
    Al asignar se DESCUENTA stock del ítem en crudo; NO se marcan etapas ni se
    descuentan materiales de nuevo (esos ya se descontaron al producir el crudo)."""

    __tablename__ = "produccion_crudo_uso"

    id = Column(BigInteger, primary_key=True, index=True)
    crudo_id = Column(
        BigInteger, ForeignKey("producto_crudo_inventario.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    detalle_pedido_id = Column(BigInteger, ForeignKey("detalle_pedido.id"), nullable=False, index=True)
    cantidad = Column(Numeric(12, 2), nullable=False, default=1)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())

    crudo = relationship("ProductoCrudoInventario")
    detalle_pedido = relationship("DetallePedido")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])


class ProduccionCrudoManoObra(Base):
    """Mano de obra en una producción de crudo: quién la hizo y cuánto cuesta.

    Al finalizar la producción (COMPLETADA), toda la mano de obra sin pagar
    genera su egreso (Gasto tipo "Mano de Obra de Producción") y se marca pagada,
    materializando el costo de producción que alimenta la nómina.
    """

    __tablename__ = "produccion_crudo_mano_obra"

    id = Column(BigInteger, primary_key=True, index=True)
    produccion_crudo_id = Column(
        BigInteger, ForeignKey("produccion_crudo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    empleado_id = Column(BigInteger, ForeignKey("empleado.id"), nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    porcentaje_recargo = Column(Numeric(5, 2), default=0.0, nullable=False)
    listo_nomina = Column(Boolean, default=True, nullable=False)
    pagado = Column(Boolean, default=False, nullable=False)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    produccion = relationship("ProduccionCrudo", back_populates="mano_obras")
    empleado = relationship("Empleado")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def empleado_nombre(self):
        return self.empleado.nombre if self.empleado else None

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None
