# backend/app/modules/inventory/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal

# Stock actual (Inventario)
class InventarioResponse(BaseModel):
    id: int
    material_id: int
    material_nombre: Optional[str] = None   
    ubicacion_id: int
    ubicacion_nombre: Optional[str] = None
    cantidad: Decimal
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Movimientos

class MovimientoCreate(BaseModel):
    material_id: int
    ubicacion_id: int
    tipo: str = Field(..., pattern="^(ENTRADA|SALIDA|AJUSTE|DAÑO|DEVOLUCION)$")
    cantidad: Decimal = Field(..., gt=0)
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[int] = None
    observaciones: Optional[str] = None

class MovimientoResponse(MovimientoCreate):
    id: int
    fecha: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# clase para dar un aviso de que hay productos que tiene stock bajo

class AlertaStockResponse(BaseModel):
    material_id: int
    material_nombre: str
    stock_actual: Decimal
    stock_minimo: Decimal   
    ubicacion_id: int
    ubicacion_nombre: str


# =========================================================================
# Inventario de PRODUCTOS (terminados / de reventa)
# =========================================================================

class ProductoInventarioResponse(BaseModel):
    id: int
    producto_id: int
    producto_nombre: Optional[str] = None
    producto_codigo: Optional[str] = None
    es_reventa: Optional[bool] = None
    ubicacion_id: int
    ubicacion_nombre: Optional[str] = None
    cantidad: Decimal
    costo_promedio: Optional[Decimal] = None
    stock_minimo: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MovimientoProductoCreate(BaseModel):
    producto_id: int
    ubicacion_id: int
    tipo: str = Field(..., pattern="^(ENTRADA|SALIDA|AJUSTE|DAÑO|DEVOLUCION)$")
    cantidad: Decimal = Field(..., gt=0)
    costo_unitario: Optional[Decimal] = Field(None, gt=0)
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[int] = None
    observaciones: Optional[str] = None


class MovimientoProductoResponse(MovimientoProductoCreate):
    id: int
    fecha: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertaStockProductoResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    stock_actual: Decimal
    stock_minimo: Decimal
    ubicacion_id: int
    ubicacion_nombre: str