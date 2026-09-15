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
    try:
        return service.crear_orden_produccion(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@router.get("/orden/{id}/costos-en-vivo")
def costos_en_vivo(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Desglose de costos EN VIVO de la orden (vista estilo Excel por sección):
    insumos + producción (con recargo) + gastos de sección. Se usa durante la
    producción, mientras se registran consumos y mano de obra."""
    data = service.costos_en_vivo_orden(db, id, usuario_actual)
    if not data:
        raise HTTPException(status_code=404, detail="Orden de produccion no encontrada")
    return data

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
    try:
        exito = service.eliminar_orden_produccion(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    try:
        exito = service.eliminar_etapa_produccion(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    from app.modules.production.service import _scope_stages
    from datetime import datetime

    # FOR UPDATE: dos "pasar a área" simultáneos sobre la misma etapa se serializan;
    # el segundo re-lee la etapa ya COMPLETADA y recibe 400 en vez de duplicar la etapa.
    # Además se respeta el alcance por creador (igual que el resto del módulo).
    etapa_actual = _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == id),
        usuario_actual,
    ).with_for_update().first()
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

    # Misma regla que crear_etapa: NO se puede tener dos etapas activas de la
    # misma área en la misma orden (dos activas = doble consumo/mano de obra y
    # doble pago destajo). El retrabajo se modela DESPUÉS de completar la anterior.
    activa_destino = db.query(EtapaProduccion).filter(
        EtapaProduccion.orden_produccion_id == etapa_actual.orden_produccion_id,
        EtapaProduccion.area_id == payload.area_id,
        EtapaProduccion.estado.in_(["ASIGNADA", "EN_PROCESO", "PAUSADA"]),
    ).first()
    if activa_destino:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El área destino ya tiene una etapa activa (etapa #{activa_destino.id}). "
                "Complete esa etapa antes de pasar trabajo a esa área."
            ),
        )

    empleados_adicionales = list(dict.fromkeys(payload.empleados_adicionales_ids))
    if payload.empleado_responsable_id in empleados_adicionales:
        raise HTTPException(status_code=400, detail="El responsable principal no puede ser adicional")
    empleados_validos = db.query(Empleado.id).filter(Empleado.id.in_(empleados_adicionales)).all()
    if len(empleados_validos) != len(empleados_adicionales):
        raise HTTPException(status_code=404, detail="Uno o mas empleados adicionales no existen")

    # 1. Completar la etapa actual (fecha local, consistente con cambiar_estado:
    #    antes se usaba utcnow() y una etapa completada de noche caía fuera del
    #    período de nómina destajo).
    etapa_actual.estado = "COMPLETADA"
    etapa_actual.fecha_fin = datetime.now()
    db.add(etapa_actual)

    # 2. Crear nueva etapa en el área destino. Si esa área ya tiene una etapa
    #    COMPLETADA para esta orden, la nueva etapa es retrabajo (no paga destajo).
    ya_completada_destino = db.query(EtapaProduccion).filter(
        EtapaProduccion.orden_produccion_id == etapa_actual.orden_produccion_id,
        EtapaProduccion.area_id == payload.area_id,
        EtapaProduccion.estado == "COMPLETADA",
    ).first()
    nueva_etapa = EtapaProduccion(
        orden_produccion_id=etapa_actual.orden_produccion_id,
        area_id=payload.area_id,
        empleado_responsable_id=payload.empleado_responsable_id,
        estado="ASIGNADA",
        observaciones=payload.observaciones,
        fecha_inicio=datetime.now(),
        es_retrabajo=ya_completada_destino is not None,
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
    from app.modules.production.service import _scope_stages

    etapa = _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == id),
        usuario_actual,
    ).first()
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
    from app.modules.production.model import EtapaAsignadoAdicional, EtapaProduccion
    from app.modules.production.service import _scope_stages

    # La etapa debe existir y pertenecer al alcance del usuario
    if not _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == id),
        usuario_actual,
    ).first():
        raise HTTPException(status_code=404, detail="Etapa de produccion no encontrada")

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
        return service.crear_consumo_material(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/consumo/por-orden/{orden_id}", response_model=List[schemas.ConsumoMaterialResponse])
def listar_consumos_por_orden(
    orden_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_consumos_por_orden(db, orden_id, usuario_actual)

@router.put("/consumo/{id}/confirmar", response_model=schemas.ConsumoMaterialResponse)
def confirmar_consumo(
    id: int,
    esquema: schemas.ConsumoConfirmarCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Confirma el uso real de una lámina pedida completa: los cortes que
    salieron de las láminas. Recalcula el costo, ajusta láminas y sobrante."""
    try:
        return service.confirmar_consumo_material(db, id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/consumo/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_consumo(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_consumo_material(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Consumo de material no encontrado")
    return None


# ------------------------------------------------------------
# Endpoints de Mano de Obra
# ------------------------------------------------------------
@router.get("/opciones-costo-produccion")
def opciones_costo_produccion(
    area_id: Optional[int] = Query(None, description="Filtrar por área de la etapa"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Tarifario activo de costos de producción (id, descripción, precio) para
    el formulario de mano de obra. Vive bajo el módulo `produccion` porque quien
    registra MO puede no tener el módulo `costos_produccion`."""
    from app.modules.costos_produccion.model import PrecioProduccion
    query = db.query(PrecioProduccion).filter(PrecioProduccion.activo.is_(True))
    if area_id is not None:
        query = query.filter(PrecioProduccion.area_id == area_id)
    items = query.order_by(PrecioProduccion.descripcion).all()
    return [
        {"id": p.id, "descripcion": p.descripcion, "precio": float(p.precio), "area_id": p.area_id}
        for p in items
    ]


@router.post("/opciones-costo-produccion", status_code=status.HTTP_201_CREATED)
def crear_opcion_costo_produccion(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Crea al vuelo un costo del tarifario (área + descripción + precio) desde
    el formulario de mano de obra, sin requerir el módulo costos_produccion."""
    from decimal import Decimal
    from app.modules.catalogos.model import Area
    from app.modules.costos_produccion.model import PrecioProduccion

    try:
        area_id = int(payload.get("area_id") or 0)
        descripcion = str(payload.get("descripcion") or "").strip()
        precio = float(payload.get("precio") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Datos inválidos.")
    if not area_id or not descripcion or precio <= 0:
        raise HTTPException(status_code=400, detail="Área, descripción y precio (> 0) son obligatorios.")
    if not db.query(Area).filter(Area.id == area_id).first():
        raise HTTPException(status_code=400, detail="El área especificada no existe.")

    item = PrecioProduccion(area_id=area_id, descripcion=descripcion[:200], precio=Decimal(str(precio)), activo=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "descripcion": item.descripcion, "precio": float(item.precio), "area_id": item.area_id}


@router.post("/mano-obra/", response_model=schemas.ManoObraResponse, status_code=status.HTTP_201_CREATED)
def registrar_mano_obra(
    esquema: schemas.ManoObraCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_mano_obra(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/mano-obra/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_mano_obra(
    id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_mano_obra(db, id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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

    data = obtener_referencia_receta(db, id, usuario_actual)
    if not data:
        raise HTTPException(status_code=404, detail="No se encontró receta de referencia para esta etapa")
    return data


@router.put("/mano-obra/{id}/listo-nomina", response_model=schemas.ManoObraResponse)
def alternar_listo_nomina(
    id: int,
    listo: bool = True,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Marca si un trabajo parcial de mano de obra está terminado y listo para incluirse en nómina."""
    try:
        db_mano = service.alternar_listo_nomina_mano_obra(db, id, listo, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_mano:
        raise HTTPException(status_code=404, detail="Mano de obra no encontrada")
    return db_mano


@router.put("/mano-obra/{id}/pagar", response_model=schemas.ManoObraResponse)
def marcar_mano_obra_pagada(
    id: int,
    pagado: bool = True,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Marca la mano de obra como pagada (crea/revierte su egreso en Gastos).
    Es el endpoint que usa el frontend (produccionService.marcarManoObraPagada);
    sin él, el botón "Marcar pagada" daba 404."""
    try:
        db_mano = service.marcar_mano_obra_pagada(db, id, pagado, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    db_obj = service.obtener_costo_por_orden(db, orden_id, usuario_actual)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Costo de produccion no encontrado para esta orden")
    return db_obj


# ------------------------------------------------------------
# Endpoints de Productos en Crudo (ítem libre: catálogo + stock)
# ------------------------------------------------------------
@router.get("/crudo/", response_model=List[schemas.CrudoResponse])
def listar_crudo(
    activo: Optional[bool] = Query(None, description="Filtrar por activo"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.listar_crudos(db, activo=activo, usuario=usuario_actual)


@router.get("/crudo/{crudo_id}", response_model=schemas.CrudoResponse)
def ver_crudo(
    crudo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_crudo(db, crudo_id, usuario_actual)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Producto en crudo no encontrado")
    return db_obj


@router.post("/crudo/", response_model=schemas.CrudoResponse, status_code=status.HTTP_201_CREATED)
def alta_crudo(
    esquema: schemas.CrudoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Crea un ítem de inventario en crudo (nombre libre). La foto de referencia
    se sube aparte como adjunto de tipo CRUDO."""
    try:
        return service.crear_crudo(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/crudo/{crudo_id}/kardex", response_model=List[schemas.CrudoMovimientoResponse])
def kardex_crudo(
    crudo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Historial de movimientos de un ítem en crudo (misma UI que insumos)."""
    return service.obtener_kardex_crudo(db, crudo_id)


@router.post("/crudo/{crudo_id}/movimiento", response_model=schemas.CrudoMovimientoResponse, status_code=status.HTTP_201_CREATED)
def movimiento_crudo(
    crudo_id: int,
    esquema: schemas.CrudoMovimientoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Registra un movimiento manual de crudo (ENTRADA/SALIDA/AJUSTE/DAÑO/DEVOLUCION)."""
    try:
        return service.registrar_movimiento_crudo(db, crudo_id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/crudo/{crudo_id}", response_model=schemas.CrudoResponse)
def editar_crudo(
    crudo_id: int,
    esquema: schemas.CrudoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Edita nombre, área, ubicación o estado del ítem en crudo."""
    try:
        db_obj = service.actualizar_crudo(db, crudo_id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_obj:
        raise HTTPException(status_code=404, detail="Producto en crudo no encontrado")
    return db_obj


# ------------------------------------------------------------
# Producción de Crudos (segunda producción, separada del kanban)
# ------------------------------------------------------------
@router.get("/crudo-produccion/", response_model=List[schemas.ProduccionCrudoResponse])
def listar_producciones_crudo(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.listar_producciones_crudo(db, usuario_actual)


@router.get("/crudo-produccion/{produccion_id}", response_model=schemas.ProduccionCrudoResponse)
def ver_produccion_crudo(
    produccion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    pc = service.obtener_produccion_crudo(db, produccion_id, usuario_actual)
    if not pc:
        raise HTTPException(status_code=404, detail="Producción de crudo no encontrada")
    return pc


@router.post("/crudo-produccion/", response_model=schemas.ProduccionCrudoResponse, status_code=status.HTTP_201_CREATED)
def crear_produccion_crudo(
    esquema: schemas.ProduccionCrudoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_produccion_crudo(db, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/crudo-produccion/{produccion_id}/consumo/", response_model=schemas.CrudoConsumoResponse, status_code=status.HTTP_201_CREATED)
def registrar_consumo_crudo(
    produccion_id: int,
    esquema: schemas.CrudoConsumoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Registra un consumo de material en una producción de crudo. Descuenta stock
    de material y genera el gasto, con quién lo pidió y quién lo registró."""
    try:
        return service.registrar_consumo_crudo(db, produccion_id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/crudo-produccion/{produccion_id}/estado", response_model=schemas.ProduccionCrudoResponse)
def cambiar_estado_produccion_crudo(
    produccion_id: int,
    esquema: schemas.ProduccionCrudoEstadoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Al marcar como COMPLETADA suma stock al ítem en crudo y materializa el
    egreso de la mano de obra sin pagar (costo de producción que va a nómina)."""
    try:
        return service.cambiar_estado_produccion_crudo(db, produccion_id, esquema.estado, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------
# Mano de obra en producción de crudo
# ------------------------------------------------------------
@router.post("/crudo-produccion/{produccion_id}/mano-obra/", response_model=schemas.ProduccionCrudoManoObraResponse, status_code=status.HTTP_201_CREATED)
def registrar_mano_obra_crudo(
    produccion_id: int,
    esquema: schemas.ProduccionCrudoManoObraCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Registra quién hizo el trabajo y cuánto cuesta en una producción de crudo.
    El egreso se materializa al finalizar la producción (COMPLETADA)."""
    try:
        return service.crear_mano_obra_crudo(db, produccion_id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/crudo-produccion/mano-obra/{mano_obra_id}", response_model=schemas.ProduccionCrudoManoObraResponse)
def actualizar_mano_obra_crudo(
    mano_obra_id: int,
    esquema: schemas.ProduccionCrudoManoObraUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.actualizar_mano_obra_crudo(db, mano_obra_id, esquema, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/crudo-produccion/mano-obra/{mano_obra_id}/listo-nomina", response_model=schemas.ProduccionCrudoManoObraResponse)
def alternar_listo_nomina_mano_obra_crudo(
    mano_obra_id: int,
    listo: bool = True,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        return service.alternar_listo_nomina_mano_obra_crudo(db, mano_obra_id, listo, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/crudo-produccion/mano-obra/{mano_obra_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_mano_obra_crudo(
    mano_obra_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_mano_obra_crudo(db, mano_obra_id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Mano de obra de crudo no encontrada")
    return None


# ------------------------------------------------------------
# Asignar crudo a un detalle de pedido (solo descuenta stock + trazabilidad)
# ------------------------------------------------------------
@router.post("/crudo/{crudo_id}/asignar/{detalle_pedido_id}", response_model=schemas.CrudoUsoResponse, status_code=status.HTTP_201_CREATED)
def asignar_crudo(
    crudo_id: int,
    detalle_pedido_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Asigna una pieza de crudo a un detalle de pedido: descuenta stock del ítem
    en crudo. No marca etapas ni descuenta materiales; el usuario cierra las
    etapas manualmente en el kanban normal."""
    try:
        return service.asignar_crudo_a_detalle(db, crudo_id, detalle_pedido_id, usuario_actual)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
