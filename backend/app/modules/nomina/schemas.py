from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal

from app.modules.catalogos.schemas import AreaResponse


# ------------------------------------------------------------
# Área config (aguinaldo %)
# ------------------------------------------------------------
class NominaAreaConfigCreate(BaseModel):
    area_id: int
    porcentaje_aguinaldo: Decimal = Field(..., ge=0, le=100)

class NominaAreaConfigResponse(BaseModel):
    id: int
    area_id: int
    porcentaje_aguinaldo: Decimal
    area: Optional[AreaResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Líneas
# ------------------------------------------------------------
class NominaLineaCreate(BaseModel):
    descripcion: str = Field(..., max_length=250)
    cantidad: Decimal = Field(1, gt=0, le=Decimal("1000000"))
    # Tope anti-desfalco: una línea manual no puede inventar millones.
    precio_unitario: Decimal = Field(..., ge=0, le=Decimal("100000000"))

class NominaLineaResponse(BaseModel):
    id: int
    detalle_id: int
    origen: str
    etapa_id: Optional[int] = None
    descripcion: str
    area_id: Optional[int] = None
    cliente_nombre: Optional[str] = None
    cantidad: Decimal
    precio_unitario: Decimal
    total: Decimal
    area: Optional[AreaResponse] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Conceptos varios
# ------------------------------------------------------------
class ConceptoVarioCreate(BaseModel):
    descripcion: str = Field(..., max_length=200)
    monto: Decimal = Field(..., ge=0, le=Decimal("100000000"))

class ConceptoVarioResponse(ConceptoVarioCreate):
    id: int

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Nómina
# ------------------------------------------------------------
class NominaDetalleUpdate(BaseModel):
    monto_a_pagar: Optional[Decimal] = Field(None, ge=0)
    metodo_caja_id: Optional[int] = None
    observaciones: Optional[str] = None

class NominaDetalleResponse(BaseModel):
    id: int
    nomina_id: int
    empleado_id: int
    empleado_nombre: str
    cargo_nombre: Optional[str] = None
    tipo_pago: str
    total_produccion: Decimal
    bono_aguinaldo: Decimal
    monto_a_pagar: Decimal
    metodo_caja_id: Optional[int] = None
    metodo_caja_nombre: Optional[str] = None
    gasto_id: Optional[int] = None
    observaciones: Optional[str] = None
    lineas: List[NominaLineaResponse] = []

    class Config:
        from_attributes = True

class NominaCreate(BaseModel):
    periodo_desde: date
    periodo_hasta: date
    descripcion: Optional[str] = None
    detalles: List[NominaDetalleUpdate] = []
    conceptos_varios: List[ConceptoVarioCreate] = []

class NominaResponse(BaseModel):
    id: int
    periodo_desde: date
    periodo_hasta: date
    estado: str
    descripcion: Optional[str] = None
    total_nomina: Decimal
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    detalles: List[NominaDetalleResponse] = []
    conceptos_varios: List[ConceptoVarioResponse] = []

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# Generación (draft)
# ------------------------------------------------------------
class LineaDraft(BaseModel):
    origen: str
    etapa_id: Optional[int] = None
    descripcion: str
    area_id: Optional[int] = None
    area_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cantidad: Decimal
    precio_unitario: Decimal
    total: Decimal

class DetalleDraft(BaseModel):
    empleado_id: int
    empleado_nombre: str
    cargo_nombre: Optional[str] = None
    tipo_pago: str
    total_produccion: Decimal
    bono_aguinaldo: Decimal
    monto_a_pagar: Decimal
    lineas: List[LineaDraft] = []

class NominaDraftResponse(BaseModel):
    periodo_desde: date
    periodo_hasta: date
    detalles: List[DetalleDraft]
    total_nomina: Decimal


# ------------------------------------------------------------
# Saldos de aguinaldo
# ------------------------------------------------------------
class SaldoAguinaldoResponse(BaseModel):
    empleado_id: int
    empleado_nombre: str
    cargo_nombre: Optional[str] = None
    saldo_aguinaldo: Decimal


class PagoAguinaldoRequest(BaseModel):
    empleado_id: int
    metodo_caja_id: int
    observaciones: Optional[str] = None


class PagoAguinaldoResponse(BaseModel):
    empleado_id: int
    empleado_nombre: str
    monto: Decimal
    gasto_id: int
    saldo_restante: Decimal
