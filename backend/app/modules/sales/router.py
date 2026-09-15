from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.sales import schemas, service

router = APIRouter(dependencies=[Depends(require_module('ventas'))])
pago_router = APIRouter(dependencies=[Depends(require_module('ventas'))])

# ------------------------------------------------------------
# Endpoints de Ventas (Facturas)
# ------------------------------------------------------------
@router.post("/", response_model=schemas.VentaResponse, status_code=status.HTTP_201_CREATED)
def crear_factura_venta(
    esquema: schemas.VentaCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_venta_desde_pedido(db, esquema, usuario=usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.VentaResponse])
def listar_facturas_venta(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por estado, observaciones o nombre de cliente"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_ventas(db, salto=salto, limite=limite, buscar=buscar, usuario=usuario_actual)

@router.get("/cuentas-por-cobrar/", response_model=List[schemas.CuentaPorCobrarResponse])
def listar_cuentas_por_cobrar(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_cuentas_por_cobrar(db)

@router.get("/{id}", response_model=schemas.VentaDetalleResponse)
def ver_factura_venta(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_venta(db, id, usuario_actual)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Factura de venta no encontrada")
    
    # Calcular y asignar campos acumulados para la respuesta
    # Usar monto_en_moneda_base para reflejar correctamente abonos en otra moneda
    total_pagado = sum(float(p.monto_en_moneda_base) for p in db_obj.pagos)
    total_descontado = sum(float(d.monto_en_moneda_base) for d in db_obj.descuentos)
    db_obj.total_pagado = total_pagado
    db_obj.total_descontado = total_descontado
    db_obj.saldo_pendiente = float(db_obj.total) - total_pagado - total_descontado
    return db_obj

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_factura_venta(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_venta(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Factura de venta no encontrada")
    return None


# ------------------------------------------------------------
# Endpoints de Pagos (Abonos)
# ------------------------------------------------------------
@pago_router.post("/", response_model=schemas.PagoResponse, status_code=status.HTTP_201_CREATED)
def registrar_pago(
    esquema: schemas.PagoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_pago(db, esquema, usuario=usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------
# Endpoints de Descuentos de cobro (rebaja sin movimiento de caja)
# ------------------------------------------------------------
@pago_router.post("/descuento/", response_model=schemas.DescuentoResponse, status_code=status.HTTP_201_CREATED)
def registrar_descuento(
    esquema: schemas.DescuentoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_descuento(db, esquema, usuario=usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@pago_router.delete("/descuento/{id}", status_code=status.HTTP_204_NO_CONTENT)
def anular_descuento(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.anular_descuento(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")
    return None
