from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.envios import schemas, service
from app.modules.users.deps import require_module, tiene_alcance_total
from app.modules.users.model import Usuario
from app.modules.users.router import get_current_user

router = APIRouter(dependencies=[Depends(require_module("envios"))])


def _serialize_envio(envio, usuario: Usuario):
    """Drivers receive a redacted DTO; owners can receive the operational detail."""
    if tiene_alcance_total(usuario):
        return jsonable_encoder(schemas.EnvioResponse.model_validate(envio))
    return jsonable_encoder(schemas.EnvioRepartoResponse.model_validate(envio))


@router.post("/", response_model=None, status_code=status.HTTP_201_CREATED)
def crear_envio(
    esquema: schemas.EnvioCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        envio = service.crear_envio(db, esquema, usuario_actual)
        return _serialize_envio(envio, usuario_actual)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Ya existe un envío registrado para este pedido")


@router.get("/mis-asignaciones", response_model=List[schemas.EnvioRepartoResponse])
def listar_mis_asignaciones(
    estado: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    if tiene_alcance_total(usuario_actual):
        raise HTTPException(status_code=400, detail="Este endpoint es exclusivo para repartidores asignados.")
    envios = service.obtener_envios(db, limite=500, estado=estado, usuario=usuario_actual)
    return envios


@router.get("/", response_model=None)
def listar_envios(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por cliente, guia, direccion u observaciones"),
    estado: Optional[str] = Query(None, description="PREPARADO, EN_TRANSITO, ENTREGADO, FALLIDO"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    envios = service.obtener_envios(
        db,
        salto=salto,
        limite=limite,
        buscar=buscar,
        estado=estado,
        usuario=usuario_actual,
    )
    return [_serialize_envio(envio, usuario_actual) for envio in envios]


@router.post("/{id}/ubicaciones", response_model=schemas.EnvioUbicacionResponse, status_code=status.HTTP_201_CREATED)
def registrar_ubicacion(
    id: int,
    datos: schemas.EnvioUbicacionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        return service.registrar_ubicacion(db, id, datos, usuario_actual)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{id}/ubicaciones", response_model=List[schemas.EnvioUbicacionResponse])
def listar_ubicaciones(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    envio, ubicaciones = service.obtener_ubicaciones(db, id, usuario_actual)
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return ubicaciones


@router.get("/{id}/ubicacion-actual", response_model=Optional[schemas.EnvioUbicacionResponse])
def obtener_ubicacion_actual(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    envio, ubicaciones = service.obtener_ubicaciones(db, id, usuario_actual)
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return ubicaciones[0] if ubicaciones else None


@router.get("/{id}", response_model=None)
def ver_envio(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    envio = service.obtener_envio(db, id, usuario_actual)
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return _serialize_envio(envio, usuario_actual)


@router.put("/{id}", response_model=None)
def actualizar_envio(
    id: int,
    esquema: schemas.EnvioUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        envio = service.actualizar_envio(db, id, esquema, usuario_actual)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return _serialize_envio(envio, usuario_actual)


@router.put("/{id}/estado", response_model=None)
def cambiar_estado_envio(
    id: int,
    estado: str = Query(..., description="PREPARADO, EN_TRANSITO, ENTREGADO, FALLIDO"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    estados_validos = ["PREPARADO", "EN_TRANSITO", "ENTREGADO", "FALLIDO"]
    if estado not in estados_validos:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Debe ser uno de: {estados_validos}")
    try:
        envio = service.actualizar_envio(db, id, schemas.EnvioUpdate(estado=estado), usuario_actual)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return _serialize_envio(envio, usuario_actual)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_envio(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        exito = service.eliminar_envio(db, id, usuario_actual)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not exito:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return None
