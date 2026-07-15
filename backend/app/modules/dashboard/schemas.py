from pydantic import BaseModel
from typing import List
from decimal import Decimal

class IngresoMesDetail(BaseModel):
    moneda: str
    monto: Decimal

class DashboardMetricsResponse(BaseModel):
    pedidos_activos: int
    ordenes_produccion_activas: int
    alertas_stock: int
    ingresos_mes: List[IngresoMesDetail]
