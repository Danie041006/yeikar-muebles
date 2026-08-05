from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List

class CompraBase(BaseModel):
    proveedor_id: int
    moneda_id: int
    fecha: date
    estado: str = "BORRADOR"
    tipo_pago: str = "CREDITO"  # CONTADO | CREDITO
    observaciones: Optional[str] = None

class CompraCreate(BaseModel):
    proveedor_id: int
    moneda_id: int
    fecha: date
    estado: Optional[str] = "BORRADOR"
    tipo_pago: Optional[str] = "CREDITO"
    observaciones: Optional[str] = None
    detalle: List["DetalleCompraCreate"]

class CompraResponse(CompraBase):
    id: int
    total: Decimal
    tasa_cambio: Decimal
    total_en_moneda_base: Optional[Decimal]
    created_at: datetime
    updated_at: datetime
    detalle: List["DetalleCompraResponse"] = Field(validation_alias="detalles")

    class Config:
        from_attributes = True

class DetalleCompraBase(BaseModel):
    material_id: int
    cantidad: Decimal = Field(..., gt=0)
    costo_unitario: Decimal = Field(..., gt=0)

class DetalleCompraCreate(DetalleCompraBase):
    pass

class DetalleCompraResponse(DetalleCompraBase):
    id: int
    compra_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# No usar update_forward_refs que es de Pydantic v1. Usar model_rebuild si es necesario.
# En Pydantic v2 (FastAPI moderno), las referencias circulares se manejan automáticamente o con model_rebuild().
# Dejamos model_rebuild al final.
CompraCreate.model_rebuild()
CompraResponse.model_rebuild()

