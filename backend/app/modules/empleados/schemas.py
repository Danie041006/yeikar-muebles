from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional
from decimal import Decimal
from app.modules.catalogos.schemas import CargoResponse

# Tope razonable para sueldos: 100 millones por semana (evita desfalco vía
# configuración de nómina con sueldos de 1e12).
SUELDO_MAX = Decimal("100000000")

class EmpleadoBase(BaseModel):
    nombre: str
    cargo_id: int
    telefono: Optional[str] = None
    activo: Optional[bool] = True
    # Campos de nómina
    en_nomina: Optional[bool] = False
    tipo_pago: Optional[Literal["DESTAJO", "FIJO"]] = None  # DESTAJO | FIJO
    sueldo_semanal: Optional[Decimal] = Field(None, ge=0, le=SUELDO_MAX)
    porcentaje_aguinaldo: Optional[Decimal] = Field(None, ge=0, le=100)

class EmpleadoCreate(EmpleadoBase):
    pass

class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    cargo_id: Optional[int] = None
    telefono: Optional[str] = None
    activo: Optional[bool] = None
    en_nomina: Optional[bool] = None
    tipo_pago: Optional[Literal["DESTAJO", "FIJO"]] = None
    sueldo_semanal: Optional[Decimal] = Field(None, ge=0, le=SUELDO_MAX)
    porcentaje_aguinaldo: Optional[Decimal] = Field(None, ge=0, le=100)

class EmpleadoResponse(EmpleadoBase):
    id: int
    saldo_aguinaldo: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cargo: Optional[CargoResponse] = None

    class Config:
        from_attributes = True
