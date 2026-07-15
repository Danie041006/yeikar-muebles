from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Dict
from decimal import Decimal
from datetime import datetime, date
import calendar

from app.modules.sales.model import Pago, Venta, DetalleVenta
from app.modules.gastos.model import Gasto
from app.modules.catalogos.model import Moneda, UnidadMedida
from app.modules.productos.model import Producto
from app.modules.production.model import CostoProduccion, OrdenProduccion, ManoObra, EtapaProduccion
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.purchases.model import Compra, DetalleCompra
from app.modules.inventory.model import Inventario
from app.modules.reports import schemas

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

    # 1. Obtener ingresos por moneda (pagos recibidos)
    ingresos_query = (
        db.query(Moneda.codigo, func.sum(Pago.monto).label("total"))
        .join(Pago, Pago.moneda_id == Moneda.id)
        .filter(Pago.fecha >= start_dt, Pago.fecha <= end_dt)
        .group_by(Moneda.codigo)
        .all()
    )
    ingresos_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in ingresos_query}

    # 2a. Obtener gastos generales por moneda
    gastos_query = (
        db.query(Moneda.codigo, func.sum(Gasto.monto).label("total"))
        .join(Gasto, Gasto.moneda_id == Moneda.id)
        .filter(Gasto.fecha >= start_date, Gasto.fecha <= end_date)
        .group_by(Moneda.codigo)
        .all()
    )
    gastos_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in gastos_query}

    # 2b. Obtener compras de materiales en estado RECIBIDA por moneda
    compras_query = (
        db.query(Moneda.codigo, func.sum(DetalleCompra.cantidad * DetalleCompra.costo_unitario).label("total"))
        .select_from(DetalleCompra)
        .join(Compra, DetalleCompra.compra_id == Compra.id)
        .join(Moneda, Compra.moneda_id == Moneda.id)
        .filter(Compra.fecha >= start_date, Compra.fecha <= end_date, Compra.estado == "RECIBIDA")
        .group_by(Moneda.codigo)
        .all()
    )
    compras_dict = {row.codigo: Decimal(str(row.total or 0.0)) for row in compras_query}

    # 2c. Obtener mano de obra pagada por moneda (vía pedido -> venta -> moneda)
    mano_obra_list = (
        db.query(ManoObra, Moneda.codigo.label("moneda_cod"))
        .select_from(ManoObra)
        .join(EtapaProduccion, ManoObra.etapa_produccion_id == EtapaProduccion.id)
        .join(OrdenProduccion, EtapaProduccion.orden_produccion_id == OrdenProduccion.id)
        .join(DetallePedido, OrdenProduccion.detalle_pedido_id == DetallePedido.id)
        .join(Pedido, DetallePedido.pedido_id == Pedido.id)
        .outerjoin(Venta, Venta.pedido_id == Pedido.id)
        .outerjoin(Moneda, Venta.moneda_id == Moneda.id)
        .filter(ManoObra.updated_at >= start_dt, ManoObra.updated_at <= end_dt, ManoObra.pagado == True)
        .all()
    )

    mano_obra_dict = {}
    for mo, moneda_cod in mano_obra_list:
        cod = moneda_cod or "COP"  # fallback a COP si no hay venta/moneda asociada
        recargo = Decimal(str(mo.porcentaje_recargo or 0.0)) / Decimal("100.0")
        monto_total = Decimal(str(mo.monto)) * (Decimal("1.0") + recargo)
        mano_obra_dict[cod] = mano_obra_dict.get(cod, Decimal("0.0")) + monto_total

    # 3. Combinar todas las monedas
    todas_monedas = set(ingresos_dict.keys()).union(gastos_dict.keys(), compras_dict.keys(), mano_obra_dict.keys())
    detalles = []
    for cod in todas_monedas:
        ing = ingresos_dict.get(cod, Decimal("0.0"))
        gas = gastos_dict.get(cod, Decimal("0.0"))
        com = compras_dict.get(cod, Decimal("0.0"))
        mo_val = mano_obra_dict.get(cod, Decimal("0.0"))

        # Egresos totales = Gastos generales + Compras recibidas + Mano de obra pagada
        egresos_totales = gas + com + mo_val

        detalles.append(
            schemas.PnLDetail(
                moneda=cod,
                ingresos=ing,
                gastos=egresos_totales,
                balance=ing - egresos_totales
            )
        )

    return schemas.PnLResponse(mes=mes, detalles=detalles)


def obtener_rentabilidad_productos(db: Session) -> List[schemas.RentabilidadProductoResponse]:
    # Obtener todos los productos
    productos = db.query(Producto).filter(Producto.activo == True).all()
    resultados = []

    for prod in productos:
        # 1. Ventas de este producto
        ventas_info = (
            db.query(
                Venta.moneda_id,
                func.sum(DetalleVenta.cantidad).label("cantidad"),
                func.sum(DetalleVenta.cantidad * DetalleVenta.precio).label("ingreso_total")
            )
            .join(DetalleVenta, DetalleVenta.venta_id == Venta.id)
            .filter(DetalleVenta.producto_id == prod.id)
            .group_by(Venta.moneda_id)
            .all()
        )

        # 2. Costo promedio de producción
        # Buscamos órdenes de producción completadas para este producto
        costos_prod = (
            db.query(func.avg(CostoProduccion.costo_total).label("costo_promedio"))
            .join(OrdenProduccion, CostoProduccion.orden_produccion_id == OrdenProduccion.id)
            .join(DetallePedido, OrdenProduccion.detalle_pedido_id == DetallePedido.id)
            .filter(DetallePedido.producto_id == prod.id, OrdenProduccion.estado == "FINALIZADA")
            .scalar()
        )
        costo_medio = float(costos_prod or 0.0)

        for v in ventas_info:
            moneda = db.query(Moneda).filter(Moneda.id == v.moneda_id).first()
            moneda_cod = moneda.codigo if moneda else "USD"
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
