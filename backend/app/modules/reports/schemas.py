from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal

class PnLDetail(BaseModel):
    moneda: str
    ingresos: Decimal
    gastos: Decimal
    balance: Decimal

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
