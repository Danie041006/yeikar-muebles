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
        tasa_venta = Decimal(str(venta.tasa_cambio or 1.0)) if venta.moneda_id != 1 else Decimal("1.0")
        if venta.moneda_id != 1 and tasa_venta == Decimal("1.0"):
            tasa_venta = obtener_tasa_moneda_a_cop(db, venta.moneda_id, venta.fecha)
        for dv in detalle_por_venta.get(venta.id, []):
            costo_unit = Decimal(str(dv.costo_unitario or 0.0))
            pct = Decimal(str(dv.porcentaje_ganancia or 0.0)) if dv.porcentaje_ganancia is not None else None
            precio = Decimal(str(dv.precio))
            cantidad = Decimal(str(dv.cantidad))
            utilidad = Decimal(str(dv.utilidad or (precio - costo_unit))) * cantidad
            descuento = Decimal(str(dv.descuento or 0.0)) * cantidad
            lineas.append(
                schemas.LineaIngresoInforme(
                    fecha=venta.fecha,
                    cliente=venta.cliente.nombre if venta.cliente else "—",
                    cantidad=cantidad,
                    producto=dv.producto.nombre if dv.producto else "—",
                    costo_unitario=costo_unit,
                    precio_costo=costo_unit * cantidad,
                    porcentaje_ganancia=pct,
                    utilidad=utilidad,
                    precio_venta=precio * cantidad,
                    descuento=descuento,
                    moneda=venta.moneda.codigo if venta.moneda else "COP",
                    tasa_cambio=tasa_venta,
                    precio_venta_en_base=(precio * cantidad) * tasa_venta,
                    es_devolucion=False,
                )
            )

    # Devoluciones del mes como líneas negativas
    for dev in devoluciones_mes:
        venta = dev.venta
        tasa_dev = Decimal(str(dev.tasa_cambio or 1.0))
        base = Decimal(str(dev.monto_en_moneda_base or (dev.monto_devuelto * tasa_dev)))
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
                precio_venta_en_base=-base,
                es_devolucion=True,
            )
        )

    totales = schemas.TotalesIngresoInforme(
        precio_costo=sum(l.precio_costo for l in lineas),
        utilidad=sum(l.utilidad for l in lineas),
        precio_venta=sum(l.precio_venta for l in lineas),
        precio_venta_en_base=sum(l.precio_venta_en_base for l in lineas),
        descuentos=sum(l.descuento for l in lineas),
    )

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
    # Ventas contado / crédito
    contado = Decimal("0.0")
    credito = Decimal("0.0")
    for venta in ventas_mes:
        pagos = pagos_por_venta.get(venta.id, [])
        total_pagado = sum(Decimal(str(p.monto_en_moneda_base or p.monto)) for p in pagos)
        total_venta = Decimal(str(venta.total))
        if len(pagos) == 1 and total_pagado >= total_venta:
            contado += _venta_en_cop(db, venta)
        else:
            credito += _venta_en_cop(db, venta)

    devoluciones_total = sum(
        Decimal(str(d.monto_en_moneda_base or (d.monto_devuelto * d.tasa_cambio)))
        for d in devoluciones_mes
    )
    descuentos_total = sum(
        Decimal(str(dv.descuento or 0.0)) * Decimal(str(dv.cantidad))
        for venta in ventas_mes for dv in detalle_por_venta.get(venta.id, [])
    )
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
    for c in conceptos:
        val = valores.get(c.id)
        v_inicial = Decimal(str(val.valor_inicial)) if val else Decimal("0.0")
        v_final = Decimal(str(val.valor_final)) if val else Decimal("0.0")
        inventarios_iniciales.append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_inicial))
        inventarios_finales.append(schemas.LineaValorConcepto(concepto_id=c.id, nombre=c.nombre, valor=v_final))
        total_inicial += v_inicial
        total_final += v_final

    # Saldos de caja a fin de mes (en COP). NO forman parte del inventario:
    # sumarlos a inventarios_finales fabricaba una utilidad ficticia (el costo
    # de ventas salía negativo por decenas de millones). Se exponen aparte en
    # el informe (campo saldos_caja al final de la respuesta).
    metodos_caja = db.query(model.MetodoCaja).filter(model.MetodoCaja.activo == True).order_by(model.MetodoCaja.orden).all()
    saldos_caja = []
    for mc in metodos_caja:
        saldo = _saldo_caja_en_cop(db, mc.id, end_date)
        saldos_caja.append(schemas.LineaValorConcepto(concepto_id=-mc.id, nombre=mc.nombre, valor=saldo))

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

    for pedido in pedidos_cierre:
        venta = venta_por_pedido.get(pedido.id)
        productos: str = "—"

        def _texto_productos(origen) -> str:
            partes = []
            for det in origen:
                nombre = det.producto.nombre if (det.producto and det.producto.nombre) else f"Producto #{det.producto_id}"
                partes.append(f"{nombre} x{det.cantidad}")
            return ", ".join(partes) if partes else "—"

        if venta:
            if venta.estado not in ("PENDIENTE", "ABONADA"):
                continue
            total_base = _venta_en_cop(db, venta)
            pagado_base = sum(
                Decimal(str(p.monto_en_moneda_base or p.monto))
                for p in pagos_por_venta_cierre.get(venta.id, [])
            )
            saldo = total_base - pagado_base
            if saldo <= Decimal("1.0"):  # ignora residuos de centavos por redondeo
                continue
            productos = _texto_productos(detalle_por_venta.get(venta.id, []))
            if productos == "—":
                productos = _texto_productos(pedido.detalles)
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
                producto=_texto_productos(pedido.detalles),
                estado_pedido=pedido.estado,
                estado_venta=None,
                moneda=moneda_pedido,
                total_en_base=total_base,
                pagado_en_base=Decimal("0.0"),
                saldo_en_base=total_base,
            )
        )

    total_pendiente = sum(l.saldo_en_base for l in pedidos_pendientes)

    return schemas.InformeMensualResponse(
        mes=mes,
        control_interno_ingresos=schemas.ControlInternoIngresos(lineas=lineas, totales=totales),
        resumen=resumen,
        estado_resultados=estado,
        pendientes_de_pago=schemas.PendientesDePagoInforme(
            lineas=pedidos_pendientes,
            total_pendiente=total_pendiente,
        ),
        saldos_caja=saldos_caja,
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
    obj = model.MetodoCaja(**esquema.model_dump())
    db.add(obj)
    db.flush()
    # Por defecto, toda cuenta nueva abre con un millón (COP) de saldo inicial.
    from app.core.caja import registrar_movimiento_caja
    registrar_movimiento_caja(
        db,
        metodo_caja_id=obj.id,
        tipo="APERTURA",
        monto=1_000_000.0,
        moneda_id=1,
        tasa_cambio=1.0,
        fecha=date.today(),
        referencia="Saldo inicial por defecto",
        observaciones="Apertura por defecto: 1.000.000 COP",
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
    db.delete(obj)
    db.commit()
    return True


def _concepto_movimiento(db: Session, m: "model.MovimientoCaja"):
    """Devuelve (concepto legible, responsable) de un movimiento de caja.

    Interpreta la `referencia` estándar ("Gasto #N", "Pago #N", "Nómina #N",
    "Compra #N") para enriquecerlo con el nombre real; queda NULL quien no
    aplica o si el registro original ya no existe.
    """
    quien = m.usuario.nombre_usuario if m.usuario else None
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
            return concepto, (g.creador.nombre_usuario if g.creador else quien)
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
    return ref or "Movimiento", quien


def resumen_diario(db: Session, dia: date) -> schemas.ResumenDiarioResponse:
    """Estado del día: saldo inicial, ingresos, egresos y quién los hizo.

    Se construye desde `movimiento_caja` (la bitácora única de caja). La
    convención es la misma que _saldo_caja_en_cop: SALIDA resta; el resto
    suma (AJUSTE lleva su signo en el monto). Todo se expresa en COP.
    """
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

    # Saldo inicial (antes del día) por cuenta
    inicial_por_cuenta: Dict[int, Decimal] = {}
    for m in movs:
        if m.fecha < dia:
            inicial_por_cuenta[m.metodo_caja_id] = (
                inicial_por_cuenta.get(m.metodo_caja_id, Decimal("0")) + signo(m) * cop(m)
            )

    # Movimientos del día + totales COP + desglose por moneda
    movimientos: List[schemas.MovimientoDiarioResponse] = []
    total_ingresos_cop = Decimal("0.0")
    total_egresos_cop = Decimal("0.0")
    por_moneda: Dict[int, dict] = {}
    final_por_cuenta: Dict[int, Decimal] = dict(inicial_por_cuenta)

    for m in movs:
        if m.fecha != dia:
            continue
        montocop = cop(m)
        val_cuenta = final_por_cuenta.get(m.metodo_caja_id, Decimal("0"))
        final_por_cuenta[m.metodo_caja_id] = val_cuenta + signo(m) * montocop
        if m.tipo == "SALIDA":
            # Los egresos con cuenta se listan desde la TABLA GASTO (más abajo)
            # para no duplicarlos: su movimiento de caja sale por referencia.
            es_salida_de_gasto = bool((m.referencia or "").startswith("Gasto #"))
            if not es_salida_de_gasto:
                total_egresos_cop += montocop
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
            total_ingresos_cop += montocop
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
            if g.area and g.area.nombre:
                concepto += f" · {g.area.nombre}"
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
                    quien=(g.creador.nombre_usuario if g.creador else "Sistema"),
                )
            )

    saldo_inicial_cop = sum(inicial_por_cuenta.values(), Decimal("0"))
    saldo_final_cop = sum(final_por_cuenta.values(), Decimal("0"))

    saldos_por_cuenta = [
        schemas.SaldoCuentaDiaria(
            metodo_caja_id=mid,
            cuenta_nombre=mc.nombre,
            saldo_inicial_cop=inicial_por_cuenta.get(mid, Decimal("0")),
            saldo_final_cop=final_por_cuenta.get(mid, Decimal("0")),
        )
        for mid, mc in {mm.metodo_caja_id: mm.metodo_caja for mm in movs if mm.metodo_caja}.items()
    ]

    return schemas.ResumenDiarioResponse(
        fecha=dia,
        saldo_inicial_cop=saldo_inicial_cop,
        total_ingresos_cop=total_ingresos_cop,
        total_egresos_cop=total_egresos_cop,
        saldo_final_cop=saldo_final_cop,
        movimientos=movimientos,
        por_moneda=[schemas.LineaMonedaDiaria(**data) for data in por_moneda.values()],
        saldos_por_cuenta=saldos_por_cuenta,
    )


def resumen_cuentas(db: Session) -> List[dict]:
    """
    Saldo por cada cuenta activa: desglosado por moneda (en su propia moneda
    y en COP) y total en COP. Usa la misma convención que _saldo_caja_en_cop:
    SALIDA resta; APERTURA/ENTRADA/AJUSTE suman (AJUSTE puede ser negativo).
    """
    metodos = listar_metodos_caja(db)
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
        resumen.append(schemas.ResumenCuentaResponse(metodo_caja=mc, saldo_por_moneda=lineas))
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
