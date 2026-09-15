from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime


# ------------------------------------------------------------
# P&L (existente)
# ------------------------------------------------------------
class PnLDetail(BaseModel):
    moneda: str
    ingresos: Decimal
    gastos: Decimal
    balance: Decimal
    # Equivalentes en COP (moneda base): antes el P&L mezclaba USD con COP
    # brutos y el balance no era comparable entre monedas.
    ingresos_cop: Decimal = Decimal("0.0")
    gastos_cop: Decimal = Decimal("0.0")
    balance_cop: Decimal = Decimal("0.0")

class PnLResponse(BaseModel):
    mes: str
    detalles: List[PnLDetail]

class RentabilidadProductoResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    cantidad_vendida: float
    precio_promedio_venta: float
    costo_promedio_produccion: float
    margen_promedio: float
    moneda: str

class ReportAlertaStockResponse(BaseModel):
    material_id: int
    material_nombre: str
    cantidad_actual: float
    umbral: float
    unidad_medida: str
    ubicacion_nombre: str


# ------------------------------------------------------------
# Catálogos flexibles del Informe Mensual
# ------------------------------------------------------------
class ConceptoReporteBase(BaseModel):
    nombre: str
    seccion: str = "INVENTARIO"
    orden: int = 1
    activo: bool = True

class ConceptoReporteCreate(ConceptoReporteBase):
    pass

class ConceptoReporteUpdate(BaseModel):
    nombre: Optional[str] = None
    seccion: Optional[str] = None
    orden: Optional[int] = None
    activo: Optional[bool] = None

class ConceptoReporteResponse(ConceptoReporteBase):
    id: int

    class Config:
        from_attributes = True


class ValorConceptoMensualBase(BaseModel):
    mes: str
    concepto_id: int
    valor_inicial: Decimal = Decimal("0.00")
    valor_final: Decimal = Decimal("0.00")
    moneda_id: int = 1
    observaciones: Optional[str] = None

class ValorConceptoMensualCreate(ValorConceptoMensualBase):
    pass

class ValorConceptoMensualUpdate(BaseModel):
    valor_inicial: Optional[Decimal] = None
    valor_final: Optional[Decimal] = None
    observaciones: Optional[str] = None

class ValorConceptoMensualResponse(ValorConceptoMensualBase):
    id: int
    concepto: Optional[ConceptoReporteResponse] = None

    class Config:
        from_attributes = True


class MetodoCajaBase(BaseModel):
    nombre: str
    codigo: str
    activo: bool = True
    orden: int = 1
    moneda_id: Optional[int] = None

class MetodoCajaCreate(MetodoCajaBase):
    pass

class MetodoCajaUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None
    moneda_id: Optional[int] = None

class MetodoCajaResponse(MetodoCajaBase):
    id: int
    moneda_codigo: Optional[str] = None
    moneda_simbolo: Optional[str] = None

    class Config:
        from_attributes = True


class ResponsableResponse(BaseModel):
    """Usuario responsable de haber registrado un movimiento de caja.

    `nombre` es el nombre real (display_name); `nombre_usuario` queda por
    compatibilidad pero la UI debe mostrar `nombre` con fallback.
    """
    id: int
    nombre_usuario: str
    nombre: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class MovimientoCajaBase(BaseModel):
    metodo_caja_id: int
    fecha: date
    tipo: str = Field(..., pattern="^(APERTURA|ENTRADA|SALIDA|AJUSTE)$")
    # monto > 0: la dirección del flujo la expresa el tipo (una SALIDA negativa
    # INGRESABA dinero a la cuenta y permitía drenar caja con un solo request).
    monto: Decimal = Field(..., gt=0)
    moneda_id: int = 1
    tasa_cambio: Decimal = Decimal("1.0")
    referencia: Optional[str] = None
    observaciones: Optional[str] = None

class MovimientoCajaCreate(MovimientoCajaBase):
    pass

class MovimientoCajaUpdate(BaseModel):
    metodo_caja_id: Optional[int] = None
    fecha: Optional[date] = None
    tipo: Optional[str] = None
    monto: Optional[Decimal] = None
    observaciones: Optional[str] = None
    referencia: Optional[str] = None

class MovimientoCajaResponse(MovimientoCajaBase):
    id: int
    usuario_id: Optional[int] = None
    monto_en_moneda_base: Optional[Decimal] = None
    transferencia_id: Optional[int] = None
    created_at: Optional[datetime] = None
    metodo_caja: Optional[MetodoCajaResponse] = None
    moneda: Optional["MonedaResponse"] = None
    usuario: Optional[ResponsableResponse] = None


