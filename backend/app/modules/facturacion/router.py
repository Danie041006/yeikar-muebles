from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module, es_admin
from app.modules.facturacion import schemas, service

router = APIRouter(dependencies=[Depends(require_module('facturacion'))])


@router.post("/", response_model=schemas.FacturaResponse, status_code=status.HTTP_201_CREATED)
def crear_factura(
    esquema: schemas.FacturaCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_factura_desde_pedido(db, esquema, usuario=usuario_actual)
    except service.FacturaNoAutorizadaError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[schemas.FacturaResponse])
def listar_facturas(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    return service.obtener_facturas(db, usuario=usuario_actual)


@router.get("/pedidos-facturables/", response_model=List[schemas.PedidoFacturableResponse])
def listar_pedidos_facturables(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    return service.pedidos_facturables(db, usuario=usuario_actual)


@router.get("/tasas/", response_model=List[schemas.TasaImpuestoResponse])
def listar_tasas(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    return service.listar_tasas_impuesto(db)


@router.put("/tasas/{clave}", response_model=schemas.TasaImpuestoResponse)
def actualizar_tasa(
    clave: str,
    esquema: schemas.TasaImpuestoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(es_admin),
):
    try:
        return service.actualizar_tasa_impuesto(db, clave, esquema, usuario=usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{id}", response_model=schemas.FacturaDetalleResponse)
def ver_factura(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    db_obj = service.obtener_factura(db, id, usuario_actual)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return db_obj


@router.post("/{id}/anular", response_model=schemas.FacturaResponse)
def anular_factura(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    try:
        db_obj = service.anular_factura(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_obj:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return db_obj
