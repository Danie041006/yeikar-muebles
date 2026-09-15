from sqlalchemy.orm import Session
from sqlalchemy import func, extract, orm as sa_orm
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime, date
import calendar

from app.modules.sales.model import Pago, Venta, DetalleVenta
from app.modules.gastos.model import Gasto
from app.modules.catalogos.model import Moneda, UnidadMedida, TipoGasto
from app.modules.productos.model import Producto
from app.modules.production.model import CostoProduccion, OrdenProduccion, ManoObra, EtapaProduccion
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.purchases.model import Compra, DetalleCompra
from app.modules.inventory.model import Inventario
from app.modules.reports import schemas, model
from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop
from app.modules.tasas_cambio.model import TasaCambio
from app.modules.auditoria.service import record_event
from app.modules.cuentas_por_pagar.model import CuentaPorPagar, PagoCuentaPorPagar
from app.modules.users.model import Usuario

def obtener_pnl(db: Session, mes: str) -> schemas.PnLResponse:
    try:
        year, month = map(int, mes.split("-"))
    except ValueError:
        raise ValueError("Formato de mes inválido. Debe ser YYYY-MM")

    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0)
    end_dt = datetime(year, month, last_day, 23, 59, 59)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    # 1. Obtener ingresos por moneda (pagos recibidos), en bruto y en COP.
    #    La conversión usa la tasa congelada de cada pago (monto_en_moneda_base).
    ingresos_query = (
        db.query(
            Moneda.codigo,
            func.sum(Pago.monto).label("total"),
            func.sum(Pago.monto_en_moneda_base).label("total_cop"),
        )
        .join(Pago, Pago.moneda_id == Moneda.id)
        .filter(Pago.fecha >= start_dt, Pago.fecha <= end_dt)
        .group_by(Moneda.codigo)
        .all()
    )
    ingresos_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in ingresos_query}
    ingresos_cop_dict = {row.codigo: Decimal(str(row.total_cop or 0.0)) for row in ingresos_query}

    # 2a. Obtener gastos generales por moneda (bruto y COP con su tasa del día)
    gastos_query = (
        db.query(
            Moneda.codigo,
            func.sum(Gasto.monto).label("total"),
            func.sum(Gasto.monto_en_moneda_base).label("total_cop"),
        )
        .join(Gasto, Gasto.moneda_id == Moneda.id)
        .filter(Gasto.fecha >= start_date, Gasto.fecha <= end_date)
        .group_by(Moneda.codigo)
        .all()
    )
    gastos_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in gastos_query}
    gastos_cop_dict = {row.codigo: Decimal(str(row.total_cop or 0.0)) for row in gastos_query}

    # 2b. Obtener compras de materiales en estado RECIBIDA por moneda (bruto y COP)
    compras_query = (
        db.query(
            Moneda.codigo,
            func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario).label("total"),
            func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario * Compra.tasa_cambio).label("total_cop"),
        )
        .select_from(DetalleCompra)
        .join(Compra, DetalleCompra.compra_id == Compra.id)
        .join(Moneda, Compra.moneda_id == Moneda.id)
        .filter(Compra.fecha >= start_date, Compra.fecha <= end_date, Compra.estado == "RECIBIDA")
        .group_by(Moneda.codigo)
        .all()
    )
    compras_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in compras_query}
    compras_cop_dict = {row.codigo: Decimal(str(row.total_cop or 0.0)) for row in compras_query}

    # 2c. Mano de obra pagada. Se paga en COP SIEMPRE (a los trabajadores se les
    #     paga en pesos, sin importar la moneda en que el cliente pagó la venta),
    #     así que va al grupo COP tanto en bruto como en equivalente.
    mano_obra_list = (
        db.query(ManoObra)
        .select_from(ManoObra)
        .filter(ManoObra.updated_at >= start_dt, ManoObra.updated_at <= end_dt, ManoObra.pagado == True)
        .all()
    )

    mano_obra_dict = {"COP": Decimal("0.0")}
    mano_obra_cop_dict = {"COP": Decimal("0.0")}
    for mo in mano_obra_list:
        recargo = Decimal(str(mo.porcentaje_recargo or 0.0)) / Decimal("100.0")
        monto_total = Decimal(str(mo.monto)) * (Decimal("1.0") + recargo)
        mano_obra_dict["COP"] += monto_total
        mano_obra_cop_dict["COP"] += monto_total

    # 3. Combinar todas las monedas (bruto + equivalente COP)
    todas_monedas = set(ingresos_dict.keys()).union(gastos_dict.keys(), compras_dict.keys(), mano_obra_dict.keys())
    detalles = []
    for cod in todas_monedas:
        ing = ingresos_dict.get(cod, Decimal("0.0"))
        gas = gastos_dict.get(cod, Decimal("0.0"))
        com = compras_dict.get(cod, Decimal("0.0"))
        mo_val = mano_obra_dict.get(cod, Decimal("0.0"))
        ing_cop = ingresos_cop_dict.get(cod, Decimal("0.0"))
        gas_cop = gastos_cop_dict.get(cod, Decimal("0.0"))
        com_cop = compras_cop_dict.get(cod, Decimal("0.0"))
        mo_cop = mano_obra_cop_dict.get(cod, Decimal("0.0"))

        # Egresos totales = Gastos generales + Compras recibidas + Mano de obra pagada
        egresos_totales = gas + com + mo_val
        egresos_cop = gas_cop + com_cop + mo_cop

        detalles.append(
            schemas.PnLDetail(
                moneda=cod,
                ingresos=ing,
                gastos=egresos_totales,
                balance=ing - egresos_totales,
                ingresos_cop=ing_cop,
                gastos_cop=egresos_cop,
                balance_cop=ing_cop - egresos_cop,
            )
        )

    return schemas.PnLResponse(mes=mes, detalles=detalles)


def obtener_rentabilidad_productos(db: Session) -> List[schemas.RentabilidadProductoResponse]:
    # Obtener todos los productos
    productos = db.query(Producto).filter(Producto.activo == True).all()
    if not productos:
        return []

    producto_ids = [p.id for p in productos]

    # 1. UNA sola query con las ventas de TODOS los productos (agrupada),
    #    en lugar de 1 query por producto (evita N+1).
    ventas_info = (
        db.query(
            DetalleVenta.producto_id,
            Venta.moneda_id,
            func.sum(DetalleVenta.cantidad).label("cantidad"),
            func.sum(DetalleVenta.cantidad * DetalleVenta.precio).label("ingreso_total")
        )
        .join(Venta, DetalleVenta.venta_id == Venta.id)
        .filter(DetalleVenta.producto_id.in_(producto_ids))
        .group_by(DetalleVenta.producto_id, Venta.moneda_id)
        .all()
    )
    ventas_por_producto: Dict[int, list] = {}
    for row in ventas_info:
        ventas_por_producto.setdefault(row.producto_id, []).append(row)

    # 2. UNA sola query con el costo promedio de producción por producto
    costos_info = (
        db.query(
            DetallePedido.producto_id,
            func.avg(CostoProduccion.costo_total).label("costo_promedio")
        )
        .join(OrdenProduccion, CostoProduccion.orden_produccion_id == OrdenProduccion.id)
        .join(DetallePedido, OrdenProduccion.detalle_pedido_id == DetallePedido.id)
        .filter(DetallePedido.producto_id.in_(producto_ids), OrdenProduccion.estado == "FINALIZADA")
        .group_by(DetallePedido.producto_id)
        .all()
    )
    costos_por_producto = {row.producto_id: float(row.costo_promedio or 0.0) for row in costos_info}

    # 3. Monedas cargadas una sola vez (tabla pequeña)
    monedas = {m.id: m.codigo for m in db.query(Moneda).all()}

    resultados = []
    for prod in productos:
        costo_medio = costos_por_producto.get(prod.id, 0.0)

        for v in ventas_por_producto.get(prod.id, []):
            moneda_cod = monedas.get(v.moneda_id, "USD")
            cant = float(v.cantidad or 0.0)
            ing_tot = float(v.ingreso_total or 0.0)
            px_prom = ing_tot / cant if cant > 0 else 0.0
            
            # Margen = precio venta - costo
            margen = px_prom - costo_medio

            resultados.append(
                schemas.RentabilidadProductoResponse(
                    producto_id=prod.id,
                    producto_nombre=prod.nombre,
                    cantidad_vendida=cant,
                    precio_promedio_venta=px_prom,
                    costo_promedio_produccion=costo_medio,
                    margen_promedio=margen,
                    moneda=moneda_cod
                )
            )

    return resultados


def obtener_alertas_stock(db: Session, umbral: Decimal) -> List[schemas.ReportAlertaStockResponse]:
    # Consultamos inventarios por debajo del umbral
    query = (
        db.query(Inventario)
        .filter(Inventario.cantidad <= umbral)
        .all()
    )
    
    resultados = []
    for inv in query:
        # Traemos material y ubicación manualmente para evitar fallos si joinedload tiene issues
        material = inv.material
        ubicacion = inv.ubicacion
        if material:
            # obtener abreviatura unidad
            um_abrev = "und"
            unidad = db.query(UnidadMedida).filter(UnidadMedida.id == material.unidad_medida_id).first()
            if unidad:
                um_abrev = unidad.abreviatura
                
            resultados.append(
                schemas.ReportAlertaStockResponse(
                    material_id=inv.material_id,
                    material_nombre=material.nombre,
                    cantidad_actual=float(inv.cantidad),
                    umbral=float(umbral),
                    unidad_medida=um_abrev,
                    ubicacion_nombre=ubicacion.nombre if ubicacion else "Depósito"
                )
            )
            
    return resultados


# ------------------------------------------------------------
# Informe Mensual
# ------------------------------------------------------------

def _mes_a_rango(mes: str):
    year, month = map(int, mes.split("-"))
    _, last_day = calendar.monthrange(year, month)
    return (
        datetime(year, month, 1, 0, 0, 0),
        datetime(year, month, last_day, 23, 59, 59),
        date(year, month, 1),
        date(year, month, last_day),
    )


def _venta_en_cop(db: Session, venta: Venta) -> Decimal:
    """Total de la venta convertido a COP con la tasa registrada al facturar."""
    if venta.moneda_id == 1:
        return Decimal(str(venta.total))
    if venta.tasa_cambio and Decimal(str(venta.tasa_cambio)) != Decimal("1.0"):
        tasa = Decimal(str(venta.tasa_cambio))
    else:
        tasa = obtener_tasa_moneda_a_cop(db, venta.moneda_id, venta.fecha)
    return Decimal(str(venta.total)) * tasa


def _trm_referencia(db: Session, moneda_id: Optional[int], fecha, tasa_guardada=None) -> Optional[Decimal]:
    """TRM confiable moneda → COP para la columna de referencia del informe.

    - COP: 1.0 (nativo).
    - Con tasa congelada distinta de 1.0 (la TRM fijada al cotizar): esa.
    - Si la guardada es 1.0 (o no hay): TRM registrada en el catálogo a la fecha.
    - Sin ninguna: None. Mostrar el equivalente asumiendo 1 USD = 1 COP
      fabricaba cifras en COP falsas (y descuadraba los totales).
    """
    if moneda_id in (None, 1):
        return Decimal("1.0")
    if tasa_guardada is not None:
        try:
            tasa = Decimal(str(tasa_guardada))
        except Exception:
            tasa = Decimal("0.0")
        if tasa > 0 and tasa != Decimal("1.0"):
            return tasa
    return _tasa_registrada_a_cop(db, moneda_id, fecha)


