from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.reports import service, schemas

router = APIRouter(prefix="/cuenta", tags=["cuentas"], dependencies=[Depends(require_module('cuentas'))])


# ------------------------------------------------------------
# Resumen de cuentas con saldo por moneda y en COP
# ------------------------------------------------------------
@router.get("/", response_model=List[schemas.ResumenCuentaResponse])
@router.get("/resumen", response_model=List[schemas.ResumenCuentaResponse])
def get_resumen_cuentas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.resumen_cuentas(db)


# ------------------------------------------------------------
# CRUD de cuentas (medios de pago / caja)
# ------------------------------------------------------------
@router.post("/", response_model=schemas.MetodoCajaResponse, status_code=201)
def post_cuenta(
    esquema: schemas.MetodoCajaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.crear_metodo_caja(db, esquema)


@router.put("/{metodo_id}", response_model=schemas.MetodoCajaResponse)
def put_cuenta(
    metodo_id: int,
    esquema: schemas.MetodoCajaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    obj = service.actualizar_metodo_caja(db, metodo_id, esquema)
    if not obj:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    return obj


@router.delete("/{metodo_id}", status_code=204)
def delete_cuenta(
    metodo_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        if not service.eliminar_metodo_caja(db, metodo_id):
            raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return None


# ------------------------------------------------------------
# Movimientos de una cuenta
# ------------------------------------------------------------
@router.get("/movimientos", response_model=List[schemas.MovimientoCajaResponse])
def get_movimientos_cuenta(
    metodo_caja_id: Optional[int] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_movimientos_caja(db, metodo_caja_id, fecha_desde, fecha_hasta)


@router.post("/{metodo_id}/movimiento", response_model=schemas.MovimientoCajaResponse, status_code=201)
def post_movimiento_cuenta(
    metodo_id: int,
    esquema: schemas.MovimientoCajaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if esquema.metodo_caja_id != metodo_id:
        raise HTTPException(status_code=400, detail="El método de caja de la URL no coincide con el del cuerpo")
    return service.crear_movimiento_caja(db, esquema, usuario_id=current_user.id)


# ------------------------------------------------------------
# Transferencias entre cuentas
# ------------------------------------------------------------
@router.post("/transferencia", response_model=schemas.TransferenciaResponse, status_code=201)
def post_transferencia(
    esquema: schemas.TransferenciaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_transferencia(db, esquema, usuario_id=current_user.id)
    except service.SaldoInsuficienteError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/transferencias", response_model=List[schemas.TransferenciaResponse])
def get_transferencias(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_transferencias(db, fecha_desde, fecha_hasta)


@router.put("/movimiento/{movimiento_id}", response_model=schemas.MovimientoCajaResponse)
def put_movimiento_cuenta(
    movimiento_id: int,
    esquema: schemas.MovimientoCajaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    obj = service.actualizar_movimiento_caja(db, movimiento_id, esquema)
    if not obj:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    return obj


@router.delete("/movimiento/{movimiento_id}", status_code=204)
def delete_movimiento_cuenta(
    movimiento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_movimiento_caja(db, movimiento_id):
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    return None