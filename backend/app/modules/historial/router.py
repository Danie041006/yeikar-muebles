"""historial/router.py — Endpoints del expediente digital (solo lectura).

Entradas: cotización, pedido, factura, envío o cliente. Todas devuelven la
ficha con la cadena completa. La auditoría interna solo viaja para
Dueño/Administrador.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.historial import service
from app.modules.users.deps import es_admin_user, require_module
from app.modules.users.model import Usuario
from app.modules.users.router import get_current_user

router = APIRouter(
    prefix="/historial",
    tags=["historial"],
    dependencies=[Depends(require_module("pedidos"))],
)


def _con_auditoria(usuario_actual: Usuario) -> bool:
    return es_admin_user(usuario_actual)


@router.get("/cotizacion/{cotizacion_id}")
def ficha_cotizacion(
    cotizacion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    ficha = service.expediente_cotizacion(db, cotizacion_id, incluir_auditoria=_con_auditoria(usuario_actual))
    if not ficha:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return ficha


@router.get("/pedido/{pedido_id}")
def ficha_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    ficha = service.cadena_expediente(db, pedido_id, incluir_auditoria=_con_auditoria(usuario_actual))
    if not ficha:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return ficha


@router.get("/factura/{factura_id}")
def ficha_factura(
    factura_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    ficha = service.expediente_factura(db, factura_id, incluir_auditoria=_con_auditoria(usuario_actual))
    if not ficha:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return ficha


@router.get("/envio/{envio_id}")
def ficha_envio(
    envio_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    ficha = service.expediente_envio(db, envio_id, incluir_auditoria=_con_auditoria(usuario_actual))
    if not ficha:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return ficha


@router.get("/cliente/{cliente_id}")
def ficha_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    ficha = service.expediente_cliente(db, cliente_id)
    if not ficha:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return ficha