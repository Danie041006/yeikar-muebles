from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import calendar
from decimal import Decimal

from app.modules.orders.model import Pedido
from app.modules.production.model import OrdenProduccion
from app.modules.inventory.model import Inventario
from app.modules.sales.model import Pago, Venta
from app.modules.catalogos.model import Moneda
from app.modules.dashboard import schemas
from app.core.hora_ve import hoy_ve
from app.modules.users.deps import filtrar_registros_propios, tiene_alcance_total
from app.modules.users.model import Usuario

def obtener_metricas_dashboard(db: Session, usuario: Usuario) -> schemas.DashboardMetricsResponse:
    # 1. Pedidos activos (que no están entregados ni cancelados)
    pedidos_query = db.query(Pedido).filter(
        Pedido.estado.notin_(["ENTREGADO", "CANCELADO"])
    )
    pedidos_activos = filtrar_registros_propios(pedidos_query, Pedido.creado_por_id, usuario).count()

    # 2. Órdenes de producción activas (no finalizadas ni canceladas)
    ordenes_query = db.query(OrdenProduccion).filter(
        OrdenProduccion.estado.in_(["PENDIENTE", "EN_PRODUCCION", "PAUSADA"])
    )
    ordenes_activas = filtrar_registros_propios(ordenes_query, OrdenProduccion.creado_por_id, usuario).count()

    # 3. Alertas de stock (materiales con cantidad <= 5)
    alertas_stock = (
        db.query(Inventario).filter(Inventario.cantidad <= 5.0).count()
        if tiene_alcance_total(usuario)
        else 0
    )

    # 4. Ingresos del mes actual (mes de Venezuela, no UTC)
    hoy = hoy_ve()
    year = hoy.year
    month = hoy.month
    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0)
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    ingresos_query = (
        db.query(Moneda.codigo, func.sum(Pago.monto).label("total"))
        .join(Pago, Pago.moneda_id == Moneda.id)
        .join(Venta, Venta.id == Pago.venta_id)
        .filter(Pago.fecha >= start_dt, Pago.fecha <= end_dt)
        .group_by(Moneda.codigo)
    )
    ingresos_query = filtrar_registros_propios(ingresos_query, Venta.creado_por_id, usuario).all()

    ingresos_mes = [
        schemas.IngresoMesDetail(
            moneda=row.codigo,
            monto=Decimal(str(row.total or 0.0))
        )
        for row in ingresos_query
    ]

    return schemas.DashboardMetricsResponse(
        pedidos_activos=pedidos_activos,
        ordenes_produccion_activas=ordenes_activas,
        alertas_stock=alertas_stock,
        ingresos_mes=ingresos_mes
    )
