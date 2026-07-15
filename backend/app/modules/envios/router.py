from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.envios import schemas, service
router = APIRouter()
@router.post("/", response_model=schemas.EnvioResponse, status_code=status.HTTP_201_CREATED)
def crear_envio(
    esquema: schemas.EnvioCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_envio(db, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/", response_model=List[schemas.EnvioResponse])
def listar_envios(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por cliente, guia, direccion u observaciones"),
    estado: Optional[str] = Query(None, description="Filtrar por estado (PREPARADO, EN_TRANSITO, ENTREGADO, FALLIDO)"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_envios(db, salto=salto, limite=limite, buscar=buscar, estado=estado)
@router.get("/{id}", response_model=schemas.EnvioResponse)
def ver_envio(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_envio(db, id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return db_obj
@router.put("/{id}", response_model=schemas.EnvioResponse)
def actualizar_envio(
    id: int,
    esquema: schemas.EnvioUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_envio(db, id, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return db_obj
@router.put("/{id}/estado", response_model=schemas.EnvioResponse)
def cambiar_estado_envio(
    id: int,
    estado: str = Query(..., description="Nuevo estado del envío (PREPARADO, EN_TRANSITO, ENTREGADO, FALLIDO)"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    # Validar estado
    estados_validos = ["PREPARADO", "EN_TRANSITO", "ENTREGADO", "FALLIDO"]
    if estado not in estados_validos:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Debe ser uno de: {estados_validos}")
        
    esquema = schemas.EnvioUpdate(estado=estado)
    db_obj = service.actualizar_envio(db, id, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return db_obj
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_envio(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_envio(db, id)
    if not exito:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return None
