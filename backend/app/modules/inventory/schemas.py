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
    # Info para la UI: dimensiones de lámina y categoría de inventario
    material_largo_cm: Optional[Decimal] = None
    material_ancho_cm: Optional[Decimal] = None
    material_unidad: Optional[str] = None
    categoria_inventario_id: Optional[int] = None
    categoria_inventario_nombre: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Movimientos

class MovimientoCreate(BaseModel):
    material_id: int
    ubicacion_id: int
    tipo: str = Field(..., pattern="^(ENTRADA|SALIDA|AJUSTE|DAÑO|DANO|DEVOLUCION)$")
    cantidad: Decimal = Field(..., gt=0)
    costo_unitario: Optional[Decimal] = Field(None, gt=0)
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[int] = None
    observaciones: Optional[str] = None
    # "La llevada": flete/aduana que se paga además del valor de la compra
    # para que el insumo entre al país (compra en el exterior). Opcional.
    # En una ENTRADA pagada desde una cuenta se registra como un gasto aparte
    # ("FLETE / LLEVADA") con salida de esa misma caja.
    llevada: Optional[Decimal] = Field(None, ge=0)
    # Compra de contado: si la ENTRADA se paga desde una cuenta de caja, se
    # genera automáticamente un gasto "COMPRA DE INSUMOS" + la salida de esa caja.
    # La tasa es obligatoria cuando la moneda de pago no es COP (insumos en COP):
    # convención "1 [moneda_pago] = X COP".
    pagado_desde_metodo_caja_id: Optional[int] = None
    moneda_pago_id: Optional[int] = None
    tasa_pago: Optional[Decimal] = Field(None, gt=0)
    # Opcionales (solo entradas): proveedor = dónde se compró; cliente = material
    # comprado para un cliente específico.
    proveedor_id: Optional[int] = None
    cliente_id: Optional[int] = None
    # "Fiar": ENTRADA sin pagar de una cuenta → se registra automáticamente una
    # cuenta por pagar (compra + pasada) con el proveedor indicado.
    fiar: Optional[bool] = False

class MovimientoResponse(MovimientoCreate):
    id: int
    fecha: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None
    proveedor_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None

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
    tipo: str = Field(..., pattern="^(ENTRADA|SALIDA|AJUSTE|DAÑO|DANO|DEVOLUCION)$")
    cantidad: Decimal = Field(..., gt=0)
    costo_unitario: Optional[Decimal] = Field(None, gt=0)
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[int] = None
    observaciones: Optional[str] = None
    # "La llevada": flete/aduana pagada además del valor de compra (opcional).
    # En una ENTRADA pagada desde una cuenta registra el gasto "FLETE / LLEVADA".
    llevada: Optional[Decimal] = Field(None, ge=0)
    # Egreso automático de compra: si la ENTRADA se pagó de contado, indica
    # desde qué cuenta de caja salió el dinero. Con costo + cuenta se genera
    # un gasto "Compra inventario reventa" + la salida de esa caja.
    # Moneda de pago opcional (default: la moneda del producto) y tasa manual
    # "1 [moneda_pago] = X COP" — obligatoria cuando moneda_pago ≠ COP y la del
    # producto tampoco lo es (la tabla de tasas ya no se usa: tasa por operación).
    pagado_desde_metodo_caja_id: Optional[int] = None
    moneda_pago_id: Optional[int] = None
    tasa_pago: Optional[Decimal] = Field(None, gt=0)
    # Opcionales (solo entradas): proveedor = dónde se compró; cliente = producto
    # comprado para un cliente específico.
    proveedor_id: Optional[int] = None
    cliente_id: Optional[int] = None


class MovimientoProductoResponse(MovimientoProductoCreate):
    id: int
    fecha: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None
    proveedor_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class AlertaStockProductoResponse(BaseModel):
    producto_id: int
    producto_nombre: str
    stock_actual: Decimal
    stock_minimo: Decimal
    ubicacion_id: int
    ubicacion_nombre: str


# =========================================================================
# Sobrantes de láminas (retazos reutilizables de materiales laminares)
# =========================================================================

class SobranteLaminaCreate(BaseModel):
    material_id: int
    ubicacion_id: int = 1
    largo_cm: Decimal = Field(..., gt=0)
    ancho_cm: Decimal = Field(..., gt=0)
    observaciones: Optional[str] = None


class SobranteLaminaUpdate(BaseModel):
    largo_cm: Optional[Decimal] = Field(None, gt=0)
    ancho_cm: Optional[Decimal] = Field(None, gt=0)
    estado: Optional[str] = Field(None, pattern="^(DISPONIBLE|CONSUMIDO|DESECHADO)$")
    ubicacion_id: Optional[int] = None
    observaciones: Optional[str] = None


class SobranteLaminaResponse(BaseModel):
    id: int
    material_id: int
    material_nombre: Optional[str] = None
    material_largo_cm: Optional[Decimal] = None
    material_ancho_cm: Optional[Decimal] = None
    ubicacion_id: int
    ubicacion_nombre: Optional[str] = None
    largo_cm: Decimal
    ancho_cm: Decimal
    area_cm2: Decimal
    estado: str
    consumo_origen_id: Optional[int] = None
    consumo_origen_tipo: Optional[str] = None
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True