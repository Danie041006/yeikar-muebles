from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.production import schemas, service

router = APIRouter()

# ------------------------------------------------------------
# Endpoints de Órdenes de Producción
# ------------------------------------------------------------
@router.post("/orden/", response_model=schemas.OrdenProduccionResponse, status_code=status.HTTP_201_CREATED)
def crear_orden(
    esquema: schemas.OrdenProduccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_orden_produccion(db, esquema)

@router.post("/orden/desde-pedido/{detalle_pedido_id}", response_model=schemas.OrdenProduccionResponse, status_code=status.HTTP_201_CREATED)
def crear_orden_desde_pedido(
    detalle_pedido_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_orden_desde_detalle_pedido(db, detalle_pedido_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/orden/", response_model=List[schemas.OrdenProduccionResponse])
def listar_ordenes(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por estado, id de orden o id de detalle_pedido"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_ordenes_produccion(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/orden/{id}", response_model=schemas.OrdenProduccionResponse)
def ver_orden(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_orden_produccion(db, id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Orden de produccion no encontrada")
    return db_obj

@router.put("/orden/{id}", response_model=schemas.OrdenProduccionResponse)
def actualizar_orden(
    id: int,
    esquema: schemas.OrdenProduccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_orden_produccion(db, id, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Orden de produccion no encontrada")
    return db_obj

@router.put("/orden/{id}/estado", response_model=schemas.OrdenProduccionResponse)
def cambiar_estado_orden(
    id: int,
    estado: str = Query(..., description="Nuevo estado de la orden (PENDIENTE, EN_PRODUCCION, PAUSADA, FINALIZADA, CANCELADA)"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        db_obj = service.cambiar_estado_orden_produccion(db, id, estado)
        if not db_obj:
            raise HTTPException(status_code=404, detail="Orden de produccion no encontrada")
        return db_obj
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/orden/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_orden(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_orden_produccion(db, id)
    if not exito:
        raise HTTPException(status_code=404, detail="Orden de produccion no encontrada")
    return None


# ------------------------------------------------------------
# Endpoints de Etapas de Producción
# ------------------------------------------------------------
@router.post("/etapa/", response_model=schemas.EtapaProduccionResponse, status_code=status.HTTP_201_CREATED)
def crear_etapa(
    esquema: schemas.EtapaProduccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_etapa_produccion(db, esquema)

@router.get("/etapa/{id}", response_model=schemas.EtapaProduccionResponse)
def ver_etapa(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_etapa_produccion(db, id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
    return db_obj

@router.put("/etapa/{id}", response_model=schemas.EtapaProduccionResponse)
def actualizar_etapa(
    id: int,
    esquema: schemas.EtapaProduccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_etapa_produccion(db, id, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
    return db_obj

@router.put("/etapa/{id}/estado", response_model=schemas.EtapaProduccionResponse)
def cambiar_estado_etapa(
    id: int,
    estado: str = Query(..., description="Nuevo estado de la etapa (ASIGNADA, EN_PROCESO, PAUSADA, COMPLETADA)"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        db_obj = service.cambiar_estado_etapa_produccion(db, id, estado)
        if not db_obj:
            raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
        return db_obj
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/etapa/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_etapa(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_etapa_produccion(db, id)
    if not exito:
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
    return None


# ------------------------------------------------------------
# Endpoints de Consumo de Material
# ------------------------------------------------------------
@router.post("/consumo/", response_model=schemas.ConsumoMaterialResponse, status_code=status.HTTP_201_CREATED)
def registrar_consumo(
    esquema: schemas.ConsumoMaterialCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_consumo_material(db, esquema)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/consumo/por-orden/{orden_id}", response_model=List[schemas.ConsumoMaterialResponse])
def listar_consumos_por_orden(
    orden_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_consumos_por_orden(db, orden_id)

@router.delete("/consumo/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_consumo(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_consumo_material(db, id)
    if not exito:
        raise HTTPException(status_code=404, detail="Consumo de material no encontrado")
    return None


# ------------------------------------------------------------
# Endpoints de Mano de Obra
# ------------------------------------------------------------
@router.post("/mano-obra/", response_model=schemas.ManoObraResponse, status_code=status.HTTP_201_CREATED)
def registrar_mano_obra(
    esquema: schemas.ManoObraCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_mano_obra(db, esquema)

@router.delete("/mano-obra/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_mano_obra(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_mano_obra(db, id)
    if not exito:
        raise HTTPException(status_code=404, detail="Mano de obra no encontrada")
    return None

@router.put("/mano-obra/{id}/pagar", response_model=schemas.ManoObraResponse)
def marcar_mano_obra_pagada(
    id: int,
    pagado: bool = True,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Marca un registro de mano de obra como pagado (efectiviza el egreso en caja)."""
    db_mano = service.marcar_mano_obra_pagada(db, id, pagado)
    if not db_mano:
        raise HTTPException(status_code=404, detail="Mano de obra no encontrada")
    return db_mano


# ------------------------------------------------------------
# Endpoints de Costos de Producción
# ------------------------------------------------------------
@router.post("/costo/calcular/{orden_id}", response_model=schemas.CostoProduccionResponse)
def calcular_costo(
    orden_id: int,
    esquema: schemas.CostoProduccionCreate = Body(default_factory=schemas.CostoProduccionCreate),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.calcular_y_guardar_costo(
            db,
            orden_id,
            ganancia_porcentaje=esquema.ganancia_porcentaje,
            costo_gastos=esquema.costo_gastos,
            precio_impuestos_base=esquema.precio_impuestos_base
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/costo/{orden_id}", response_model=schemas.CostoProduccionResponse)
def ver_costo(
    orden_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_costo_por_orden(db, orden_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Costo de produccion no encontrado para esta orden")
    return db_obj
