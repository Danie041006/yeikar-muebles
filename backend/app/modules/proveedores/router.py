from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.proveedores import schemas, service

router = APIRouter()

@router.post("/", response_model=schemas.ProveedorResponse, status_code=status.HTTP_201_CREATED)
def crear_proveedor(
    esquema: schemas.ProveedorCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_proveedor(db, esquema)

@router.get("/", response_model=List[schemas.ProveedorResponse])
def listar_proveedores(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre, email o telefono"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_proveedores(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/{id_proveedor}", response_model=schemas.ProveedorResponse)
def ver_proveedor(
    id_proveedor: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_proveedor(db, id_proveedor)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return db_obj

@router.put("/{id_proveedor}", response_model=schemas.ProveedorResponse)
def actualizar_proveedor(
    id_proveedor: int,
    esquema: schemas.ProveedorUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_proveedor(db, id_proveedor, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return db_obj

@router.delete("/{id_proveedor}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_proveedor(
    id_proveedor: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_proveedor(db, id_proveedor)
    if not exito:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return None
