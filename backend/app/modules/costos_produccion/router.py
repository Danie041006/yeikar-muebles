from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.costos_produccion import service, schemas

router = APIRouter(
    prefix="/costo-produccion",
    tags=["Costos de Producción"],
    dependencies=[Depends(require_module('costos_produccion'))],
)

@router.get("/", response_model=List[schemas.PrecioProduccionResponse])
def listar_precios(
    area_id: Optional[int] = Query(None, description="Filtrar por área (id)"),
    buscar: Optional[str] = Query(None, description="Búsqueda por descripción"),
    activo: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return service.listar_precios(db, area_id=area_id, buscar=buscar, activo=activo, skip=skip, limit=limit)

@router.post("/", response_model=schemas.PrecioProduccionResponse, status_code=201)
def crear_precio(
    esquema: schemas.PrecioProduccionCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_precio(db, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{precio_id}", response_model=schemas.PrecioProduccionResponse)
def actualizar_precio(
    precio_id: int,
    esquema: schemas.PrecioProduccionUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        obj = service.actualizar_precio(db, precio_id, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not obj:
        raise HTTPException(status_code=404, detail="Precio de producción no encontrado")
    return obj

@router.delete("/{precio_id}", status_code=204)
def eliminar_precio(
    precio_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if not service.eliminar_precio(db, precio_id):
        raise HTTPException(status_code=404, detail="Precio de producción no encontrado")
    return None
