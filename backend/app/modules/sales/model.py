from decimal import Decimal

from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.core.hora_ve import ahora_ve
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
    # Tasa de cambio al momento de la facturación (COP por 1 unidad de moneda de la venta).
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Total convertido a moneda base (COP) con la tasa del día de facturación.
    total_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relaciones
    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="venta")
    descuentos = relationship("DescuentoVenta", back_populates="venta")
    cliente = relationship("Client")
    pedido = relationship("Pedido")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def pedido_estado(self):
        """Estado del pedido vinculado (ENTREGADO = ya despachado y recibido).

        La UI agrupa las cuentas por cobrar con esto: la ubicación del dinero
        pendiente (entregado vs. en proceso) vive en el pedido, no en la venta.
        """
        return self.pedido.estado if self.pedido else None


    from app.modules.productos.model import Producto, Material


class DetalleVenta(Base):
    __tablename__ = "detalle_venta"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=True)
    tipo_item = Column(String(20), nullable=False, server_default="FABRICADO")  # FABRICADO | REVENTA | INSUMO
    cantidad = Column(Numeric(14, 4), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    # Captura flexible del insumo (copiada del pedido): la venta/documentos
    # muestran la unidad vendida (cm/m³) y `cantidad_base` es la que descuenta
    # inventario (p. ej. 1128 cm = 0,1128 m³).
    unidad_captura = Column(String(4), nullable=True)  # 'M' | 'CM'
    cantidad_base = Column(Numeric(14, 4), nullable=True)
    # Snapshot de costos al momento de facturar (para Control Interno de Ingresos)
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    porcentaje_ganancia = Column(Numeric(5, 2), nullable=True)
    utilidad = Column(Numeric(15, 2), nullable=True)
    # Descuento otorgado (opcional, precio ya refleja el descuento; este campo lo documenta)
    descuento = Column(Numeric(15, 2), nullable=True, default=0.0)
    # Descripción del ítem cuando no hay producto (muebles a medida, notas
    # históricas). Se copia del pedido al facturar; el catálogo manda si hay.
    descripcion_especifica = Column(Text, nullable=True)
    # Promo obsequio: línea del plástico de regalo (precio 0, 1 por colchón)
    es_obsequio = Column(Boolean, nullable=False, server_default="false")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")
    material = relationship("Material")


class DescuentoVenta(Base):
    """Rebaja otorgada al cobrar (p. ej. el dueño deja una deuda de 1.150.000
    en 1.000.000): resta del saldo pendiente igual que un pago, pero NO mueve
    dinero a ninguna cuenta de caja (no genera MovimientoCaja).

    Replica la lógica multimoneda de Pago: `tasa_cambio` convierte a la moneda
    de la venta y `monto_en_moneda_base` es lo que realmente descuenta del saldo.
    """

    __tablename__ = "descuento_venta"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(DateTime, nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    # Tasa de cambio usada para convertir a la moneda de la venta.
    # Si la moneda del descuento es igual a la de la venta, tasa_cambio = 1.0
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Monto equivalente en la moneda de la venta ya convertido.
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False)
    # Motivo opcional (p. ej. "acuerdo con el dueño").
    motivo = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="descuentos")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None


class Pago(Base):
    __tablename__ = "pago"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(DateTime, nullable=False)
    monto = Column(Numeric(15, 2), nullable=False)
    # Tasa de cambio usada para convertir a la moneda base de la venta.
    # Si la moneda del pago es igual a la de la venta, tasa_cambio = 1.0
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Monto equivalente en la moneda base (moneda de la venta) ya convertido.
    # Es el valor que realmente se descuenta del saldo pendiente.
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False)
    # EFECTIVO_COP | EFECTIVO_USD | EFECTIVO_VES | BANCOLOMBIA | BANCARIBE | ZELLE | BINANCE
    metodo_pago = Column(String(50), nullable=False)
    # Recibido y aplicado son distintos cuando el cliente deja un excedente.
    # NULL conserva la lectura de los pagos históricos.
    monto_aplicado = Column(Numeric(15, 2), nullable=True)
    tipo = Column(String(20), nullable=False, server_default="COBRO", default="COBRO")
    operacion_id = Column(String(36), nullable=True, unique=True)
    referencia = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)
    # Quién digitó el cobro. La fecha del pago (`fecha`) puede ser anterior;
    # este campo y `created_at` conservan la trazabilidad del registro.
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    venta = relationship("Venta", back_populates="pagos")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    correcciones = relationship(
        "PagoCorreccion",
        back_populates="pago",
        cascade="all, delete-orphan",
        order_by="PagoCorreccion.id",
    )
    credito_generado = relationship("SaldoFavor", back_populates="pago_origen", uselist=False)
    aplicacion_credito = relationship("AplicacionSaldoFavor", back_populates="pago", uselist=False)

    @property
    def saldo_favor_generado(self):
        credito = self.credito_generado
        return float(credito.monto) if credito and not credito.anulado else 0.0

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None

    @property
    def recibos(self):
        """Comprobantes digitales del pago (adjuntos tipo PAGO)."""
        from sqlalchemy.orm import object_session
        from app.modules.adjuntos.service import adjuntos_info
        s = object_session(self)
        if s is None:
            return []
        return adjuntos_info(s, "PAGO", self.id)