# ------------------------------------------------------------
# Transferencias entre cuentas de caja
# ------------------------------------------------------------
class TransferenciaCreate(BaseModel):
    cuenta_origen_id: int
    cuenta_destino_id: int
    monto: Decimal = Field(..., gt=0)
    fecha: Optional[date] = None
    # Moneda en que sale el dinero. Default: la moneda propia de la cuenta
    # origen (o COP si la cuenta no tiene moneda asignada).
    moneda_id: Optional[int] = None
    # Tasa moneda de salida → COP. Opcional: si se omite se usa la TRM
    # registrada a la fecha; si se indica, no puede desviarse más de 50%.
    tasa_cambio: Optional[Decimal] = Field(None, gt=0)
    referencia: Optional[str] = None
    observaciones: Optional[str] = None


class TransferenciaResponse(BaseModel):
    """Una transferencia con sus dos patas (SALIDA en origen, ENTRADA en destino)."""
    transferencia_id: int
    fecha: date
    monto_salida: Decimal
    monto_entrada: Decimal
    moneda_salida_codigo: str
    moneda_entrada_codigo: str
    tasa_cambio: Decimal
    saldo_disponible_origen: Decimal = Decimal("0.0")
    referencia: Optional[str] = None
    observaciones: Optional[str] = None
    pata_salida: MovimientoCajaResponse
    pata_entrada: MovimientoCajaResponse


class ListTransferenciasResponse(BaseModel):
    transferencias: List[TransferenciaResponse] = []

class ResumenCuentaResponse(BaseModel):
    """Saldo de una cuenta, por moneda (monto en su propia moneda).

    Sin conversión a COP: la tasa cambia a diario y se ingresa manualmente en
    cada operación; consolidar saldos con tasas históricas mezcladas no tiene
    sentido contable.
    """
    metodo_caja: MetodoCajaResponse
    saldo_por_moneda: List["LineaSaldoMoneda"] = []

class LineaSaldoMoneda(BaseModel):
    moneda_id: int
    codigo: str
    simbolo: str
    monto: Decimal = Decimal("0.0")

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Reporte diario (estado del día)
# ------------------------------------------------------------
class MovimientoDiarioResponse(BaseModel):
    """Un movimiento de caja del día con concepto legible y responsable."""
    id: int
    tipo: str  # APERTURA | ENTRADA | SALIDA | AJUSTE
    moneda_codigo: str
    moneda_simbolo: str
    monto: Decimal = Decimal("0.0")
    monto_cop: Decimal = Decimal("0.0")
    cuenta_nombre: Optional[str] = None
    referencia: Optional[str] = None
    concepto: str
    quien: Optional[str] = None

class LineaMonedaDiaria(BaseModel):
    moneda_id: int
    codigo: str
    simbolo: str
    monto_ingresos: Decimal = Decimal("0.0")
    monto_egresos: Decimal = Decimal("0.0")
    monto_cop: Decimal = Decimal("0.0")

class SaldoCuentaDiaria(BaseModel):
    """Saldo de una cuenta en el día, desglosado por moneda.

    `saldo_inicial/final` van en la moneda nativa (`moneda_codigo`); los
    `*_cop` son solo referencia convertida. Una cuenta puede tener varias
    filas (una por moneda con movimiento).
    """
    metodo_caja_id: int
    cuenta_nombre: str
    moneda_codigo: str = "?"
    moneda_simbolo: str = "?"
    saldo_inicial: Decimal = Decimal("0.0")
    saldo_final: Decimal = Decimal("0.0")
    saldo_inicial_cop: Decimal = Decimal("0.0")
    saldo_final_cop: Decimal = Decimal("0.0")


class MonedaVistaDiaria(BaseModel):
    """Una moneda con movimiento en el día, ofrecida como vista (tab).

    Sin conversión: cada vista muestra su moneda en valor nativo.
    """
    moneda_id: int
    codigo: str
    simbolo: str

