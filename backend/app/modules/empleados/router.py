from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.empleados import schemas, service

router = APIRouter()

@router.post("/", response_model=schemas.EmpleadoResponse, status_code=status.HTTP_201_CREATED)
def crear_empleado(
    esquema: schemas.EmpleadoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_empleado(db, esquema)

@router.get("/", response_model=List[schemas.EmpleadoResponse])
def listar_empleados(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre o telefono"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_empleados(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/{id_empleado}", response_model=schemas.EmpleadoResponse)
def ver_empleado(
    id_empleado: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_empleado(db, id_empleado)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return db_obj

@router.put("/{id_empleado}", response_model=schemas.EmpleadoResponse)
def actualizar_empleado(
    id_empleado: int,
    esquema: schemas.EmpleadoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_empleado(db, id_empleado, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return db_obj

@router.delete("/{id_empleado}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_empleado(
    id_empleado: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_empleado(db, id_empleado)
    if not exito:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return None