def _nombre_detalle(det) -> Optional[str]:
    """Nombre legible de una línea (pedido/venta/cotización) sin nunca
    interpolar 'None'.

    Orden de precedencia:
      1. Producto del catálogo (FABRICADO/REVENTA con referencia).
      2. Material del catálogo (INSUMO).
      3. Descripción personalizada guardada: los muebles a medida y las
         notas históricas (importadas desde cotizaciones del Cotizador IA
         o notas de entrega) NO tienen producto/material y viven en
         `descripcion_especifica` (detalle_pedido/detalle_venta) o en
         `observaciones` (detalle_cotizacion).
      4. Ids numéricos como último recurso, SOLO si no son nulos.
    """
    if getattr(det, "producto", None) and det.producto.nombre:
        return det.producto.nombre
    if getattr(det, "material", None) and getattr(det.material, "nombre", None):
        return det.material.nombre
    desc = getattr(det, "descripcion_especifica", None) or getattr(det, "observaciones", None)
    if desc and str(desc).strip():
        return str(desc).strip()
    if getattr(det, "producto_id", None):
        return f"Producto #{det.producto_id}"
    if getattr(det, "material_id", None):
        return f"Material #{det.material_id}"
    return None


def _texto_productos(origen) -> str:
    """Concatena las líneas de un origen (detalles de venta, pedido o
    cotización) como 'Nombre xcantidad'. Nunca emite 'None'."""
    partes = []
    for det in origen:
        nombre = _nombre_detalle(det) or "Ítem a medida"
        partes.append(f"{nombre} x{det.cantidad}")
    return ", ".join(partes) if partes else "—"


def _primer_texto_productos(*fuentes) -> str:
    """Primera fuente (venta → pedido → cotización) con nombres reales.

    Una fuente compuesta solo por líneas anónimas ('Ítem a medida') no sirve:
    se sigue buscando en la siguiente. Las notas históricas pueden no tener
    detalle_pedido: el nombre original vive en la cotización, que es la fuente
    literal a mostrar.
    """
    primero = "—"
    for fuente in fuentes:
        if not fuente:
            continue
        partes = []
        reales = 0
        for det in fuente:
            nombre = _nombre_detalle(det)
            if nombre:
                reales += 1
            else:
                nombre = "Ítem a medida"
            partes.append(f"{nombre} x{det.cantidad}")
        texto = ", ".join(partes)
        if primero == "—":
            primero = texto
        if reales:
            return texto
    return primero


def _saldo_caja_en_cop(db: Session, metodo_id: int, hasta: date) -> Decimal:
    """Saldo de un método de caja sumando movimientos hasta la fecha (en COP)."""
    movs = (
        db.query(model.MovimientoCaja)
        .filter(model.MovimientoCaja.metodo_caja_id == metodo_id, model.MovimientoCaja.fecha <= hasta)
        .all()
    )
    saldo = Decimal("0.0")
    for m in movs:
        base = Decimal(str(m.monto_en_moneda_base)) if m.monto_en_moneda_base is not None else (
            Decimal(str(m.monto)) * Decimal(str(m.tasa_cambio or 1.0))
        )
        if m.tipo == "SALIDA":
            saldo -= base
        else:
            saldo += base  # APERTURA | ENTRADA | AJUSTE (AJUSTE puede ser negativo en monto)
    return saldo


