from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# ------------------------------------------------------------
# TipoProducto
# ------------------------------------------------------------
class TipoProductoBase(BaseModel):
    nombre: str

class TipoProductoCreate(TipoProductoBase):
    pass

class TipoProductoUpdate(BaseModel):
    nombre: Optional[str] = None

class TipoProductoResponse(TipoProductoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# UnidadMedida
# ------------------------------------------------------------
class UnidadMedidaBase(BaseModel):
    nombre: str
    abreviatura: str

class UnidadMedidaCreate(UnidadMedidaBase):
    pass

class UnidadMedidaUpdate(BaseModel):
    nombre: Optional[str] = None
    abreviatura: Optional[str] = None

class UnidadMedidaResponse(UnidadMedidaBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# TipoGasto
# ------------------------------------------------------------
class TipoGastoBase(BaseModel):
    nombre: str
    categoria: str = "OPERATIVO"

class TipoGastoCreate(TipoGastoBase):
    pass

class TipoGastoUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None

class TipoGastoResponse(TipoGastoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Ubicacion
# ------------------------------------------------------------
class UbicacionBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    tipo: str  # DEPOSITO, TALLER, PUNTO_VENTA
    activo: Optional[bool] = True

class UbicacionCreate(UbicacionBase):
    pass

class UbicacionUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None
    activo: Optional[bool] = None

class UbicacionResponse(UbicacionBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Area
# ------------------------------------------------------------
class AreaBase(BaseModel):
    nombre: str

class AreaCreate(AreaBase):
    pass

class AreaUpdate(BaseModel):
    nombre: Optional[str] = None

class AreaResponse(AreaBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Cargo
# ------------------------------------------------------------
class CargoBase(BaseModel):
    nombre: str

class CargoCreate(CargoBase):
    pass

class CargoUpdate(BaseModel):
    nombre: Optional[str] = None

class CargoResponse(CargoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Moneda
# ------------------------------------------------------------
class MonedaBase(BaseModel):
    codigo: str  # COP, USD, VES
    nombre: str
    simbolo: str
    activo: Optional[bool] = True

class MonedaCreate(MonedaBase):
    pass

class MonedaUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    simbolo: Optional[str] = None
    activo: Optional[bool] = None

class MonedaResponse(MonedaBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ------------------------------------------------------------
# Rol
# ------------------------------------------------------------
class RolBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: Optional[bool] = True

class RolCreate(RolBase):
    pass

class RolUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class RolResponse(RolBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
