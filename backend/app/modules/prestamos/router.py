from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.prestamos import schemas, service
from app.modules.users.deps import require_module
from app.modules.users.model import Usuario
from app.modules.users.router import get_current_user

router = APIRouter(
    prefix="/prestamo",
    tags=["préstamos"],
    dependencies=[Depends(require_module("cuentas"))],
)


@router.get("/", response_model=List[schemas.PrestamoResponse])
def listar_prestamos(
    estado: Optional[str] = Query(None, description="PENDIENTE | PAGADO"),
    persona: Optional[str] = Query(None, description="Filtra por nombre de la persona"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Historial de préstamos con saldo y cobros, para el detalle en Cuentas."""
    return service.listar_prestamos(
        db,
        estado=estado,
        persona=persona,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@router.get("/pendientes", response_model=List[schemas.PendientePrestamo])
def prestamos_pendientes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Deudores con saldo (persona + moneda) para el selector de la entrada."""
    return service.pendientes(db)


@router.get("/resumen", response_model=schemas.ResumenPrestamos)
def resumen_prestamos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Total por cobrar, por moneda y por persona (tarjeta de Cuentas)."""
    return service.resumen(db)
