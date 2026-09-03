from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.cuentas_por_pagar import service, schemas

router = APIRouter(prefix="/cuentas-por-pagar", tags=["Cuentas por Pagar"], dependencies=[Depends(require_module('gastos'))])


@router.get("/", response_model=List[schemas.CuentaPorPagarResponse])
def listar_cuentas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    estado: Optional[str] = Query(None, description="PENDIENTE | PAGADA"),
    proveedor_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.obtener_cuentas(db, skip, limit, estado, proveedor_id, current_user)


@router.get("/resumen", response_model=schemas.ResumenCuentasPorPagar)
def resumen_cuentas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Saldo total pendiente + desglose por proveedor."""
    return service.obtener_resumen(db, current_user)


@router.post("/", response_model=schemas.CuentaPorPagarResponse, status_code=201)
def crear_cuenta(
    datos: schemas.CuentaPorPagarCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_cuenta(db, datos, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{cxp_id}/abonos", response_model=schemas.AbonoResponse, status_code=201)
def registrar_abono(
    cxp_id: int,
    abono: schemas.AbonoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        return service.abonar(db, cxp_id, abono, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/abonos/{abono_id}", status_code=204)
def eliminar_abono(
    abono_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        if not service.eliminar_abono(db, abono_id, current_user):
            raise HTTPException(status_code=404, detail="El abono no existe.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None


@router.delete("/{cxp_id}", status_code=204)
def eliminar_cuenta(
    cxp_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        if not service.eliminar_cuenta(db, cxp_id, current_user):
            raise HTTPException(status_code=404, detail="La cuenta por pagar no existe.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None