from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CambioSync(BaseModel):
    cursor: int
    tabla: str
    pk: str
    op: str
    ocurrido_en: datetime


class CambiosResponse(BaseModel):
    cambios: List[CambioSync]
    cursor: int
    hay_mas: bool


class OperacionPush(BaseModel):
    operacion_id: UUID
    tipo: str = Field(min_length=1, max_length=120)
    payload: Dict[str, Any] = Field(default_factory=dict)
    ocurrida_en: Optional[datetime] = None


class PushRequest(BaseModel):
    operaciones: List[OperacionPush] = Field(min_length=1, max_length=200)


class ResultadoPush(BaseModel):
    operacion_id: UUID
    estado: Literal["ok", "conflicto", "error", "en_proceso"]
    detalle: Optional[str] = None
    entidad: Optional[Dict[str, Any]] = None
    resultado: Optional[Dict[str, Any]] = None


class PushResponse(BaseModel):
    resultados: List[ResultadoPush]
