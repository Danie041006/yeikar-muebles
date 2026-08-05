from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.orders import schemas, service

router = APIRouter(dependencies=[Depends(require_module('pedidos'))])

@router.post("/", response_model=schemas.PedidoResponse, status_code=status.HTTP_201_CREATED)
def crear_pedido(
    esquema: schemas.PedidoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_pedido(db, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.PedidoResponse])
def listar_pedidos(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por estado, observaciones o nombre de cliente"),
    solo_mes_actual: bool = Query(True, description="Filtrar solo pedidos del mes actual"),
    mes: Optional[int] = Query(None, ge=1, le=12, description="Filtrar por mes específico"),
    anio: Optional[int] = Query(None, ge=2000, le=2100, description="Filtrar por año específico"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_pedidos(
        db, salto=salto, limite=limite, buscar=buscar,
        solo_mes_actual=solo_mes_actual, mes=mes, anio=anio
    )

@router.get("/{id_pedido}", response_model=schemas.PedidoResponse)
def ver_pedido(
    id_pedido: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_pedido(db, id_pedido)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return db_obj

@router.put("/{id_pedido}", response_model=schemas.PedidoResponse)
def actualizar_pedido(
    id_pedido: int,
    esquema: schemas.PedidoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_pedido(db, id_pedido, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return db_obj

@router.delete("/{id_pedido}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_pedido(
    id_pedido: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_pedido(db, id_pedido)
    if not exito:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return None

@router.post("/convertir/{id_cotizacion}", response_model=schemas.PedidoResponse, status_code=status.HTTP_201_CREATED)
def convertir_cotizacion_a_pedido(
    id_cotizacion: int,
    body: schemas.ConvertirCotizacionBody,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    from datetime import date as fecha_tipo
    fecha_entrega = None
    if body.fecha_entrega_estimada:
        try:
            fecha_entrega = fecha_tipo.fromisoformat(body.fecha_entrega_estimada)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha invalido, use YYYY-MM-DD")

    detalles_dict = [d.model_dump() for d in body.detalles]
    try:
        return service.convertir_cotizacion_a_pedido(
            db,
            id_cotizacion,
            fecha_entrega,
            detalles_dict,
            adelanto=body.adelanto,
            moneda_adelanto_id=body.moneda_adelanto_id,
            tasa_cambio_adelanto=body.tasa_cambio_adelanto,
            metodo_pago=body.metodo_pago,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="La cotización ya fue convertida a pedido")
