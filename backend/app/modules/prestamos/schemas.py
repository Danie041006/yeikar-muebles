from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.modules.catalogos.schemas import MonedaResponse


class CobroPrestamoCreate(BaseModel):
    """Cobro de un préstamo registrado como ENTRADA de caja.

    Viaja dentro del alta de un movimiento de caja: la entrada y el abono al
    préstamo se crean en la misma transacción (una sola operación).
    """

    # Persona a la que se le cobra (debe coincidir con un préstamo pendiente).
    persona_nombre: str = Field(..., min_length=1, max_length=150)
    # Moneda del préstamo (el monto se expresa en esta moneda).
    moneda_id: int
    # Monto cobrado EN LA MONEDA DEL PRÉSTAMO (puede ser parcial).
    monto: Decimal = Field(..., gt=0)
    # "1 [moneda del préstamo] = X [moneda de la cuenta]". Obligatoria solo si
    # la cuenta donde entra el dinero tiene otra moneda.
    tasa_conversion: Optional[Decimal] = Field(None, gt=0)


class PagoPrestamoResponse(BaseModel):
    id: int
    prestamo_id: int
    fecha: date
    monto: Decimal
    metodo_caja_id: int
    metodo_caja_nombre: Optional[str] = None
    moneda_cuenta_id: int
    moneda_cuenta_codigo: Optional[str] = None
    tasa_conversion: Decimal = Decimal("1.0")
    monto_en_moneda_cuenta: Decimal
    monto_en_moneda_base: Decimal
    movimiento_caja_id: Optional[int] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PrestamoResponse(BaseModel):
    id: int
    persona_nombre: str
    fecha: date
    moneda_id: int
    monto: Decimal
    tasa_cambio: Decimal = Decimal("1.0")
    monto_en_moneda_base: Decimal
    monto_abonado: Decimal
    saldo: Decimal
    estado: str
    metodo_caja_id: Optional[int] = None
    movimiento_caja_id: Optional[int] = None
    observaciones: Optional[str] = None
    creado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    moneda: Optional[MonedaResponse] = None
    pagos: List[PagoPrestamoResponse] = []

    class Config:
        from_attributes = True


class PendientePrestamo(BaseModel):
    """Fila del selector "¿a quién le estás cobrando?" en la entrada de caja.

    Agrupa por persona + moneda: es exactamente lo que la dueña ve como
    "Fulano debe tanto".
    """

    persona_nombre: str
    moneda_id: int
    moneda_codigo: str
    moneda_simbolo: Optional[str] = None
    saldo: Decimal
    prestamos: int
    ultima_fecha: Optional[date] = None


class TotalPrestamosMoneda(BaseModel):
    moneda_id: int
    moneda_codigo: str
    moneda_simbolo: Optional[str] = None
    total_prestado: Decimal
    total_cobrado: Decimal
    saldo: Decimal


class ResumenPrestamos(BaseModel):
    personas_con_saldo: int
    por_moneda: List[TotalPrestamosMoneda] = []
    por_persona: List[PendientePrestamo] = []
