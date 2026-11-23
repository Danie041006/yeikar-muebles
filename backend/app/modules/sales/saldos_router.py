from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.sales import saldos_service
from app.modules.sales.saldos_schemas import AplicarSaldoCreate, SaldoFavorResponse
from app.modules.sales.schemas import PagoResponse
from app.modules.users.deps import require_module
from app.modules.users.model import Usuario
from app.modules.users.router import get_current_user

router = APIRouter(prefix="/saldo-favor", tags=["saldos a favor"],
                   dependencies=[Depends(require_module("ventas"))])


@router.get("/", response_model=list[SaldoFavorResponse])
def listar(
    cliente_id: int | None = None, salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
):
    return saldos_service.listar_saldos(db, cliente_id, salto, limite)


@router.post("/aplicar", response_model=PagoResponse, status_code=201)
def aplicar(
    esquema: AplicarSaldoCreate, db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return saldos_service.aplicar_saldo(db, esquema, usuario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