class ResumenDiarioResponse(BaseModel):
    fecha: date
    saldo_inicial_cop: Decimal = Decimal("0.0")
    total_ingresos_cop: Decimal = Decimal("0.0")
    total_egresos_cop: Decimal = Decimal("0.0")
    saldo_final_cop: Decimal = Decimal("0.0")
    # Vista en la moneda pedida (?moneda=USD): mismos totales pero SOLO con
    # movimientos de esa moneda, en su valor nativo. Sin conversión ni tasas.
    moneda_vista: str = "COP"
    moneda_vista_simbolo: str = "$"
    saldo_inicial_vista: Decimal = Decimal("0.0")
    total_ingresos_vista: Decimal = Decimal("0.0")
    total_egresos_vista: Decimal = Decimal("0.0")
    saldo_final_vista: Decimal = Decimal("0.0")
    # Monedas con movimiento en el día (tabs de la UI). COP siempre va.
    monedas: List[MonedaVistaDiaria] = []
    movimientos: List[MovimientoDiarioResponse] = []
    por_moneda: List[LineaMonedaDiaria] = []
    saldos_por_cuenta: List[SaldoCuentaDiaria] = []


class DevolucionVentaBase(BaseModel):
    venta_id: int
    detalle_venta_id: Optional[int] = None
    fecha: date
    cantidad: Decimal = Decimal("1.0")
    motivo: Optional[str] = None
    # La devolución no puede superar lo efectivamente cobrado en la venta:
    # una devolución de 999M sobre una venta de 2.7M era aceptada.
    monto_devuelto: Decimal = Field(..., gt=0)
    moneda_id: int = 1
    tasa_cambio: Decimal = Field(Decimal("1.0"), gt=0)

class DevolucionVentaCreate(DevolucionVentaBase):
    pass

class DevolucionVentaUpdate(BaseModel):
    detalle_venta_id: Optional[int] = None
    fecha: Optional[date] = None
    cantidad: Optional[Decimal] = None
    motivo: Optional[str] = None
    monto_devuelto: Optional[Decimal] = None

class DevolucionVentaResponse(DevolucionVentaBase):
    id: int
    monto_en_moneda_base: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    venta: Optional["VentaResponse"] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Informe Mensual
# ------------------------------------------------------------
class LineaIngresoInforme(BaseModel):
    fecha: date
    cliente: str
    cantidad: Decimal
    producto: str
    costo_unitario: Decimal
    precio_costo: Decimal
    porcentaje_ganancia: Optional[Decimal]
    utilidad: Decimal
    precio_venta: Decimal
    descuento: Decimal
    moneda: str
    # TRM de referencia moneda → COP. None cuando no hay tasa confiable
    # (ni la congelada de la venta ni TRM registrada en el catálogo): mostrar
    # el equivalente en COP fabricado (1 USD = 1 COP) descuadraba el informe.
    tasa_cambio: Optional[Decimal] = None
    precio_venta_en_base: Optional[Decimal] = None
    es_devolucion: bool

class TotalesIngresoInforme(BaseModel):
    precio_costo: Decimal
    utilidad: Decimal
    precio_venta: Decimal
    precio_venta_en_base: Decimal
    descuentos: Decimal

class TotalesPorMonedaInforme(BaseModel):
    """TOTALES de la sección 1 separados por moneda: sumar costos/ventas de
    monedas distintas en una sola cifra mezclaba USD con COP."""
    moneda: str
    precio_costo: Decimal = Decimal("0.0")
    utilidad: Decimal = Decimal("0.0")
    precio_venta: Decimal = Decimal("0.0")
    # Equivalente COP solo para la fila COP (nativo); en monedas extranjeras
    # queda None si no hay TRM confiable.
    precio_venta_en_base: Optional[Decimal] = None
    descuentos: Decimal = Decimal("0.0")

class ControlInternoIngresos(BaseModel):
    lineas: List[LineaIngresoInforme]
    totales: TotalesIngresoInforme
    totales_por_moneda: List[TotalesPorMonedaInforme] = []

class ResumenMoneda(BaseModel):
    """Ingresos/egresos/dispodible de UNA moneda, en su moneda nativa."""
    moneda: str
    ingresos: Decimal = Decimal("0.0")
    egresos: Decimal = Decimal("0.0")
    disponible: Decimal = Decimal("0.0")

class ResumenMes(BaseModel):
    ingresos: Decimal
    egresos: Decimal
    disponible: Decimal
    # Desglose por moneda (cifras nativas, sin conversiones). Es la fuente
    # de verdad; ingresos/egresos/disponible planos quedan por compatibilidad
    # y reflejan solo el renglón COP.
    por_moneda: List[ResumenMoneda] = []

class LineaValorConcepto(BaseModel):
    concepto_id: int
    nombre: str
    valor: Decimal
    # Código de la moneda en que el valor es nativo (inventarios manuales
    # pueden registrarse en moneda distinta de COP).
    moneda: Optional[str] = None