class PagoCorreccion(Base):
    """Historial de correcciones del MONTO de un abono.

    Un cobro digitado mal se corrige sin borrarlo ni crear otro pago: se
    ajusta `Pago.monto` / `Pago.monto_en_moneda_base`, se actualiza su
    movimiento de caja y se deja aquí la huella de antes y después. La
    cotización y los documentos imprimibles muestran el monto vigente, pero
    NO este historial: la trazabilidad vive en Ventas y Cobros y en la
    auditoría del sistema.
    """

    __tablename__ = "pago_correccion"

    id = Column(BigInteger, primary_key=True, index=True)
    pago_id = Column(
        BigInteger,
        ForeignKey("pago.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id = Column(
        BigInteger,
        ForeignKey("usuario.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    monto_anterior = Column(Numeric(15, 2), nullable=False)
    monto_nuevo = Column(Numeric(15, 2), nullable=False)
    # Equivalente en la moneda de la venta antes y después de la corrección.
    monto_base_anterior = Column(Numeric(15, 2), nullable=False)
    monto_base_nuevo = Column(Numeric(15, 2), nullable=False)
    motivo = Column(Text, nullable=True)
    # Momento de la corrección (hora Venezuela). `Pago.created_at` conserva
    # intacto el momento en que se digitó el cobro original.
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    pago = relationship("Pago", back_populates="correcciones")
    usuario = relationship("Usuario", foreign_keys=[usuario_id])

    @property
    def usuario_nombre(self):
        return (self.usuario.nombre or self.usuario.nombre_usuario) if self.usuario else None


class SaldoFavor(Base):
    """Lote de crédito en la moneda recibida. Su uso se registra por separado."""

    __tablename__ = "saldo_favor"
    __table_args__ = (CheckConstraint("monto >= 0", name="ck_saldo_favor_monto"),)

    id = Column(BigInteger, primary_key=True)
    cliente_id = Column(ForeignKey("cliente.id", ondelete="RESTRICT"), nullable=False, index=True)
    moneda_id = Column(ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    pago_origen_id = Column(ForeignKey("pago.id", ondelete="SET NULL"), nullable=True, unique=True)
    monto = Column(Numeric(15, 2), nullable=False)
    origen = Column(String(30), nullable=False, default="EXCEDENTE_PAGO")
    referencia = Column(String(150), nullable=False)
    anulado = Column(Boolean, nullable=False, default=False, server_default="false")
    creado_por_id = Column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=ahora_ve)

    cliente = relationship("Client")
    moneda = relationship("Moneda")
    pago_origen = relationship("Pago", back_populates="credito_generado")
    aplicaciones = relationship("AplicacionSaldoFavor", back_populates="credito")
    creador = relationship("Usuario")

    @property
    def monto_usado(self):
        return sum((a.monto for a in self.aplicaciones), Decimal("0"))

    @property
    def saldo(self):
        return Decimal("0") if self.anulado else self.monto - self.monto_usado

    @property
    def cliente_nombre(self):
        return self.cliente.nombre

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None


class AplicacionSaldoFavor(Base):
    """Consumo de un lote; al revertirlo se devuelve exactamente esta moneda."""

    __tablename__ = "aplicacion_saldo_favor"
    __table_args__ = (CheckConstraint("monto > 0", name="ck_aplicacion_saldo_favor_monto"),)

    id = Column(BigInteger, primary_key=True)
    saldo_favor_id = Column(ForeignKey("saldo_favor.id", ondelete="RESTRICT"), nullable=False, index=True)
    pago_id = Column(ForeignKey("pago.id", ondelete="RESTRICT"), nullable=False, unique=True)
    monto = Column(Numeric(15, 2), nullable=False)

    credito = relationship("SaldoFavor", back_populates="aplicaciones")
    pago = relationship("Pago", back_populates="aplicacion_credito")