def obtener_informe_mensual(db: Session, mes: str) -> schemas.InformeMensualResponse:
    start_dt, end_dt, start_date, end_date = _mes_a_rango(mes)
    # Catálogo de monedas (id → código), una sola query para todo el informe
    monedas_catalogo = {m.id: m.codigo for m in db.query(Moneda).all()}

    # ============================================================
    # 1. CONTROL INTERNO DE INGRESOS
    # ============================================================
    ventas_mes = (
        db.query(Venta)
        .filter(Venta.fecha >= start_date, Venta.fecha <= end_date)
        .all()
    )
    venta_ids = [v.id for v in ventas_mes]

    detalles = []
    if venta_ids:
        detalles = (
            db.query(DetalleVenta)
            .filter(DetalleVenta.venta_id.in_(venta_ids))
            .all()
        )

    detalle_por_venta: Dict[int, List[DetalleVenta]] = {}
    for dv in detalles:
        detalle_por_venta.setdefault(dv.venta_id, []).append(dv)

    # Cargar TODOS los pagos del mes en una sola query (evita N+1)
    pagos_mes = (
        db.query(Pago).filter(Pago.venta_id.in_(venta_ids)).all()
    ) if venta_ids else []
    pagos_por_venta: Dict[int, List[Pago]] = {}
    for p in pagos_mes:
        pagos_por_venta.setdefault(p.venta_id, []).append(p)

    lineas = []
    devoluciones_mes = (
        db.query(model.DevolucionVenta)
        .filter(model.DevolucionVenta.fecha >= start_date, model.DevolucionVenta.fecha <= end_date)
        .all()
    )

    for venta in ventas_mes:
        tasa_venta = _trm_referencia(db, venta.moneda_id, venta.fecha, venta.tasa_cambio)
        detalles_venta = detalle_por_venta.get(venta.id, [])
        if not detalles_venta:
            # Venta sin renglones (facturación directa / histórica): sin línea
            # su total era invisible en la tabla aunque sus pagos sí contaban
            # en el resumen → el informe no cuadraba consigo mismo.
            precio_linea = Decimal(str(venta.total))
            lineas.append(
                schemas.LineaIngresoInforme(
                    fecha=venta.fecha,
                    cliente=venta.cliente.nombre if venta.cliente else "—",
                    cantidad=Decimal("1"),
                    producto="(Venta sin detalle de producto)",
                    costo_unitario=Decimal("0.0"),
                    precio_costo=Decimal("0.0"),
                    porcentaje_ganancia=None,
                    utilidad=Decimal("0.0"),
                    precio_venta=precio_linea,
                    descuento=Decimal("0.0"),
                    moneda=venta.moneda.codigo if venta.moneda else "COP",
                    tasa_cambio=tasa_venta,
                    precio_venta_en_base=precio_linea * tasa_venta if tasa_venta is not None else None,
                    es_devolucion=False,
                )
            )
        for dv in detalles_venta:
            costo_unit = Decimal(str(dv.costo_unitario or 0.0))
            pct = Decimal(str(dv.porcentaje_ganancia or 0.0)) if dv.porcentaje_ganancia is not None else None
            precio = Decimal(str(dv.precio))
            cantidad = Decimal(str(dv.cantidad))
            utilidad = Decimal(str(dv.utilidad or (precio - costo_unit))) * cantidad
            descuento = Decimal(str(dv.descuento or 0.0)) * cantidad
            precio_linea = precio * cantidad
            lineas.append(
                schemas.LineaIngresoInforme(
                    fecha=venta.fecha,
                    cliente=venta.cliente.nombre if venta.cliente else "—",
                    cantidad=cantidad,
                    producto=dv.producto.nombre if dv.producto else (_nombre_detalle(dv) or "—"),
                    costo_unitario=costo_unit,
                    precio_costo=costo_unit * cantidad,
                    porcentaje_ganancia=pct,
                    utilidad=utilidad,
                    precio_venta=precio_linea,
                    descuento=descuento,
                    moneda=venta.moneda.codigo if venta.moneda else "COP",
                    tasa_cambio=tasa_venta,
                    precio_venta_en_base=precio_linea * tasa_venta if tasa_venta is not None else None,
                    es_devolucion=False,
                )
            )

    # Devoluciones del mes como líneas negativas
    for dev in devoluciones_mes:
        venta = dev.venta
        dev_moneda_id = dev.moneda.id if dev.moneda else 1
        tasa_dev = _trm_referencia(db, dev_moneda_id, dev.fecha, dev.tasa_cambio)
        base_dev = (
            Decimal(str(dev.monto_en_moneda_base or (dev.monto_devuelto * tasa_dev)))
            if tasa_dev is not None
            else None
        )
        lineas.append(
            schemas.LineaIngresoInforme(
                fecha=dev.fecha,
                cliente=venta.cliente.nombre if venta and venta.cliente else "—",
                cantidad=-dev.cantidad,
                producto=f"DEVOLUCIÓN ({dev.motivo or 'sin motivo'})",
                costo_unitario=Decimal("0.0"),
                precio_costo=Decimal("0.0"),
                porcentaje_ganancia=None,
                utilidad=Decimal("0.0"),
                precio_venta=-dev.monto_devuelto,
                descuento=Decimal("0.0"),
                moneda=dev.moneda.codigo if dev.moneda else "COP",
                tasa_cambio=tasa_dev,
                precio_venta_en_base=-base_dev if base_dev is not None else None,
                es_devolucion=True,
            )
        )

    totales = schemas.TotalesIngresoInforme(
        precio_costo=sum(l.precio_costo for l in lineas),
        utilidad=sum(l.utilidad for l in lineas),
        precio_venta=sum(l.precio_venta for l in lineas),
        precio_venta_en_base=sum(l.precio_venta_en_base or Decimal("0.0") for l in lineas),
        descuentos=sum(l.descuento for l in lineas),
    )

    # TOTALES separados por moneda: una cifra que suma USD con COP no significa
    # nada contable (era exactamente el descuadre del informe).
    def _total_moneda(cod: str) -> schemas.TotalesPorMonedaInforme:
        ls = [l for l in lineas if l.moneda == cod]
        return schemas.TotalesPorMonedaInforme(
            moneda=cod,
            precio_costo=sum(l.precio_costo for l in ls),
            utilidad=sum(l.utilidad for l in ls),
            precio_venta=sum(l.precio_venta for l in ls),
            precio_venta_en_base=sum(l.precio_venta_en_base or Decimal("0.0") for l in ls) if cod == "COP" else None,
            descuentos=sum(l.descuento for l in ls),
        )

    orden_monedas = sorted({l.moneda for l in lineas}, key=lambda c: (c != "COP", c))
    totales_por_moneda = [_total_moneda(cod) for cod in orden_monedas]

    # ============================================================
    # 2. RESUMEN DEL MES
    # ============================================================
    ingresos = Decimal("0.0")
    for venta in ventas_mes:
        for p in pagos_por_venta.get(venta.id, []):
            if not (start_dt <= p.fecha <= end_dt):
                continue
            monto_base_venta = Decimal(str(p.monto_en_moneda_base or p.monto))
            ingresos += monto_base_venta * (
                Decimal(str(venta.tasa_cambio or 1.0)) if venta.moneda_id != 1 else Decimal("1.0")
            )

    gastos_generales = (
        db.query(func.coalesce(func.sum(Gasto.monto_en_moneda_base), 0))
        .filter(Gasto.fecha >= start_date, Gasto.fecha <= end_date)
        .scalar()
    )
    compras_recibidas = (
        db.query(func.coalesce(func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario), 0))
        .join(Compra, DetalleCompra.compra_id == Compra.id)
        .filter(Compra.fecha >= start_date, Compra.fecha <= end_date, Compra.estado == "RECIBIDA")
        .scalar()
    )
    egresos = Decimal(str(gastos_generales or 0.0)) + Decimal(str(compras_recibidas or 0.0))

    # Mano de obra pagada en el mes → costo COP
    mano_obra_list = (
        db.query(ManoObra, Venta.moneda_id)
        .select_from(ManoObra)
        .join(EtapaProduccion, ManoObra.etapa_produccion_id == EtapaProduccion.id)
        .join(OrdenProduccion, EtapaProduccion.orden_produccion_id == OrdenProduccion.id)
        .join(DetallePedido, OrdenProduccion.detalle_pedido_id == DetallePedido.id)
        .join(Pedido, DetallePedido.pedido_id == Pedido.id)
        .outerjoin(Venta, Venta.pedido_id == Pedido.id)
        .filter(ManoObra.updated_at >= start_dt, ManoObra.updated_at <= end_dt, ManoObra.pagado == True)
        .all()
    )
    for mo, moneda_id in mano_obra_list:
        recargo = Decimal(str(mo.porcentaje_recargo or 0.0)) / Decimal("100.0")
        monto = Decimal(str(mo.monto)) * (Decimal("1.0") + recargo)
        if moneda_id and moneda_id != 1:
            monto *= obtener_tasa_moneda_a_cop(db, moneda_id, mo.updated_at.date())
        egresos += monto

    resumen = schemas.ResumenMes(
        ingresos=ingresos,
        egresos=egresos,
        disponible=ingresos - egresos,
    )

    # ============================================================
    # 3. ESTADO DE RESULTADOS
    # ============================================================
    # Ventas contado / crédito (legacy en COP con TRM + desglose nativo por moneda)
    contado = Decimal("0.0")
    credito = Decimal("0.0")
    ventas_por_moneda: Dict[str, Dict[str, Decimal]] = {}
    for venta in ventas_mes:
        pagos = pagos_por_venta.get(venta.id, [])
        total_pagado = sum(Decimal(str(p.monto_en_moneda_base or p.monto)) for p in pagos)
        total_venta = Decimal(str(venta.total))
        es_contado = len(pagos) == 1 and total_pagado >= total_venta
        if es_contado:
            contado += _venta_en_cop(db, venta)
        else:
            credito += _venta_en_cop(db, venta)
        cod_v = venta.moneda.codigo if venta.moneda else "COP"
        agg_v = ventas_por_moneda.setdefault(
            cod_v, {"contado": Decimal("0.0"), "credito": Decimal("0.0"), "devoluciones": Decimal("0.0"), "descuentos": Decimal("0.0")}
        )
        agg_v["contado" if es_contado else "credito"] += total_venta
        agg_v["descuentos"] += sum(
            Decimal(str(dv.descuento or 0.0)) * Decimal(str(dv.cantidad))
            for dv in detalle_por_venta.get(venta.id, [])
        )

    devoluciones_total = sum(
        Decimal(str(d.monto_en_moneda_base or (d.monto_devuelto * d.tasa_cambio)))
        for d in devoluciones_mes
    )
    for d in devoluciones_mes:
        cod_d = d.moneda.codigo if d.moneda else "COP"
        ventas_por_moneda.setdefault(
            cod_d, {"contado": Decimal("0.0"), "credito": Decimal("0.0"), "devoluciones": Decimal("0.0"), "descuentos": Decimal("0.0")}
        )["devoluciones"] += Decimal(str(d.monto_devuelto))
    descuentos_total_cop = Decimal("0.0")
    for venta in ventas_mes:
        tasa_v = _venta_en_cop(db, venta) / Decimal(str(venta.total)) if venta.total else Decimal("0.0")
        descuentos_total_cop += sum(
            Decimal(str(dv.descuento or 0.0)) * Decimal(str(dv.cantidad)) for dv in detalle_por_venta.get(venta.id, [])
        ) * tasa_v

    ventas_estado = schemas.VentasEstadoResultados(
        contado=contado,
        credito=credito,
        extraordinarias=Decimal("0.0"),
        devoluciones=devoluciones_total,
        descuentos=descuentos_total_cop,
        total_ventas_netas=contado + credito - devoluciones_total - descuentos_total_cop,
    )

    # Inventarios iniciales / finales desde catálogo flexible
    conceptos = (
        db.query(model.ConceptoReporte)
        .filter(model.ConceptoReporte.activo == True, model.ConceptoReporte.seccion == "INVENTARIO")
        .order_by(model.ConceptoReporte.orden)
        .all()
    )
    valores = {
        v.concepto_id: v
        for v in db.query(model.ValorConceptoMensual).filter(model.ValorConceptoMensual.mes == mes).all()
    }

    inventarios_iniciales = []
    inventarios_finales = []
    total_inicial = Decimal("0.0")
    total_final = Decimal("0.0")
    # Corte de inventario desglosado por la moneda en que se registró cada valor
    inventarios_por_moneda: Dict[str, Dict[str, Decimal | List[schemas.LineaValorConcepto]]] = {}
    for c in conceptos:
        val = valores.get(c.id)
        v_inicial = Decimal(str(val.valor_inicial)) if val else Decimal("0.0")
        v_final = Decimal(str(val.valor_final)) if val else Decimal("0.0")
        moneda_val = monedas_catalogo.get(val.moneda_id, "COP") if val else "COP"
        inventarios_iniciales.append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_inicial, moneda=moneda_val))
        inventarios_finales.append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_final, moneda=moneda_val))
        total_inicial += v_inicial
        total_final += v_final
        inv_m = inventarios_por_moneda.setdefault(
            moneda_val, {"total_inicial": Decimal("0.0"), "total_final": Decimal("0.0"), "iniciales": [], "finales": []}
        )
        inv_m["iniciales"].append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_inicial, moneda=moneda_val))
        inv_m["finales"].append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_final, moneda=moneda_val))
        inv_m["total_inicial"] += v_inicial
        inv_m["total_final"] += v_final

    # Saldos de caja a fin de mes, EN LA MONEDA PROPIA de cada cuenta. NO
    # forman parte del inventario (sumarlos fabricaba utilidad ficticia) y NO
    # se consolidan en COP: los movimientos históricos guardan equivalentes
    # con tasas mezcladas (algunos fabricados 1:1), así que el saldo nativo es
    # la única cifra fiable.
    metodos_caja = db.query(model.MetodoCaja).filter(model.MetodoCaja.activo == True).order_by(model.MetodoCaja.orden).all()
    saldos_caja: List[schemas.LineaSaldoCajaInforme] = []
    for mc in metodos_caja:
        movs_mc = (
            db.query(model.MovimientoCaja)
            .filter(model.MovimientoCaja.metodo_caja_id == mc.id, model.MovimientoCaja.fecha <= end_date)
            .all()
        )
        por_moneda_mc: Dict[str, Decimal] = {}
        for m in movs_mc:
            cod_mc = monedas_catalogo.get(m.moneda_id, "COP")
            signo = Decimal("-1") if m.tipo == "SALIDA" else Decimal("1")
            por_moneda_mc[cod_mc] = por_moneda_mc.get(cod_mc, Decimal("0.0")) + signo * Decimal(str(m.monto))
        for cod_mc, saldo_mc in sorted(por_moneda_mc.items(), key=lambda kv: (kv[0] != "COP", kv[0])):
            saldos_caja.append(
                schemas.LineaSaldoCajaInforme(metodo_caja_id=mc.id, nombre=mc.nombre, moneda=cod_mc, saldo=saldo_mc)
            )

    # Compras del mes (recibidas)
    compras_mes = (
        db.query(Compra)
        .filter(Compra.fecha >= start_date, Compra.fecha <= end_date, Compra.estado == "RECIBIDA")
        .all()
    )
    compras_contado = Decimal("0.0")
    compras_credito = Decimal("0.0")
    for c in compras_mes:
        tasa_c = Decimal(str(c.tasa_cambio or 1.0)) if c.moneda_id != 1 else Decimal("1.0")
        if c.moneda_id != 1 and tasa_c == Decimal("1.0"):
            tasa_c = obtener_tasa_moneda_a_cop(db, c.moneda_id, c.fecha)
        total_c = Decimal(str(c.total)) * tasa_c
        if c.tipo_pago == "CONTADO":
            compras_contado += total_c
        else:
            compras_credito += total_c

    total_compras = compras_contado + compras_credito
    total_mercancia = total_inicial + total_compras
    compras_estado = schemas.ComprasEstadoResultados(
        contado=compras_contado,
        credito=compras_credito,
        total_compras_brutas=total_compras,
        total_mercancia=total_mercancia,
    )

    compras_netas = total_mercancia - total_final
    utilidad_bruta = ventas_estado.total_ventas_netas - compras_netas

    # Gastos por categoría
    gastos_mes = (
        db.query(Gasto)
        .join(TipoGasto, Gasto.tipo_gasto_id == TipoGasto.id)
        .filter(Gasto.fecha >= start_date, Gasto.fecha <= end_date)
        .all()
    )
    gastos_por_tipo: Dict[int, Dict] = {}
    for g in gastos_mes:
        info = gastos_por_tipo.setdefault(g.tipo_gasto_id, {"nombre": g.tipo_gasto.nombre, "categoria": g.tipo_gasto.categoria, "monto": Decimal("0.0")})
        info["monto"] += Decimal(str(g.monto_en_moneda_base or (g.monto * g.tasa_cambio)))

    def _lineas_categoria(cat: str):
        return [
            schemas.LineaGastoInforme(tipo_id=tid, nombre=info["nombre"], monto=info["monto"])
            for tid, info in gastos_por_tipo.items() if info["categoria"] == cat
        ]

    operativos = _lineas_categoria("OPERATIVO")
    administrativos = _lineas_categoria("ADMINISTRATIVO")
    financieros = _lineas_categoria("FINANCIERO")
    impuestos = _lineas_categoria("IMPUESTO")
    # El consumo de materia prima en producción (PRODUCCION) es un costo real:
    # antes quedaba fuera del estado de resultados y solo aparecía en el resumen.
    produccion = _lineas_categoria("PRODUCCION")

    gastos_estado = schemas.GastosEstadoResultados(
        operativos=operativos,
        administrativos=administrativos,
        financieros=financieros,
        impuestos=impuestos,
        produccion=produccion,
        total_gastos_operativos=sum(l.monto for l in operativos),
        total_gastos_administrativos=sum(l.monto for l in administrativos),
        total_financieros=sum(l.monto for l in financieros),
        total_impuestos=sum(l.monto for l in impuestos),
        total_gastos_produccion=sum(l.monto for l in produccion),
        total_gastos=sum(l.monto for l in operativos + administrativos + financieros + impuestos + produccion),
    )

    estado = schemas.EstadoResultados(
        ventas=ventas_estado,
        inventarios_iniciales=inventarios_iniciales,
        total_inventarios_iniciales=total_inicial,
        compras=compras_estado,
        inventarios_finales=inventarios_finales,
        total_inventarios_finales=total_final,
        compras_netas=compras_netas,
        utilidad_bruta=utilidad_bruta,
        gastos=gastos_estado,
        utilidad_periodo=utilidad_bruta - gastos_estado.total_gastos,
    )

    # ============================================================
    # 4. PENDIENTES DE PAGO AL CIERRE (pedidos/ventas sin cobrar)
    #    Cualquier pedido con fecha <= fin del mes cuyo cliente
    #    todavía debe dinero (venta abonada o sin facturar).
    # ============================================================
    pedidos_cierre = (
        db.query(Pedido)
        .filter(Pedido.fecha <= end_date)
        .order_by(Pedido.fecha, Pedido.id)
        .all()
    )
    pedidos_pendientes = []
    total_pendiente = Decimal("0.0")

    # Cargar ventas y pagos de TODOS los pedidos en 2 queries (evita N+1)
    pedido_ids_cierre = [p.id for p in pedidos_cierre]
    ventas_de_pedidos = (
        db.query(Venta).filter(Venta.pedido_id.in_(pedido_ids_cierre)).all()
    ) if pedido_ids_cierre else []
    venta_por_pedido = {v.pedido_id: v for v in ventas_de_pedidos}
    pagos_de_ventas = (
        db.query(Pago).filter(Pago.venta_id.in_([v.id for v in ventas_de_pedidos])).all()
    ) if ventas_de_pedidos else []
    pagos_por_venta_cierre: Dict[int, List[Pago]] = {}
    for p in pagos_de_ventas:
        pagos_por_venta_cierre.setdefault(p.venta_id, []).append(p)
    # Descuentos de cobro: restan del saldo igual que los pagos (sin mover caja).
    from app.modules.sales.model import DescuentoVenta
    descuentos_de_ventas = (
        db.query(DescuentoVenta).filter(DescuentoVenta.venta_id.in_([v.id for v in ventas_de_pedidos])).all()
    ) if ventas_de_pedidos else []
    descuentos_por_venta_cierre: Dict[int, List[DescuentoVenta]] = {}
    for d in descuentos_de_ventas:
        descuentos_por_venta_cierre.setdefault(d.venta_id, []).append(d)

    for pedido in pedidos_cierre:
        venta = venta_por_pedido.get(pedido.id)
        productos: str = "—"

        if venta:
            if venta.estado not in ("PENDIENTE", "ABONADA"):
                continue
            total_base = _venta_en_cop(db, venta)
            pagado_base = sum(
                Decimal(str(p.monto_en_moneda_base or p.monto))
                for p in pagos_por_venta_cierre.get(venta.id, [])
            )
            descontado_base = sum(
                Decimal(str(d.monto_en_moneda_base or d.monto))
                for d in descuentos_por_venta_cierre.get(venta.id, [])
            )
            saldo = total_base - pagado_base - descontado_base
            if saldo <= Decimal("1.0"):  # ignora residuos de centavos por redondeo
                continue
            productos = _primer_texto_productos(
                detalle_por_venta.get(venta.id, []),
                pedido.detalles,
                pedido.cotizacion.detalles if pedido.cotizacion else [],
            )
            # Cifras nativas en la moneda de la venta (monto_en_moneda_base de
            # los pagos y descuentos ya vive en esa moneda): la referencia fiable.
            total_nat = Decimal(str(venta.total))
            saldo_nat = total_nat - pagado_base - descontado_base
            pedidos_pendientes.append(
                schemas.PendientePagoLinea(
                    pedido_id=pedido.id,
                    venta_id=venta.id,
                    fecha=venta.fecha,
                    cliente=pedido.cliente.nombre if pedido.cliente else "—",
                    producto=productos,
                    estado_pedido=pedido.estado,
                    estado_venta=venta.estado,
                    moneda=venta.moneda.codigo if venta.moneda else "COP",
                    total_en_base=total_base,
                    pagado_en_base=pagado_base,
                    saldo_en_base=saldo,
                    total_en_moneda=total_nat,
                    pagado_en_moneda=pagado_base,
                    saldo_en_moneda=saldo_nat,
                )
            )
            continue

        # Pedido sin factura: solo estados facturables
        if pedido.estado not in ("APROBADO", "PRODUCCION", "TERMINADO", "ENTREGADO"):
            continue

        total_pedido = sum(
            Decimal(str(det.precio)) * Decimal(str(det.cantidad))
            for det in pedido.detalles
        )
        if total_pedido <= 0:
            continue

        moneda_pedido = "COP"
        tasa = Decimal("1.0")
        cotizacion = pedido.cotizacion
        if cotizacion and cotizacion.moneda_id and cotizacion.moneda_id != 1:
            moneda_pedido = cotizacion.moneda.codigo if cotizacion.moneda else "COP"
            tasa = Decimal(str(cotizacion.tasa_cambio)) if cotizacion.tasa_cambio else Decimal("0.0")
            if tasa <= Decimal("1.0"):
                tasa = obtener_tasa_moneda_a_cop(db, cotizacion.moneda_id, pedido.fecha)
        total_base = total_pedido * tasa

        pedidos_pendientes.append(
            schemas.PendientePagoLinea(
                pedido_id=pedido.id,
                venta_id=None,
                fecha=pedido.fecha,
                cliente=pedido.cliente.nombre if pedido.cliente else "—",
                producto=_primer_texto_productos(
                    pedido.detalles,
                    pedido.cotizacion.detalles if pedido.cotizacion else [],
                ),
                estado_pedido=pedido.estado,
                estado_venta=None,
                moneda=moneda_pedido,
                total_en_base=total_base,
                pagado_en_base=Decimal("0.0"),
                saldo_en_base=total_base,
                total_en_moneda=total_pedido,
                pagado_en_moneda=Decimal("0.0"),
                saldo_en_moneda=total_pedido,
            )
        )

    total_pendiente = sum(l.saldo_en_base for l in pedidos_pendientes)
    pendientes_por_moneda: Dict[str, Decimal] = {}
    for l in pedidos_pendientes:
        cod_l = l.moneda
        pendientes_por_moneda[cod_l] = pendientes_por_moneda.get(cod_l, Decimal("0.0")) + (
            l.saldo_en_moneda if l.saldo_en_moneda is not None else l.saldo_en_base
        )
    total_pendiente_por_moneda = [
        schemas.SaldoPorMoneda(moneda=cod, saldo=pendientes_por_moneda[cod])
        for cod in sorted(pendientes_por_moneda, key=lambda c: (c != "COP", c))
    ]

    # ============================================================
    # 5. DESGLOSE POR MONEDA (cifras nativas, sin conversiones)
    #    Resumen y estado de resultados en la moneda de cada operación:
    #    sumar USD con COP fabricaba balances que no correspondían a ninguna
    #    de las dos monedas.
    # ============================================================
    ingresos_m: Dict[str, Decimal] = {}
    egresos_m: Dict[str, Decimal] = {}
    # Ingresos: TODO el dinero cobrado en el mes (pagos), en su moneda física.
    # Las devoluciones del mes son dinero que sale: restan.
    pagos_cobrados_mes = (
        db.query(Pago).filter(Pago.fecha >= start_dt, Pago.fecha <= end_dt).all()
    )
    for p in pagos_cobrados_mes:
        cod_p = monedas_catalogo.get(p.moneda_id, "COP")
        ingresos_m[cod_p] = ingresos_m.get(cod_p, Decimal("0.0")) + Decimal(str(p.monto))
    for d in devoluciones_mes:
        cod_d = monedas_catalogo.get(d.moneda_id, "COP")
        ingresos_m[cod_d] = ingresos_m.get(cod_d, Decimal("0.0")) - Decimal(str(d.monto_devuelto))

    for g in gastos_mes:
        cod_g = monedas_catalogo.get(g.moneda_id, "COP")
        egresos_m[cod_g] = egresos_m.get(cod_g, Decimal("0.0")) + Decimal(str(g.monto))
    for c in compras_mes:
        cod_c = monedas_catalogo.get(c.moneda_id, "COP")
        egresos_m[cod_c] = egresos_m.get(cod_c, Decimal("0.0")) + Decimal(str(c.total))
    # Mano de obra: se paga SIEMPRE en pesos (COP nativo).
    mano_obra_cop = Decimal("0.0")
    for mo, _moneda_id_mo in mano_obra_list:
        recargo_mo = Decimal(str(mo.porcentaje_recargo or 0.0)) / Decimal("100.0")
        mano_obra_cop += Decimal(str(mo.monto)) * (Decimal("1.0") + recargo_mo)
    egresos_m["COP"] = egresos_m.get("COP", Decimal("0.0")) + mano_obra_cop

    resumen_por_moneda: List[schemas.ResumenMoneda] = []
    for cod_rm in sorted(set(ingresos_m) | set(egresos_m), key=lambda c: (c != "COP", c)):
        ing_rm = ingresos_m.get(cod_rm, Decimal("0.0"))
        egr_rm = egresos_m.get(cod_rm, Decimal("0.0"))
        resumen_por_moneda.append(
            schemas.ResumenMoneda(moneda=cod_rm, ingresos=ing_rm, egresos=egr_rm, disponible=ing_rm - egr_rm)
        )
    resumen.por_moneda = resumen_por_moneda

    # ── Estado de resultados por moneda ──
    compras_por_moneda: Dict[str, Dict[str, Decimal]] = {}
    for c in compras_mes:
        cod_c = monedas_catalogo.get(c.moneda_id, "COP")
        agg_c = compras_por_moneda.setdefault(cod_c, {"contado": Decimal("0.0"), "credito": Decimal("0.0")})
        total_c = Decimal(str(c.total))
        if c.tipo_pago == "CONTADO":
            agg_c["contado"] += total_c
        else:
            agg_c["credito"] += total_c

    gastos_por_moneda: Dict[str, Dict[int, Dict]] = {}
    for g in gastos_mes:
        cod_g = monedas_catalogo.get(g.moneda_id, "COP")
        info_g = gastos_por_moneda.setdefault(cod_g, {}).setdefault(
            g.tipo_gasto_id, {"nombre": g.tipo_gasto.nombre, "categoria": g.tipo_gasto.categoria, "monto": Decimal("0.0")}
        )
        info_g["monto"] += Decimal(str(g.monto))

    def _gastos_de_moneda(cod: str) -> schemas.GastosEstadoResultados:
        gmap = gastos_por_moneda.get(cod, {})

        def _cat(cat: str) -> List[schemas.LineaGastoInforme]:
            return [
                schemas.LineaGastoInforme(tipo_id=tid, nombre=info["nombre"], monto=info["monto"])
                for tid, info in gmap.items() if info["categoria"] == cat
            ]

        op_m, adm_m, fin_m, imp_m, prod_m = (
            _cat("OPERATIVO"), _cat("ADMINISTRATIVO"), _cat("FINANCIERO"),
            _cat("IMPUESTO"), _cat("PRODUCCION"),
        )
        return schemas.GastosEstadoResultados(
            operativos=op_m,
            administrativos=adm_m,
            financieros=fin_m,
            impuestos=imp_m,
            produccion=prod_m,
            total_gastos_operativos=sum(l.monto for l in op_m),
            total_gastos_administrativos=sum(l.monto for l in adm_m),
            total_financieros=sum(l.monto for l in fin_m),
            total_impuestos=sum(l.monto for l in imp_m),
            total_gastos_produccion=sum(l.monto for l in prod_m),
            total_gastos=sum(l.monto for l in op_m + adm_m + fin_m + imp_m + prod_m),
        )

    CEROS_VENTAS = {"contado": Decimal("0.0"), "credito": Decimal("0.0"), "devoluciones": Decimal("0.0"), "descuentos": Decimal("0.0")}
    estado_por_moneda: List[schemas.EstadoPorMoneda] = []
    cods_estado = sorted(
        set(ventas_por_moneda) | set(compras_por_moneda) | set(inventarios_por_moneda) | set(gastos_por_moneda),
        key=lambda c: (c != "COP", c),
    )
    for cod_e in cods_estado:
        agg_ve = CEROS_VENTAS | ventas_por_moneda.get(cod_e, {})
        agg_co = compras_por_moneda.get(cod_e, {"contado": Decimal("0.0"), "credito": Decimal("0.0")})
        inv_me = inventarios_por_moneda.get(cod_e, {})
        total_inicial_m = inv_me.get("total_inicial", Decimal("0.0"))
        total_final_m = inv_me.get("total_final", Decimal("0.0"))
        compras_tot_m = agg_co["contado"] + agg_co["credito"]
        mercancia_m = total_inicial_m + compras_tot_m
        compras_netas_m = mercancia_m - total_final_m
        ventas_netas_m = agg_ve["contado"] + agg_ve["credito"] - agg_ve["devoluciones"] - agg_ve["descuentos"]
        utilidad_bruta_m = ventas_netas_m - compras_netas_m
        gastos_m = _gastos_de_moneda(cod_e)
        estado_por_moneda.append(
            schemas.EstadoPorMoneda(
                moneda=cod_e,
                ventas=schemas.VentasEstadoResultados(
                    contado=agg_ve["contado"],
                    credito=agg_ve["credito"],
                    extraordinarias=Decimal("0.0"),
                    devoluciones=agg_ve["devoluciones"],
                    descuentos=agg_ve["descuentos"],
                    total_ventas_netas=ventas_netas_m,
                ),
                inventarios_iniciales=list(inv_me.get("iniciales", [])),
                total_inventarios_iniciales=total_inicial_m,
                compras=schemas.ComprasEstadoResultados(
                    contado=agg_co["contado"],
                    credito=agg_co["credito"],
                    total_compras_brutas=compras_tot_m,
                    total_mercancia=mercancia_m,
                ),
                inventarios_finales=list(inv_me.get("finales", [])),
                total_inventarios_finales=total_final_m,
                compras_netas=compras_netas_m,
                utilidad_bruta=utilidad_bruta_m,
                gastos=gastos_m,
                utilidad_periodo=utilidad_bruta_m - gastos_m.total_gastos,
            )
        )

    return schemas.InformeMensualResponse(
        mes=mes,
        control_interno_ingresos=schemas.ControlInternoIngresos(
            lineas=lineas,
            totales=totales,
            totales_por_moneda=totales_por_moneda,
        ),
        resumen=resumen,
        estado_resultados=estado,
        pendientes_de_pago=schemas.PendientesDePagoInforme(
            lineas=pedidos_pendientes,
            total_pendiente=total_pendiente,
            total_pendiente_por_moneda=total_pendiente_por_moneda,
        ),
        saldos_caja=saldos_caja,
        estado_resultados_por_moneda=estado_por_moneda,
    )