class VentasEstadoResultados(BaseModel):
    contado: Decimal
    credito: Decimal
    extraordinarias: Decimal
    devoluciones: Decimal
    descuentos: Decimal
    total_ventas_netas: Decimal

class ComprasEstadoResultados(BaseModel):
    contado: Decimal
    credito: Decimal
    total_compras_brutas: Decimal
    total_mercancia: Decimal

class LineaGastoInforme(BaseModel):
    tipo_id: int
    nombre: str
    monto: Decimal

class GastosEstadoResultados(BaseModel):
    operativos: List[LineaGastoInforme]
    administrativos: List[LineaGastoInforme]
    financieros: List[LineaGastoInforme]
    impuestos: List[LineaGastoInforme]
    produccion: List[LineaGastoInforme] = []
    total_gastos_operativos: Decimal
    total_gastos_administrativos: Decimal
    total_financieros: Decimal
    total_impuestos: Decimal
    total_gastos_produccion: Decimal = Decimal("0.0")
    total_gastos: Decimal

class EstadoResultados(BaseModel):
    ventas: VentasEstadoResultados
    inventarios_iniciales: List[LineaValorConcepto]
    total_inventarios_iniciales: Decimal
    compras: ComprasEstadoResultados
    inventarios_finales: List[LineaValorConcepto]
    total_inventarios_finales: Decimal
    compras_netas: Decimal
    utilidad_bruta: Decimal
    gastos: GastosEstadoResultados
    utilidad_periodo: Decimal

class EstadoPorMoneda(BaseModel):
    """Estado de resultados desglosado por moneda, todo en cifras nativas
    (sin conversiones): las equivalencias en COP con TRM mezclada descuadran
    el informe cuando las ventas conviven en varias monedas."""
    moneda: str
    ventas: VentasEstadoResultados
    inventarios_iniciales: List[LineaValorConcepto] = []
    total_inventarios_iniciales: Decimal = Decimal("0.0")
    compras: ComprasEstadoResultados
    inventarios_finales: List[LineaValorConcepto] = []
    total_inventarios_finales: Decimal = Decimal("0.0")
    compras_netas: Decimal = Decimal("0.0")
    utilidad_bruta: Decimal = Decimal("0.0")
    gastos: GastosEstadoResultados
    utilidad_periodo: Decimal = Decimal("0.0")

class PendientePagoLinea(BaseModel):
    pedido_id: int
    venta_id: Optional[int] = None
    fecha: date
    cliente: str
    producto: str
    estado_pedido: str
    estado_venta: Optional[str] = None
    moneda: str
    total_en_base: Decimal
    pagado_en_base: Decimal
    saldo_en_base: Decimal
    # Saldo en la moneda nativa del pedido/venta (sin conversión). Es la
    # cifra confiable; *_en_base es solo referencia COP.
    total_en_moneda: Optional[Decimal] = None
    pagado_en_moneda: Optional[Decimal] = None
    saldo_en_moneda: Optional[Decimal] = None

class SaldoPorMoneda(BaseModel):
    moneda: str
    saldo: Decimal = Decimal("0.0")

class PendientesDePagoInforme(BaseModel):
    lineas: List[PendientePagoLinea]
    total_pendiente: Decimal
    total_pendiente_por_moneda: List[SaldoPorMoneda] = []

class LineaSaldoCajaInforme(BaseModel):
    """Saldo de una cuenta de caja al cierre, en su moneda nativa."""
    metodo_caja_id: int
    nombre: str
    moneda: str
    saldo: Decimal = Decimal("0.0")

class InformeMensualResponse(BaseModel):
    mes: str
    control_interno_ingresos: ControlInternoIngresos
    resumen: ResumenMes
    estado_resultados: EstadoResultados
    pendientes_de_pago: PendientesDePagoInforme
    # Saldos de caja al cierre por cuenta, en la moneda de la cuenta. Antes se
    # mezclaban con los inventarios finales fabricando utilidad ficticia y se
    # consolidaban en COP con tasas históricas mezcladas.
    saldos_caja: List[LineaSaldoCajaInforme] = []
    # Desglose completo del estado de resultados por moneda (nativo).
    estado_resultados_por_moneda: List[EstadoPorMoneda] = []


# Rebuilds para referencias circulares
from app.modules.catalogos.schemas import MonedaResponse  # noqa: E402
from app.modules.sales.schemas import VentaResponse  # noqa: E402
MovimientoCajaResponse.model_rebuild()
ResumenCuentaResponse.model_rebuild()
DevolucionVentaResponse.model_rebuild()
