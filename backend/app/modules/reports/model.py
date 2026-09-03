from sqlalchemy import Column, Integer, BigInteger, Numeric, String, Date, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class ConceptoReporte(Base):
    """
    Catálogo FLEXIBLE de líneas del informe mensual (ej. líneas de inventario
    inicial/final: MDF e Insumos, Melamina, Colchones, Electrodomésticos...).
    El usuario puede renombrar, agregar o desactivar líneas sin tocar código.
    """
    __tablename__ = "concepto_reporte"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    seccion = Column(String(50), nullable=False, default="INVENTARIO")  # INVENTARIO | extensible
    orden = Column(Integer, default=1, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class ValorConceptoMensual(Base):
    """
    Valores de corte mensual de cada concepto (inventario inicial y final).
    El usuario los digita al cierre del mes.
    """
    __tablename__ = "valor_concepto_mensual"

    id = Column(BigInteger, primary_key=True, index=True)
    mes = Column(String(7), nullable=False, index=True)  # YYYY-MM
    concepto_id = Column(BigInteger, ForeignKey("concepto_reporte.id", ondelete="CASCADE"), nullable=False)
    valor_inicial = Column(Numeric(15, 2), nullable=False, default=0.0)
    valor_final = Column(Numeric(15, 2), nullable=False, default=0.0)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, default=1)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    concepto = relationship("ConceptoReporte")
    moneda = relationship("Moneda")


class MetodoCaja(Base):
    """
    Catálogo de métodos/cuentas de caja (EFECTIVO PESOS, BANCOLOMBIA, ZELLE,
    BANCARIBE, EFECTIVO USD, EFECTIVO VES...). Editable por el usuario.
    """
    __tablename__ = "metodo_caja"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    codigo = Column(String(50), nullable=False, unique=True)
    activo = Column(Boolean, default=True, nullable=False)
    orden = Column(Integer, default=1, nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    moneda = relationship("Moneda")

    @property
    def moneda_codigo(self):
        return self.moneda.codigo if self.moneda else None

    @property
    def moneda_simbolo(self):
        return self.moneda.simbolo if self.moneda else None


class MovimientoCaja(Base):
    """
    Seguimiento CONTINUO de caja: cada entrada/salida/ajuste lleva su fecha,
    moneda y tasa del momento. El saldo por método se calcula sumando
    movimientos hasta la fecha: APERTURA/ENTRADA suman, SALIDA resta,
    AJUSTE suma/resta según el signo del monto.

    `pago_id` vincula el movimiento con el pago de venta que lo originó
    (se genera automáticamente al registrar un cobro). Permite limpiar el
    movimiento si el pago se elimina y evitar duplicados.

    `transferencia_id` empareja las dos patas de una transferencia entre
    cuentas (SALIDA en origen + ENTRADA en destino): una sola operación
    contable que redistribuye saldo sin tocar el total del negocio.
    """
    __tablename__ = "movimiento_caja"

    id = Column(BigInteger, primary_key=True, index=True)
    metodo_caja_id = Column(BigInteger, ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=False)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    pago_id = Column(BigInteger, ForeignKey("pago.id", ondelete="CASCADE"), nullable=True, index=True)
    fecha = Column(Date, nullable=False)
    tipo = Column(String(20), nullable=False)  # APERTURA | ENTRADA | SALIDA | AJUSTE
    monto = Column(Numeric(15, 2), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, default=1)
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    transferencia_id = Column(BigInteger, nullable=True, index=True)
    referencia = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    metodo_caja = relationship("MetodoCaja")
    moneda = relationship("Moneda")
    usuario = relationship("Usuario")
    pago = relationship("Pago")


class DevolucionVenta(Base):
    """
    Devolución de una venta (p. ej. cuando algo salió mal en el despacho).
    Al registrarla, la línea sale del Control Interno de Ingresos del mes
    y se refleja en (-) Devoluciones sobre ventas del Estado de Resultados.
    """
    __tablename__ = "devolucion_venta"

    id = Column(BigInteger, primary_key=True, index=True)
    venta_id = Column(BigInteger, ForeignKey("venta.id", ondelete="RESTRICT"), nullable=False)
    detalle_venta_id = Column(BigInteger, ForeignKey("detalle_venta.id", ondelete="SET NULL"), nullable=True)
    fecha = Column(Date, nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False, default=1.0)
    motivo = Column(Text, nullable=True)
    monto_devuelto = Column(Numeric(15, 2), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False, default=1)
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    venta = relationship("Venta")
    detalle_venta = relationship("DetalleVenta")
    moneda = relationship("Moneda")