# ------------------------------------------------------------
# CRUD: Conceptos de reporte
# ------------------------------------------------------------
def listar_conceptos(db: Session, seccion: Optional[str] = None) -> List[model.ConceptoReporte]:
    query = db.query(model.ConceptoReporte).order_by(model.ConceptoReporte.orden, model.ConceptoReporte.id)
    if seccion:
        query = query.filter(model.ConceptoReporte.seccion == seccion)
    return query.all()

def crear_concepto(db: Session, esquema: schemas.ConceptoReporteCreate) -> model.ConceptoReporte:
    obj = model.ConceptoReporte(**esquema.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def actualizar_concepto(db: Session, concepto_id: int, esquema: schemas.ConceptoReporteUpdate) -> Optional[model.ConceptoReporte]:
    obj = db.query(model.ConceptoReporte).filter(model.ConceptoReporte.id == concepto_id).first()
    if not obj:
        return None
    for campo, valor in esquema.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    db.commit()
    db.refresh(obj)
    return obj

def eliminar_concepto(db: Session, concepto_id: int) -> bool:
    obj = db.query(model.ConceptoReporte).filter(model.ConceptoReporte.id == concepto_id).first()
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ------------------------------------------------------------
# CRUD: Valores mensuales de conceptos (corte de inventario)
# ------------------------------------------------------------
def obtener_valores_mensuales(db: Session, mes: str) -> List[model.ValorConceptoMensual]:
    return db.query(model.ValorConceptoMensual).filter(model.ValorConceptoMensual.mes == mes).all()

def guardar_valores_mensuales(db: Session, mes: str, valores: List[schemas.ValorConceptoMensualCreate]) -> List[model.ValorConceptoMensual]:
    """Upsert: crea o actualiza el valor de cada concepto para el mes."""
    guardados = []
    for v in valores:
        existente = (
            db.query(model.ValorConceptoMensual)
            .filter(model.ValorConceptoMensual.mes == mes, model.ValorConceptoMensual.concepto_id == v.concepto_id)
            .first()
        )
        if existente:
            existente.valor_inicial = v.valor_inicial
            existente.valor_final = v.valor_final
            existente.moneda_id = v.moneda_id
            existente.observaciones = v.observaciones
            guardados.append(existente)
        else:
            obj = model.ValorConceptoMensual(mes=mes, **v.model_dump(exclude={"mes"}))
            db.add(obj)
            guardados.append(obj)
    db.commit()
    for g in guardados:
        db.refresh(g)
    return guardados


# ------------------------------------------------------------
# CRUD: Métodos de caja
# ------------------------------------------------------------
def listar_metodos_caja(db: Session) -> List[model.MetodoCaja]:
    return db.query(model.MetodoCaja).order_by(model.MetodoCaja.orden, model.MetodoCaja.id).all()

def crear_metodo_caja(db: Session, esquema: schemas.MetodoCajaCreate) -> model.MetodoCaja:
    CODIGO_MONEDA = {"EFECTIVO_USD": 2, "ZELLE": 2, "BINANCE": 2, "EFECTIVO_VES": 3, "BANCARIBE": 3}
    moneda_id = esquema.moneda_id or CODIGO_MONEDA.get(esquema.codigo, 1)
    obj = model.MetodoCaja(**esquema.model_dump(), moneda_id=moneda_id)
    db.add(obj)
    db.flush()
    from app.core.caja import registrar_movimiento_caja
    registrar_movimiento_caja(
        db,
        metodo_caja_id=obj.id,
        tipo="APERTURA",
        monto=1_000_000.0 if moneda_id == 1 else 0.0,
        moneda_id=moneda_id,
        tasa_cambio=1.0,
        fecha=date.today(),
        referencia="Saldo inicial por defecto",
        observaciones=f"Apertura por defecto: {1_000_000 if moneda_id == 1 else 0} {'COP' if moneda_id == 1 else 'USD'}",
    )
    db.commit()
    db.refresh(obj)
    return obj

def actualizar_metodo_caja(db: Session, metodo_id: int, esquema: schemas.MetodoCajaUpdate) -> Optional[model.MetodoCaja]:
    obj = db.query(model.MetodoCaja).filter(model.MetodoCaja.id == metodo_id).first()
    if not obj:
        return None
    for campo, valor in esquema.model_dump(exclude_unset=True).items():
        setattr(obj, campo, valor)
    db.commit()
    db.refresh(obj)
    return obj

def eliminar_metodo_caja(db: Session, metodo_id: int) -> bool:
    obj = db.query(model.MetodoCaja).filter(model.MetodoCaja.id == metodo_id).first()
    if not obj:
        return False
    en_uso = db.query(model.MovimientoCaja).filter(
        model.MovimientoCaja.metodo_caja_id == metodo_id
    ).first()
    if en_uso:
        raise ValueError(
            "El método de caja tiene movimientos asociados; "
            "desactívalo (activo=false) en lugar de eliminarlo."
        )
    db.delete(obj)
    db.commit()
    return True


# ------------------------------------------------------------
# CRUD: Movimientos de caja
# ------------------------------------------------------------
def listar_movimientos_caja(db: Session, metodo_id: Optional[int] = None, fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None) -> List[model.MovimientoCaja]:
    query = db.query(model.MovimientoCaja)
    if metodo_id:
        query = query.filter(model.MovimientoCaja.metodo_caja_id == metodo_id)
    if fecha_desde:
        query = query.filter(model.MovimientoCaja.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.MovimientoCaja.fecha <= fecha_hasta)
    return query.order_by(model.MovimientoCaja.fecha.desc(), model.MovimientoCaja.id.desc()).all()

def crear_movimiento_caja(db: Session, esquema: schemas.MovimientoCajaCreate, usuario_id: Optional[int] = None) -> model.MovimientoCaja:
    datos = esquema.model_dump()
    monto = Decimal(str(datos["monto"]))
    tasa = Decimal(str(datos.get("tasa_cambio") or 1.0))
    datos["monto_en_moneda_base"] = round(monto * tasa, 2)
    datos["usuario_id"] = usuario_id
    obj = model.MovimientoCaja(**datos)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def actualizar_movimiento_caja(db: Session, movimiento_id: int, esquema: schemas.MovimientoCajaUpdate) -> Optional[model.MovimientoCaja]:
    obj = db.query(model.MovimientoCaja).filter(model.MovimientoCaja.id == movimiento_id).first()
    if not obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(obj, campo, valor)
    if "monto" in datos or "tasa_cambio" in datos:
        obj.monto_en_moneda_base = round(Decimal(str(obj.monto)) * Decimal(str(obj.tasa_cambio or 1.0)), 2)
    db.commit()
    db.refresh(obj)
    return obj

def eliminar_movimiento_caja(db: Session, movimiento_id: int) -> bool:
    obj = db.query(model.MovimientoCaja).filter(model.MovimientoCaja.id == movimiento_id).first()
    if not obj:
        return False
    # Una transferencia es UNA operación con dos patas: borrar una borra ambas
    # (dejar una sola pata fabricaría dinero o lo haría desaparecer del libro).
    if obj.transferencia_id:
        db.query(model.MovimientoCaja).filter(
            model.MovimientoCaja.transferencia_id == obj.transferencia_id
        ).delete(synchronize_session=False)
    else:
        db.delete(obj)
    db.commit()
    return True


# ------------------------------------------------------------
# Transferencias entre cuentas de caja
# ------------------------------------------------------------
class SaldoInsuficienteError(ValueError):
    """La cuenta origen no tiene saldo suficiente para la transferencia."""


def _saldo_cuenta_a_fecha(db: Session, metodo_caja_id: int, moneda_id: int, hasta: date) -> Decimal:
    """Saldo disponible de una cuenta EN UNA MONEDA hasta la fecha (inclusive):
    APERTURA/ENTRADA suman, SALIDA resta, AJUSTE suma/resta según el signo."""
    movs = (
        db.query(model.MovimientoCaja)
        .filter(
            model.MovimientoCaja.metodo_caja_id == metodo_caja_id,
            model.MovimientoCaja.moneda_id == moneda_id,
            model.MovimientoCaja.fecha <= hasta,
        )
        .all()
    )
    saldo = Decimal("0.0")
    for m in movs:
        signo = Decimal("-1") if m.tipo == "SALIDA" else Decimal("1")
        saldo += signo * Decimal(str(m.monto))
    return saldo


def _tasa_registrada_a_cop(db: Session, moneda_id: int, fecha: date) -> Optional[Decimal]:
    """Última tasa moneda → COP registrada a la fecha (o la más próxima si no
    hay exacta). None si no existe ninguna: a diferencia del cobro de ventas,
    aquí NO se asume 1.0 (1 USD = 1 COP fabricaría o destruiría dinero)."""
    tasa = db.query(TasaCambio).filter(
        TasaCambio.moneda_origen_id == moneda_id,
        TasaCambio.moneda_destino_id == 1,
        TasaCambio.fecha <= fecha,
    ).order_by(TasaCambio.fecha.desc()).first()
    if not tasa:
        tasa = db.query(TasaCambio).filter(
            TasaCambio.moneda_origen_id == moneda_id,
            TasaCambio.moneda_destino_id == 1,
        ).order_by(TasaCambio.fecha.asc()).first()
    return Decimal(str(tasa.valor)) if tasa and Decimal(str(tasa.valor)) > 0 else None


def _tasa_transferencia_salida(db: Session, moneda_salida_id: int, tasa_indicada: Optional[Decimal], fecha: date) -> Decimal:
    """Resuelve y valida la tasa de la pata de salida (moneda → COP).

    - Moneda COP: tasa 1.0 fija.
    - Sin tasa indicada: usa la TRM registrada (obligatoria: si no hay, error).
    - Con tasa indicada: rechazada si se desvía más de 50% de la registrada
      (anti TRM inventada, mismo criterio que los pagos de venta).
    """
    if moneda_salida_id in (None, 1):
        return Decimal("1.0")
    registrada = _tasa_registrada_a_cop(db, moneda_salida_id, fecha)
    if tasa_indicada is None:
        if registrada is None:
            raise ValueError(
                f"No hay tasa de cambio registrada para la moneda {moneda_salida_id}. "
                "Indica la tasa (moneda → COP) al transferir."
            )
        return registrada
    tasa = Decimal(str(tasa_indicada))
    if tasa <= 0:
        raise ValueError("La tasa de cambio debe ser mayor que cero.")
    if registrada and abs(tasa - registrada) / registrada > Decimal("0.5"):
        raise ValueError(
            f"La tasa indicada ({tasa}) difiere más de 50% de la tasa registrada "
            f"({registrada}). Usa la TRM real del día."
        )
    return tasa


def _mov_caja_response(m: model.MovimientoCaja) -> schemas.MovimientoCajaResponse:
    return schemas.MovimientoCajaResponse(
        metodo_caja_id=m.metodo_caja_id,
        fecha=m.fecha,
        tipo=m.tipo,
        monto=m.monto,
        moneda_id=m.moneda_id,
        tasa_cambio=m.tasa_cambio,
        referencia=m.referencia,
        observaciones=m.observaciones,
        id=m.id,
        usuario_id=m.usuario_id,
        monto_en_moneda_base=m.monto_en_moneda_base,
        transferencia_id=m.transferencia_id,
        created_at=m.created_at,
        metodo_caja=schemas.MetodoCajaResponse(
            id=m.metodo_caja.id, nombre=m.metodo_caja.nombre, codigo=m.metodo_caja.codigo,
            activo=m.metodo_caja.activo, orden=m.metodo_caja.orden, moneda_id=m.metodo_caja.moneda_id,
            moneda_codigo=m.metodo_caja.moneda_codigo, moneda_simbolo=m.metodo_caja.moneda_simbolo,
        ) if m.metodo_caja else None,
        moneda=schemas.MonedaResponse(
            id=m.moneda.id, codigo=m.moneda.codigo, nombre=m.moneda.nombre, simbolo=m.moneda.simbolo,
        ) if m.moneda else None,
        usuario=schemas.ResponsableResponse(
            id=m.usuario.id, nombre_usuario=m.usuario.nombre_usuario,
            nombre=m.usuario.display_name, email=m.usuario.email,
        ) if m.usuario else None,
    )


def _transferencia_response(db: Session, salida: model.MovimientoCaja) -> schemas.TransferenciaResponse:
    destino_id = salida.transferencia_id
    entrada = (
        db.query(model.MovimientoCaja)
        .filter(model.MovimientoCaja.transferencia_id == destino_id, model.MovimientoCaja.id != salida.id)
        .first()
    )
    if entrada is None:
        raise ValueError("La transferencia está incompleta (falta la pata de entrada).")
    return schemas.TransferenciaResponse(
        transferencia_id=destino_id,
        fecha=salida.fecha,
        monto_salida=salida.monto,
        monto_entrada=entrada.monto,
        moneda_salida_codigo=salida.moneda.codigo if salida.moneda else "?",
        moneda_entrada_codigo=entrada.moneda.codigo if entrada.moneda else "?",
        tasa_cambio=salida.tasa_cambio,
        saldo_disponible_origen=_saldo_cuenta_a_fecha(
            db, salida.metodo_caja_id, salida.moneda_id, salida.fecha
        ),
        referencia=salida.referencia,
        observaciones=salida.observaciones,
        pata_salida=_mov_caja_response(salida),
        pata_entrada=_mov_caja_response(entrada),
    )


def crear_transferencia(
    db: Session,
    esquema: schemas.TransferenciaCreate,
    usuario_id: Optional[int] = None,
) -> schemas.TransferenciaResponse:
    """Mueve dinero entre dos cuentas de caja como UNA operación contable de
    dos patas: SALIDA en origen + ENTRADA en destino, emparejadas por
    `transferencia_id`. El saldo total del negocio no cambia.

    - Valida cuentas distintas, activas y saldo disponible en origen.
    - Multimoneda (p. ej. EFECTIVO_USD → BANCOLOMBIA): la pata de destino
      lleva el monto convertido con la TRM de su moneda (del catálogo).
    """
    fecha = esquema.fecha or date.today()
    monto = Decimal(str(esquema.monto))

    origen = db.query(model.MetodoCaja).filter(model.MetodoCaja.id == esquema.cuenta_origen_id).first()
    destino = db.query(model.MetodoCaja).filter(model.MetodoCaja.id == esquema.cuenta_destino_id).first()
    if not origen:
        raise ValueError("La cuenta de origen no existe.")
    if not destino:
        raise ValueError("La cuenta de destino no existe.")
    if origen.id == destino.id:
        raise ValueError("La cuenta de origen y la de destino deben ser distintas.")
    if not origen.activo or not destino.activo:
        raise ValueError("Ambas cuentas deben estar activas.")

    moneda_salida = esquema.moneda_id or origen.moneda_id or 1
    moneda_entrada = destino.moneda_id or moneda_salida

    # Tasa de la pata de salida (moneda que sale → COP) y monto en base.
    tasa_salida = _tasa_transferencia_salida(db, moneda_salida, esquema.tasa_cambio, fecha)
    base_salida = round(monto * tasa_salida, 2)

    # Pata de entrada: misma moneda (1:1) o convertida con la TRM de destino.
    if moneda_entrada == moneda_salida:
        tasa_entrada = tasa_salida
        monto_entrada = monto
    else:
        if moneda_entrada == 1:
            tasa_entrada = Decimal("1.0")
        else:
            tasa_entrada = _tasa_registrada_a_cop(db, moneda_entrada, fecha)
            if tasa_entrada is None:
                raise ValueError(
                    f"La cuenta destino opera en la moneda {moneda_entrada} y no hay "
                    "tasa de cambio registrada para ella. Regístrala primero."
                )
        monto_entrada = (base_salida / tasa_entrada).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
        if monto_entrada <= 0:
            raise ValueError("El monto convertido a la moneda de destino queda en 0. Revisa la tasa.")

    # Saldo disponible en origen (en la moneda que sale) hasta la fecha.
    saldo_disponible = _saldo_cuenta_a_fecha(db, origen.id, moneda_salida, fecha)
    if monto > saldo_disponible + Decimal("0.005"):
        raise SaldoInsuficienteError(
            f"Saldo insuficiente en '{origen.nombre}': disponible {saldo_disponible:,.2f}, "
            f"solicitado {monto:,.2f}."
        )

    # Pata 1: SALIDA en origen. Su id hace de transferencia_id de la operación.
    salida = model.MovimientoCaja(
        metodo_caja_id=origen.id,
        usuario_id=usuario_id,
        fecha=fecha,
        tipo="SALIDA",
        monto=monto,
        moneda_id=moneda_salida,
        tasa_cambio=tasa_salida,
        monto_en_moneda_base=base_salida,
        referencia=(esquema.referencia or f"Transferencia a {destino.nombre}")[:150],
        observaciones=esquema.observaciones,
    )
    db.add(salida)
    db.flush()

    salida.transferencia_id = salida.id
    salida.referencia = f"Transferencia #T{salida.id} a {destino.nombre}"[:150]

    # Pata 2: ENTRADA en destino (misma transacción).
    entrada = model.MovimientoCaja(
        metodo_caja_id=destino.id,
        usuario_id=usuario_id,
        transferencia_id=salida.id,
        fecha=fecha,
        tipo="ENTRADA",
        monto=monto_entrada,
        moneda_id=moneda_entrada,
        tasa_cambio=tasa_entrada,
        monto_en_moneda_base=round(monto_entrada * tasa_entrada, 2),
        referencia=f"Transferencia #T{salida.id} de {origen.nombre}"[:150],
        observaciones=esquema.observaciones,
    )
    db.add(entrada)
    db.flush()

    record_event(
        db,
        actor=db.query(Usuario).filter(Usuario.id == usuario_id).first() if usuario_id else None,
        action="CREATE",
        entity_type="transferencia_caja",
        entity_id=salida.id,
        after={
            "cuenta_origen_id": origen.id,
            "cuenta_destino_id": destino.id,
            "monto": float(monto),
            "moneda_salida_id": moneda_salida,
            "monto_entrada": float(monto_entrada),
            "moneda_entrada_id": moneda_entrada,
        },
    )
    db.commit()
    db.refresh(salida)
    db.refresh(entrada)
    return _transferencia_response(db, salida)


def listar_transferencias(
    db: Session,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> List[schemas.TransferenciaResponse]:
    """Transferencias (patas emparejadas) en un rango de fechas, más recientes primero."""
    query = (
        db.query(model.MovimientoCaja)
        .options(
            sa_orm.joinedload(model.MovimientoCaja.metodo_caja),
            sa_orm.joinedload(model.MovimientoCaja.moneda),
            sa_orm.joinedload(model.MovimientoCaja.usuario),
        )
        .filter(model.MovimientoCaja.transferencia_id.isnot(None))
    )
    if fecha_desde:
        query = query.filter(model.MovimientoCaja.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.MovimientoCaja.fecha <= fecha_hasta)
    patas = query.order_by(model.MovimientoCaja.fecha.desc(), model.MovimientoCaja.id.desc()).all()

    respuestas: List[schemas.TransferenciaResponse] = []
    vistos: set = set()
    for pata in patas:
        tid = pata.transferencia_id
        if tid in vistos:
            continue
        vistos.add(tid)
        salida = pata if pata.tipo == "SALIDA" else next(
            (p for p in patas if p.transferencia_id == tid and p.tipo == "SALIDA"), None
        )
        if salida is None:
            continue
        respuestas.append(_transferencia_response(db, salida))
    return respuestas


def _concepto_movimiento(db: Session, m: "model.MovimientoCaja"):
    """Devuelve (concepto legible, responsable) de un movimiento de caja.

    Interpreta la `referencia` estándar ("Gasto #N", "Pago #N", "Nómina #N",
    "Compra #N") para enriquecerlo con el nombre real; queda NULL quien no
    aplica o si el registro original ya no existe.
    """
    quien = m.usuario.display_name if m.usuario else None
    ref = (m.referencia or "").strip()
    if ref.startswith("Gasto #"):
        try:
            g = db.query(Gasto).filter(Gasto.id == int(ref.split("#")[1].split(" ")[0])).first()
        except ValueError:
            g = None
        if g:
            nombre_tipo = g.tipo_gasto.nombre if g.tipo_gasto else "Gasto"
            desc = g.descripcion or ""
            concepto = f"Gasto: {nombre_tipo}" + (f" — {desc}" if desc else "")
            return concepto, (g.creador.display_name if g.creador else quien)
        return "Gasto", quien
    if ref.startswith("Pago #"):
        try:
            pago_id = int(ref.split("#")[1].split(" ")[0])
            f = db.query(Pago).filter(Pago.id == pago_id).first()
        except ValueError:
            f = None
        if f and f.venta:
            cliente = f.venta.cliente.nombre if f.venta.cliente else "?"
            concepto = f"Pago venta #{f.venta_id} — {cliente}"
        else:
            concepto = "Pago"
        return concepto, quien
    if ref.startswith("Nómina #"):
        return "Nómina semanal", quien
    if ref.startswith("Compra #"):
        return "Compra", quien
    if ref.startswith("Transferencia #"):
        return "Transferencia entre cuentas", quien
    if ref.startswith("CxP #"):
        # "CxP #102 abono #65" → concepto corto (la referencia va aparte y
        # la UI la muestra como chip; antes se duplicaba el texto).
        try:
            partes = ref.split("#")
            cxp_id = int(partes[1].split(" ")[0])
            abono_id = int(partes[2].split(" ")[0]) if len(partes) > 2 else None
        except (IndexError, ValueError):
            return "Abono deuda", quien
        pago = (
            db.query(PagoCuentaPorPagar)
            .options(
                sa_orm.joinedload(PagoCuentaPorPagar.creador),
                sa_orm.joinedload(PagoCuentaPorPagar.cuenta_por_pagar).joinedload(
                    CuentaPorPagar.proveedor
                ),
            )
            .filter(PagoCuentaPorPagar.id == abono_id)
            .first()
            if abono_id is not None
            else None
        )
        cxp = pago.cuenta_por_pagar if pago and pago.cuenta_por_pagar else None
        if cxp is None:
            cxp = (
                db.query(CuentaPorPagar)
                .options(sa_orm.joinedload(CuentaPorPagar.proveedor))
                .filter(CuentaPorPagar.id == cxp_id)
                .first()
            )
        proveedor = cxp.proveedor.nombre if cxp and cxp.proveedor else None
        concepto = f"Abono deuda #{cxp_id}" + (f" — {proveedor}" if proveedor else "")
        quien_pago = (
            pago.creador.display_name
            if pago and pago.creador
            else quien
        )
        return concepto, quien_pago
    return ref or "Movimiento", quien


def resumen_diario(
    db: Session, dia: date, moneda_vista: str = "COP"
) -> schemas.ResumenDiarioResponse:
    """Estado del día: saldo inicial, ingresos, egresos y quién los hizo.

    Se construye desde `movimiento_caja` (la bitácora única de caja). La
    convención es la misma que _saldo_caja_en_cop: SALIDA resta; el resto
    suma (AJUSTE lleva su signo en el monto).

    `moneda_vista` (p. ej. "USD") NO convierte nada: filtra la vista a esa
    moneda y totaliza en su valor nativo. Cada moneda se muestra según su
    moneda, sin tasa de cambio. `por_moneda` trae el resumen multimoneda y
    `monedas` las vistas disponibles (tabs); los totales `*_cop` quedan como
    referencia compatible.
    """
    codigo_vista = (moneda_vista or "COP").upper()
    mon_vista = (
        db.query(Moneda).filter(func.upper(Moneda.codigo) == codigo_vista).first()
    )
    if mon_vista is None:
        raise ValueError(f"Moneda desconocida: {moneda_vista}")
    vista_id = mon_vista.id

    def es_vista(moneda_id) -> bool:
        return (moneda_id or 1) == vista_id
    movs = (
        db.query(model.MovimientoCaja)
        .options(
            sa_orm.joinedload(model.MovimientoCaja.metodo_caja),
            sa_orm.joinedload(model.MovimientoCaja.moneda),
            sa_orm.joinedload(model.MovimientoCaja.usuario),
        )
        .filter(model.MovimientoCaja.fecha <= dia)
        .order_by(model.MovimientoCaja.fecha, model.MovimientoCaja.id)
        .all()
    )

    def cop(m) -> Decimal:
        if m.monto_en_moneda_base is not None:
            return Decimal(str(m.monto_en_moneda_base))
        return Decimal(str(m.monto)) * Decimal(str(m.tasa_cambio or 1.0))

    def signo(m) -> Decimal:
        return Decimal("-1") if m.tipo == "SALIDA" else Decimal("1")

    # Saldo por cuenta Y moneda, en la moneda nativa de cada movimiento.
    # Antes se sumaba todo convertido a COP por cuenta, mezclando USD con
    # COP en la misma cifra. El COP queda solo como referencia.
    nativo: Dict[tuple, dict] = {}

    def _linea_nativa(m) -> dict:
        key = (m.metodo_caja_id, m.moneda_id)
        lin = nativo.get(key)
        if lin is None:
            lin = nativo[key] = {
                "metodo_caja_id": m.metodo_caja_id,
                "cuenta_nombre": (
                    m.metodo_caja.nombre if m.metodo_caja else f"Cuenta #{m.metodo_caja_id}"
                ),
                "moneda_id": m.moneda_id,
                "codigo": m.moneda.codigo if m.moneda else "?",
                "simbolo": m.moneda.simbolo if m.moneda else "?",
                "inicial": Decimal("0"),
                "final": Decimal("0"),
                "inicial_cop": Decimal("0"),
                "final_cop": Decimal("0"),
            }
        return lin

    # Saldo inicial (antes del día). AJUSTE lleva su signo en el monto.
    inicial_por_cuenta: Dict[int, Decimal] = {}
    inicial_vista = Decimal("0")
    for m in movs:
        if m.fecha < dia:
            delta_cop = signo(m) * cop(m)
            inicial_por_cuenta[m.metodo_caja_id] = (
                inicial_por_cuenta.get(m.metodo_caja_id, Decimal("0")) + delta_cop
            )
            lin = _linea_nativa(m)
            delta_nat = signo(m) * Decimal(str(m.monto))
            lin["inicial"] += delta_nat
            lin["final"] += delta_nat
            lin["inicial_cop"] += delta_cop
            lin["final_cop"] += delta_cop
            if es_vista(m.moneda_id):
                inicial_vista += delta_nat
    # Las cuentas con movimiento solo el día actual también aparecen.
    for m in movs:
        if m.fecha == dia:
            _linea_nativa(m)

    # Movimientos del día + totales COP + desglose por moneda.
    # Los totales *_vista y las líneas/saldos solo cubren la moneda vista.
    movimientos: List[schemas.MovimientoDiarioResponse] = []
    total_ingresos_cop = Decimal("0.0")
    total_egresos_cop = Decimal("0.0")
    ingresos_vista = Decimal("0")
    egresos_vista = Decimal("0")
    por_moneda: Dict[int, dict] = {}
    final_por_cuenta: Dict[int, Decimal] = dict(inicial_por_cuenta)

    for m in movs:
        if m.fecha != dia:
            continue
        montocop = cop(m)
        val_cuenta = final_por_cuenta.get(m.metodo_caja_id, Decimal("0"))
        final_por_cuenta[m.metodo_caja_id] = val_cuenta + signo(m) * montocop
        lin = _linea_nativa(m)
        lin["final"] += signo(m) * Decimal(str(m.monto))
        lin["final_cop"] += signo(m) * montocop
        # Las patas de una transferencia NO son ingreso ni egreso del negocio:
        # solo redistribuyen saldo entre cuentas. Se listan, pero no suman a
        # los totales del día (igual que los "Gasto #", que vienen de la tabla).
        es_transferencia = m.transferencia_id is not None
        if m.tipo == "SALIDA":
            # Los egresos con cuenta se listan desde la TABLA GASTO (más abajo)
            # para no duplicarlos: su movimiento de caja sale por referencia.
            es_salida_de_gasto = bool((m.referencia or "").startswith("Gasto #"))
            if not es_salida_de_gasto:
                if not es_transferencia:
                    total_egresos_cop += montocop
                    if es_vista(m.moneda_id):
                        egresos_vista += Decimal(str(m.monto))
                    meta = por_moneda.setdefault(
                        m.moneda_id,
                        {"moneda_id": m.moneda_id,
                         "codigo": m.moneda.codigo if m.moneda else "?",
                         "simbolo": m.moneda.simbolo if m.moneda else "?",
                         "monto_ingresos": Decimal("0.0"), "monto_egresos": Decimal("0.0"),
                         "monto_cop": Decimal("0.0")},
                    )
                    meta["monto_egresos"] += Decimal(str(m.monto))
                    meta["monto_cop"] += montocop
                concepto, quien = _concepto_movimiento(db, m)
                movimientos.append(
                    schemas.MovimientoDiarioResponse(
                        id=m.id,
                        tipo=m.tipo,
                        moneda_codigo=m.moneda.codigo if m.moneda else "?",
                        moneda_simbolo=m.moneda.simbolo if m.moneda else "?",
                        monto=m.monto,
                        monto_cop=montocop,
                        cuenta_nombre=m.metodo_caja.nombre if m.metodo_caja else None,
                        referencia=m.referencia,
                        concepto=concepto,
                        quien=quien,
                    )
                )
        else:
            if not es_transferencia:
                total_ingresos_cop += montocop
                if es_vista(m.moneda_id):
                    ingresos_vista += Decimal(str(m.monto))
                meta = por_moneda.setdefault(
                    m.moneda_id,
                    {"moneda_id": m.moneda_id,
                     "codigo": m.moneda.codigo if m.moneda else "?",
                     "simbolo": m.moneda.simbolo if m.moneda else "?",
                     "monto_ingresos": Decimal("0.0"), "monto_egresos": Decimal("0.0"),
                     "monto_cop": Decimal("0.0")},
                )
                meta["monto_ingresos"] += Decimal(str(m.monto))
                meta["monto_cop"] += montocop

            concepto, quien = _concepto_movimiento(db, m)
            movimientos.append(
                schemas.MovimientoDiarioResponse(
                    id=m.id,
                    tipo=m.tipo,
                    moneda_codigo=m.moneda.codigo if m.moneda else "?",
                    moneda_simbolo=m.moneda.simbolo if m.moneda else "?",
                    monto=m.monto,
                    monto_cop=montocop,
                    cuenta_nombre=m.metodo_caja.nombre if m.metodo_caja else None,
                    referencia=m.referencia,
                    concepto=concepto,
                    quien=quien,
                )
            )

    # ── Egresos del día desde la TABLA GASTO ─────────────────────────────
    # Incluye los gastos SIN cuenta de caja (p.ej. consumo de materia prima en
    # producción), que nunca generaban movimiento y quedaban invisibles.
    gastos_dia = (
        db.query(Gasto)
        .options(
            sa_orm.joinedload(Gasto.tipo_gasto),
            sa_orm.joinedload(Gasto.moneda),
            sa_orm.joinedload(Gasto.area),
            sa_orm.joinedload(Gasto.creador),
        )
        .filter(Gasto.fecha == dia)
        .order_by(Gasto.id)
        .all()
    )
    if gastos_dia:
        # Gastos que nacieron de una deuda (fiado): nunca tocaron caja, por
        # eso su cuenta queda vacía. Se marcan para no confundirlos.
        ids_fiado = {
            r[0]
            for r in db.query(CuentaPorPagar.gasto_id).filter(
                CuentaPorPagar.gasto_id.in_([g.id for g in gastos_dia])
            ).all()
            if r[0] is not None
        }
        refs = {f"Gasto #{g.id}": g for g in gastos_dia}
        movs_gasto = (
            db.query(model.MovimientoCaja)
            .options(sa_orm.joinedload(model.MovimientoCaja.metodo_caja))
            .filter(model.MovimientoCaja.referencia.in_(refs.keys()))
            .all()
        )
        cuenta_por_ref = {
            mv.referencia: (mv.metodo_caja.nombre if mv.metodo_caja else None)
            for mv in movs_gasto
        }
        for g in gastos_dia:
            montocop = (
                Decimal(str(g.monto_en_moneda_base))
                if g.monto_en_moneda_base is not None
                else Decimal(str(g.monto)) * Decimal(str(g.tasa_cambio or 1.0))
            )
            total_egresos_cop += montocop
            if es_vista(g.moneda_id):
                egresos_vista += Decimal(str(g.monto))
            meta = por_moneda.setdefault(
                g.moneda_id,
                {"moneda_id": g.moneda_id,
                 "codigo": g.moneda.codigo if g.moneda else "?",
                 "simbolo": g.moneda.simbolo if g.moneda else "?",
                 "monto_ingresos": Decimal("0.0"), "monto_egresos": Decimal("0.0"),
                 "monto_cop": Decimal("0.0")},
            )
            meta["monto_egresos"] += Decimal(str(g.monto))
            meta["monto_cop"] += montocop

            concepto = g.tipo_gasto.nombre if g.tipo_gasto else "Egreso"
            if g.id in ids_fiado:
                concepto += " (fiado)"
            if g.area and g.area.nombre:
                concepto += f" · {g.area.nombre}"
            desc = (g.descripcion or "").strip()
            if desc:
                if concepto.upper().startswith("NÓMINA"):
                    partes = desc.split("—")
                    if len(partes) > 1:
                        nombre_empleado = partes[-1].strip()
                        concepto += f" — {nombre_empleado}"
                else:
                    concepto += f" — {desc}"
            movimientos.append(
                schemas.MovimientoDiarioResponse(
                    id=g.id,
                    tipo="EGRESO",
                    moneda_codigo=g.moneda.codigo if g.moneda else "?",
                    moneda_simbolo=g.moneda.simbolo if g.moneda else "?",
                    monto=g.monto,
                    monto_cop=montocop,
                    cuenta_nombre=cuenta_por_ref.get(f"Gasto #{g.id}"),
                    referencia=f"Gasto #{g.id}",
                    concepto=concepto,
                    quien=(g.creador.display_name if g.creador else "Sistema"),
                )
            )

    saldo_inicial_cop = sum(inicial_por_cuenta.values(), Decimal("0"))
    saldo_final_cop = sum(final_por_cuenta.values(), Decimal("0"))

    # La vista solo muestra su moneda: líneas y saldos de otras monedas
    # quedan fuera (el resumen multimoneda vive en `por_moneda`).
    movimientos = [mv for mv in movimientos if mv.moneda_codigo == codigo_vista]
    saldo_final_vista = sum(
        (lin["final"] for lin in nativo.values() if es_vista(lin["moneda_id"])),
        Decimal("0"),
    )

    # Una fila por (cuenta, moneda) de la vista, en valor nativo + COP ref.
    saldos_por_cuenta = [
        schemas.SaldoCuentaDiaria(
            metodo_caja_id=lin["metodo_caja_id"],
            cuenta_nombre=lin["cuenta_nombre"],
            moneda_codigo=lin["codigo"],
            moneda_simbolo=lin["simbolo"],
            saldo_inicial=lin["inicial"],
            saldo_final=lin["final"],
            saldo_inicial_cop=lin["inicial_cop"],
            saldo_final_cop=lin["final_cop"],
        )
        for lin in sorted(nativo.values(), key=lambda l: (l["cuenta_nombre"], l["codigo"]))
        if es_vista(lin["moneda_id"])
    ]

    por_moneda_resp = [
        schemas.LineaMonedaDiaria(
            moneda_id=data["moneda_id"],
            codigo=data["codigo"],
            simbolo=data["simbolo"],
            monto_ingresos=data["monto_ingresos"],
            monto_egresos=data["monto_egresos"],
            monto_cop=data["monto_cop"],
        )
        for data in por_moneda.values()
    ]

    # Monedas con movimiento en el día (tabs de la UI). COP siempre va.
    vistas: Dict[int, dict] = {1: {"codigo": "COP", "simbolo": "$"}}
    for data in por_moneda.values():
        if data["moneda_id"] and data["codigo"] != "?":
            vistas.setdefault(
                data["moneda_id"],
                {"codigo": data["codigo"], "simbolo": data["simbolo"]},
            )
    for lin in nativo.values():
        if lin["moneda_id"] and lin["codigo"] != "?":
            vistas.setdefault(
                lin["moneda_id"],
                {"codigo": lin["codigo"], "simbolo": lin["simbolo"]},
            )
    monedas = [
        schemas.MonedaVistaDiaria(
            moneda_id=mid_v,
            codigo=info["codigo"],
            simbolo=info["simbolo"],
        )
        for mid_v, info in vistas.items()
    ]
    monedas.sort(key=lambda m: (m.codigo != "COP", m.codigo))

    return schemas.ResumenDiarioResponse(
        fecha=dia,
        saldo_inicial_cop=saldo_inicial_cop,
        total_ingresos_cop=total_ingresos_cop,
        total_egresos_cop=total_egresos_cop,
        saldo_final_cop=saldo_final_cop,
        moneda_vista=codigo_vista,
        moneda_vista_simbolo=mon_vista.simbolo if mon_vista.simbolo else "?",
        saldo_inicial_vista=inicial_vista,
        total_ingresos_vista=ingresos_vista,
        total_egresos_vista=egresos_vista,
        saldo_final_vista=saldo_final_vista,
        monedas=monedas,
        movimientos=movimientos,
        por_moneda=por_moneda_resp,
        saldos_por_cuenta=saldos_por_cuenta,
    )


def resumen_cuentas(db: Session) -> List[dict]:
    """
    Saldo por cada cuenta activa: desglosado por moneda (en su propia moneda
    y en COP) y total en COP. Usa la misma convención que _saldo_caja_en_cop:
    SALIDA resta; APERTURA/ENTRADA/AJUSTE suman (AJUSTE puede ser negativo).
    """
    from sqlalchemy import orm as sa_orm

    metodos = (
        db.query(model.MetodoCaja)
        .options(sa_orm.joinedload(model.MetodoCaja.moneda))
        .order_by(model.MetodoCaja.orden, model.MetodoCaja.id)
        .all()
    )
    movs = (
        db.query(model.MovimientoCaja)
        .options(sa_orm.joinedload(model.MovimientoCaja.moneda))
        .order_by(model.MovimientoCaja.metodo_caja_id, model.MovimientoCaja.id)
        .all()
    )
    monedas: dict = {}  # moneda_id -> {codigo, simbolo}
    for m in movs:
        if m.moneda and m.moneda_id not in monedas:
            monedas[m.moneda_id] = {"codigo": m.moneda.codigo, "simbolo": m.moneda.simbolo}

    resumen: List[schemas.ResumenCuentaResponse] = []
    for mc in metodos:
        mc_resp = schemas.MetodoCajaResponse(
            id=mc.id, nombre=mc.nombre, codigo=mc.codigo, activo=mc.activo,
            orden=mc.orden, moneda_id=mc.moneda_id,
            moneda_codigo=mc.moneda.codigo if mc.moneda else None,
            moneda_simbolo=mc.moneda.simbolo if mc.moneda else None,
        )
        lineas: List[schemas.LineaSaldoMoneda] = []
        for m in movs:
            if m.metodo_caja_id != mc.id:
                continue
            signo = Decimal("-1") if m.tipo == "SALIDA" else Decimal("1")
            linea = next((l for l in lineas if l.moneda_id == m.moneda_id), None)
            if linea is None:
                meta = monedas.get(m.moneda_id, {"codigo": "?", "simbolo": "?"})
                linea = schemas.LineaSaldoMoneda(
                    moneda_id=m.moneda_id, codigo=meta["codigo"], simbolo=meta["simbolo"],
                    monto=Decimal("0.0"),
                )
                lineas.append(linea)
            linea.monto += signo * Decimal(str(m.monto))
        resumen.append(schemas.ResumenCuentaResponse(metodo_caja=mc_resp, saldo_por_moneda=lineas))
    return resumen


# ------------------------------------------------------------
# CRUD: Devoluciones de venta
# ------------------------------------------------------------
def listar_devoluciones(db: Session, fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None) -> List[model.DevolucionVenta]:
    query = db.query(model.DevolucionVenta)
    if fecha_desde:
        query = query.filter(model.DevolucionVenta.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.DevolucionVenta.fecha <= fecha_hasta)
    return query.order_by(model.DevolucionVenta.fecha.desc()).all()

def crear_devolucion(db: Session, esquema: schemas.DevolucionVentaCreate) -> model.DevolucionVenta:
    # 1. La devolución debe corresponder a una venta existente y no superar lo cobrado.
    from app.modules.sales.model import Venta, Pago
    venta = db.query(Venta).filter(Venta.id == esquema.venta_id).first()
    if not venta:
        raise ValueError("La venta especificada no existe.")
    total_pagado = sum(
        float(p.monto_en_moneda_base) for p in db.query(Pago).filter(Pago.venta_id == venta.id).all()
    )
    # Resta lo YA devuelto en devoluciones previas: sin esto se podía reembolsar
    # N veces la misma venta (cada devolución generaba una SALIDA de caja).
    total_ya_devuelto = sum(
        float(d.monto_en_moneda_base or 0)
        for d in db.query(model.DevolucionVenta).filter(model.DevolucionVenta.venta_id == venta.id).all()
    )
    monto_devuelto_base = round(
        Decimal(str(esquema.monto_devuelto)) * Decimal(str(esquema.tasa_cambio or 1.0)), 2
    )
    if monto_devuelto_base + Decimal(str(round(total_ya_devuelto, 2))) > Decimal(str(total_pagado)) + Decimal("0.01"):
        raise ValueError(
            f"El monto devuelto ({monto_devuelto_base:,.2f} COP, ya se han devuelto "
            f"{total_ya_devuelto:,.2f}) excede lo cobrado en la venta "
            f"({total_pagado:,.2f} COP). No se puede devolver más de lo pagado."
        )

    datos = esquema.model_dump()
    datos["monto_en_moneda_base"] = monto_devuelto_base
    obj = model.DevolucionVenta(**datos)
    db.add(obj)
    db.flush()

    # 2. El reembolso SALE de la misma cuenta por la que se cobró (último pago).
    #    Sin esto, la devolución era solo un número en el ER: el dinero cobrado
    #    permanecía en caja y se contaba dos veces.
    ultimo_pago = db.query(Pago).filter(Pago.venta_id == venta.id).order_by(Pago.id.desc()).first()
    if ultimo_pago and ultimo_pago.metodo_pago:
        from app.core.caja import registrar_movimiento_caja
        registrar_movimiento_caja(
            db,
            codigo=ultimo_pago.metodo_pago,
            tipo="SALIDA",
            monto=float(esquema.monto_devuelto),
            moneda_id=esquema.moneda_id,
            tasa_cambio=float(esquema.tasa_cambio or 1.0),
            fecha=esquema.fecha,
            referencia=f"Devolución venta #{venta.id}",
            observaciones=esquema.motivo or f"Devolución de la venta #{venta.id}",
        )

    db.commit()
    db.refresh(obj)
    return obj

def eliminar_devolucion(db: Session, devolucion_id: int) -> bool:
    obj = db.query(model.DevolucionVenta).filter(model.DevolucionVenta.id == devolucion_id).first()
    if not obj:
        return False
    # Revertir el reembolso de caja (ENTRADA de vuelta) para no dejar egresos fantasma.
    from app.modules.reports.model import MovimientoCaja
    db.query(MovimientoCaja).filter(
        MovimientoCaja.referencia == f"Devolución venta #{obj.venta_id}"
    ).delete(synchronize_session=False)
    db.delete(obj)
    db.commit()
    return True
