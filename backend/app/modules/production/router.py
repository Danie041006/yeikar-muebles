from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.production import schemas, service

router = APIRouter(dependencies=[Depends(require_module('produccion'))])

# ------------------------------------------------------------
# Endpoints de Órdenes de Producción
# ------------------------------------------------------------
@router.post("/orden/", response_model=schemas.OrdenProduccionResponse, status_code=status.HTTP_201_CREATED)
def crear_orden(
    esquema: schemas.OrdenProduccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_orden_produccion(db, esquema, usuario_actual)

@router.post("/orden/desde-pedido/{detalle_pedido_id}", response_model=schemas.OrdenProduccionResponse, status_code=status.HTTP_201_CREATED)
def crear_orden_desde_pedido(
    detalle_pedido_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_orden_desde_detalle_pedido(db, detalle_pedido_id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Ya existe una orden de producción para este detalle de pedido")

@router.get("/orden/", response_model=List[schemas.OrdenProduccionResponse])
def listar_ordenes(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por estado, id de orden o id de detalle_pedido"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_ordenes_produccion(db, salto=salto, limite=limite, buscar=buscar, usuario=usuario_actual)

@router.get("/orden/{id}", response_model=schemas.OrdenProduccionResponse)
def ver_orden(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_orden_produccion(db, id, usuario_actual)
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
    db_obj = service.actualizar_orden_produccion(db, id, esquema, usuario_actual)
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
        db_obj = service.cambiar_estado_orden_produccion(db, id, estado, usuario_actual)
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
    exito = service.eliminar_orden_produccion(db, id, usuario_actual)
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
    try:
        return service.crear_etapa_produccion(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/etapa/{id}", response_model=schemas.EtapaProduccionResponse)
def ver_etapa(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_etapa_produccion(db, id, usuario_actual)
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
    db_obj = service.actualizar_etapa_produccion(db, id, esquema, usuario_actual)
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
        db_obj = service.cambiar_estado_etapa_produccion(db, id, estado, usuario_actual)
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
    exito = service.eliminar_etapa_produccion(db, id, usuario_actual)
    if not exito:
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
    return None


@router.post("/etapa/{id}/pasar-a-area", response_model=schemas.EtapaProduccionResponse, status_code=status.HTTP_201_CREATED)
def pasar_a_area(
    id: int,
    payload: schemas.PasarAAreaRequest,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Completa la etapa actual (COMPLETADA) y crea una nueva etapa en el área destino.
    Permite asignar un responsable principal y empleados adicionales opcionales.
    """
    from app.modules.catalogos.model import Area
    from app.modules.empleados.model import Empleado
    from app.modules.production.model import EtapaProduccion, EtapaAsignadoAdicional
    from datetime import datetime

    # FOR UPDATE: dos "pasar a área" simultáneos sobre la misma etapa se serializan;
    # el segundo re-lee la etapa ya COMPLETADA y recibe 400 en vez de duplicar la etapa.
    etapa_actual = db.query(EtapaProduccion).filter(EtapaProduccion.id == id).with_for_update().first()
    if not etapa_actual:
        raise HTTPException(status_code=404, detail="Etapa no encontrada")
    if etapa_actual.estado == "COMPLETADA":
        raise HTTPException(status_code=400, detail="La etapa ya esta completada")
    if etapa_actual.area_id == payload.area_id:
        raise HTTPException(status_code=400, detail="El area destino debe ser diferente al area actual")

    if not db.query(Area).filter(Area.id == payload.area_id).first():
        raise HTTPException(status_code=404, detail="Area destino no encontrada")
    if not db.query(Empleado).filter(Empleado.id == payload.empleado_responsable_id).first():
        raise HTTPException(status_code=404, detail="Responsable principal no encontrado")

    empleados_adicionales = list(dict.fromkeys(payload.empleados_adicionales_ids))
    if payload.empleado_responsable_id in empleados_adicionales:
        raise HTTPException(status_code=400, detail="El responsable principal no puede ser adicional")
    empleados_validos = db.query(Empleado.id).filter(Empleado.id.in_(empleados_adicionales)).all()
    if len(empleados_validos) != len(empleados_adicionales):
        raise HTTPException(status_code=404, detail="Uno o mas empleados adicionales no existen")

    # 1. Completar la etapa actual
    etapa_actual.estado = "COMPLETADA"
    etapa_actual.fecha_fin = datetime.utcnow()
    db.add(etapa_actual)

    # 2. Crear nueva etapa en el área destino
    nueva_etapa = EtapaProduccion(
        orden_produccion_id=etapa_actual.orden_produccion_id,
        area_id=payload.area_id,
        empleado_responsable_id=payload.empleado_responsable_id,
        estado="ASIGNADA",
        observaciones=payload.observaciones,
        fecha_inicio=datetime.utcnow(),
    )
    db.add(nueva_etapa)
    db.flush()  # obtener ID de la nueva etapa

    # 3. Asignar empleados adicionales (opcional)
    for emp_id in empleados_adicionales:
        adicional = EtapaAsignadoAdicional(
            etapa_produccion_id=nueva_etapa.id,
            empleado_id=emp_id,
        )
        db.add(adicional)

    db.commit()
    db.refresh(nueva_etapa)
    return nueva_etapa


@router.post("/etapa/{id}/asignados", response_model=schemas.AsignadoAdicionalResponse, status_code=status.HTTP_201_CREATED)
def agregar_asignado_adicional(
    id: int,
    esquema: schemas.AsignadoAdicionalCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    from app.modules.empleados.model import Empleado
    from app.modules.production.model import EtapaAsignadoAdicional, EtapaProduccion

    etapa = db.query(EtapaProduccion).filter(EtapaProduccion.id == id).first()
    if not etapa:
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")
    empleado = db.query(Empleado).filter(Empleado.id == esquema.empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if etapa.empleado_responsable_id == esquema.empleado_id:
        raise HTTPException(status_code=400, detail="El responsable principal no puede ser asignado como adicional")

    existente = db.query(EtapaAsignadoAdicional).filter(
        EtapaAsignadoAdicional.etapa_produccion_id == id,
        EtapaAsignadoAdicional.empleado_id == esquema.empleado_id,
    ).first()
    if existente:
        raise HTTPException(status_code=409, detail="El empleado ya esta asignado a esta etapa")

    asignado = EtapaAsignadoAdicional(etapa_produccion_id=id, empleado_id=esquema.empleado_id)
    db.add(asignado)
    db.commit()
    db.refresh(asignado)
    return asignado


@router.delete("/etapa/{id}/asignados/{empleado_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_asignado_adicional(
    id: int,
    empleado_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    from app.modules.production.model import EtapaAsignadoAdicional

    asignado = db.query(EtapaAsignadoAdicional).filter(
        EtapaAsignadoAdicional.etapa_produccion_id == id,
        EtapaAsignadoAdicional.empleado_id == empleado_id,
    ).first()
    if not asignado:
        raise HTTPException(status_code=404, detail="Asignado adicional no encontrado")
    db.delete(asignado)
    db.commit()
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

@router.get("/etapa/{id}/referencia-receta", response_model=schemas.ReferenciaRecetaResponse)
def referencia_receta(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Retorna la receta del producto asociado a la etapa como referencia visual.
    Cada material incluye su seccion, cantidad_base y costo_unitario.
    """
    from app.modules.production.service import obtener_referencia_receta

    data = obtener_referencia_receta(db, id)
    if not data:
        raise HTTPException(status_code=404, detail="No se encontró receta de referencia para esta etapa")
    return data


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
    except IntegrityError:
        raise HTTPException(status_code=409, detail="El costo de producción ya está siendo calculado por otra operación")

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
