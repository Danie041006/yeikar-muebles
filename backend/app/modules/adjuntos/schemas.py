from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AdjuntoInfo(BaseModel):
    """Representación ligera de un adjunto embebida en las respuestas de las
    entidades (Producto.fotos, Pago.recibos, Gasto.comprobantes...)."""

    id: int
    nombre: Optional[str] = None
    mime: str
    tamano: int
    url: Optional[str] = None  # Solo se llena para PRODUCTO (pública, para el PDF)


class AdjuntoResponse(BaseModel):
    id: int
    entidad_tipo: str
    entidad_id: int
    uuid: str
    nombre: Optional[str] = None
    mime: str
    tamano: int
    url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
