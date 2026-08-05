from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.quotes import schemas, service

router = APIRouter(dependencies=[Depends(require_module('cotizaciones'))])

@router.post("/", response_model=schemas.CotizacionResponse, status_code=status.HTTP_201_CREATED)
def crear_cotizacion(
    esquema: schemas.CotizacionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_cotizacion(db, esquema)

@router.get("/", response_model=List[schemas.CotizacionResponse])
def listar_cotizaciones(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por observaciones, estado o cliente"),
    solo_mes_actual: bool = Query(True, description="Filtrar solo cotizaciones del mes actual"),
    mes: Optional[int] = Query(None, ge=1, le=12, description="Filtrar por mes específico"),
    anio: Optional[int] = Query(None, ge=2000, le=2100, description="Filtrar por año específico"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_cotizaciones(
        db, salto=salto, limite=limite, buscar=buscar,
        solo_mes_actual=solo_mes_actual, mes=mes, anio=anio
    )

@router.get("/{id_cotizacion}", response_model=schemas.CotizacionResponse)
def ver_cotizacion(
    id_cotizacion: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_cotizacion(db, id_cotizacion)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return db_obj

@router.put("/{id_cotizacion}", response_model=schemas.CotizacionResponse)
def actualizar_cotizacion(
    id_cotizacion: int,
    esquema: schemas.CotizacionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        db_obj = service.actualizar_cotizacion(db, id_cotizacion, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_obj:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
    return db_obj

@router.delete("/{id_cotizacion}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cotizacion(
    id_cotizacion: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_cotizacion(db, id_cotizacion)
        if not exito:
            raise HTTPException(status_code=404, detail="Cotizacion no encontrada")
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

