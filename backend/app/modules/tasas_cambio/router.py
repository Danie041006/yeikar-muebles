from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.tasas_cambio import service, schemas

router = APIRouter(prefix="/tasas-cambio", tags=["Tasas de Cambio"], dependencies=[Depends(require_module('tasas'))])

@router.post("/", response_model=schemas.TasaCambioResponse, status_code=201)
def crear_tasa(
    tasa: schemas.TasaCambioCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_tasa(db, tasa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.TasaCambioResponse])
def listar_tasas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    moneda_origen_id: Optional[int] = Query(None),
    moneda_destino_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_tasas(db, skip, limit, moneda_origen_id, moneda_destino_id)

@router.get("/{tasa_id}", response_model=schemas.TasaCambioResponse)
def obtener_tasa(
    tasa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_tasa = service.obtener_tasa(db, tasa_id)
    if not db_tasa:
        raise HTTPException(status_code=404, detail="Tasa de cambio no encontrada")
    return db_tasa

@router.get("/ultima/", response_model=schemas.TasaCambioResponse)
def obtener_ultima_tasa(
    moneda_origen_id: int = Query(...),
    moneda_destino_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    tasa = service.obtener_ultima_tasa(db, moneda_origen_id, moneda_destino_id)
    if not tasa:
        raise HTTPException(status_code=404, detail="No hay tasa registrada para ese par")
    return tasa

@router.delete("/{tasa_id}", status_code=204)
def eliminar_tasa(
    tasa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_tasa(db, tasa_id):
        raise HTTPException(status_code=404, detail="Tasa de cambio no encontrada")
    return None