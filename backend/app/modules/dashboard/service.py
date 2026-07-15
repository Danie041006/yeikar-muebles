from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import calendar
from decimal import Decimal

from app.modules.orders.model import Pedido
from app.modules.production.model import OrdenProduccion
from app.modules.inventory.model import Inventario
from app.modules.sales.model import Pago
from app.modules.catalogos.model import Moneda
from app.modules.dashboard import schemas

def obtener_metricas_dashboard(db: Session) -> schemas.DashboardMetricsResponse:
    # 1. Pedidos activos (que no están entregados ni cancelados)
    pedidos_activos = db.query(Pedido).filter(
        Pedido.estado.notin_(["ENTREGADO", "CANCELADO"])
    ).count()

    # 2. Órdenes de producción activas (no finalizadas ni canceladas)
    ordenes_activas = db.query(OrdenProduccion).filter(
        OrdenProduccion.estado.in_(["PENDIENTE", "EN_PRODUCCION", "PAUSADA"])
    ).count()

    # 3. Alertas de stock (materiales con cantidad <= 5)
    alertas_stock = db.query(Inventario).filter(
        Inventario.cantidad <= 5.0
    ).count()

    # 4. Ingresos del mes actual
    now = datetime.utcnow()
    year = now.year
    month = now.month
    _, last_day = calendar.monthrange(year, month)
    start_dt = datetime(year, month, 1, 0, 0, 0)
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    ingresos_query = (
        db.query(Moneda.codigo, func.sum(Pago.monto).label("total"))
        .join(Pago, Pago.moneda_id == Moneda.id)
        .filter(Pago.fecha >= start_dt, Pago.fecha <= end_dt)
        .group_by(Moneda.codigo)
        .all()
    )

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
