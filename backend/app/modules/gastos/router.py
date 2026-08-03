from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date
from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.gastos import service, schemas
from app.modules.gastos.model import Gasto
from app.modules.catalogos.model import TipoGasto

router = APIRouter(prefix="/gastos", tags=["Gastos"], dependencies=[Depends(require_module('gastos'))])

@router.post("/", response_model=schemas.GastoResponse, status_code=201)
def crear_gasto(
    gasto: schemas.GastoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.crear_gasto(db, gasto)

@router.get("/", response_model=List[schemas.GastoResponse])
def listar_gastos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tipo_gasto_id: Optional[int] = Query(None),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria: OPERATIVO, PASIVO, PRODUCCION"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.obtener_gastos(db, skip, limit, tipo_gasto_id, categoria, fecha_desde, fecha_hasta)

@router.get("/{gasto_id}", response_model=schemas.GastoResponse)
def obtener_gasto(
    gasto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_gasto = service.obtener_gasto(db, gasto_id)
    if not db_gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    return db_gasto

@router.put("/{gasto_id}", response_model=schemas.GastoResponse)
def actualizar_gasto(
    gasto_id: int,
    gasto_update: schemas.GastoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_gasto = service.actualizar_gasto(db, gasto_id, gasto_update)
    if not db_gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    return db_gasto

@router.delete("/{gasto_id}", status_code=204)
def eliminar_gasto(
    gasto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_gasto(db, gasto_id):
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    return None