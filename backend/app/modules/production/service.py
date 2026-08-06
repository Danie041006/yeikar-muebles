from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from decimal import Decimal
from datetime import datetime, date
from app.modules.production.model import OrdenProduccion, EtapaProduccion, ConsumoMaterial, ManoObra, CostoProduccion
from app.modules.production.schemas import (
    OrdenProduccionCreate, OrdenProduccionUpdate,
    EtapaProduccionCreate, EtapaProduccionUpdate,
    ConsumoMaterialCreate, ManoObraCreate, CostoProduccionCreate
)
from app.modules.orders.model import DetallePedido
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.productos.model import Material
from app.modules.catalogos.model import Ubicacion, TipoGasto
from app.modules.inventory.service import registrar_movimiento
from app.modules.inventory.schemas import MovimientoCreate
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios, tiene_alcance_total
from app.modules.users.model import Usuario


def _scope_orders(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return filtrar_registros_propios(query, OrdenProduccion.creado_por_id, usuario)


def _scope_stages(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return query.join(EtapaProduccion.orden).filter(OrdenProduccion.creado_por_id == usuario.id)


def _snapshot_orden(orden: OrdenProduccion) -> dict:
    return {
        "detalle_pedido_id": orden.detalle_pedido_id,
        "estado": orden.estado,
        "fecha_inicio": orden.fecha_inicio,
        "fecha_fin": orden.fecha_fin,
    }
# ------------------------------------------------------------
# Servicios para Órdenes de Producción
# ------------------------------------------------------------
def obtener_orden_produccion(db: Session, id_orden: int, usuario: Usuario | None = None):
    query = db.query(OrdenProduccion).options(
        joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
    ).filter(OrdenProduccion.id == id_orden)
    return _scope_orders(query, usuario).first()


def obtener_ordenes_produccion(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    usuario: Usuario | None = None,
):
    query = db.query(OrdenProduccion).options(
        joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
    )
    query = _scope_orders(query, usuario)
    if buscar:
        if buscar.isdigit():
            id_val = int(buscar)
            query = query.filter(
                or_(
                    OrdenProduccion.id == id_val,
                    OrdenProduccion.detalle_pedido_id == id_val,
                    OrdenProduccion.estado.ilike(f"%{buscar}%")
                )
            )
        else:
            query = query.filter(OrdenProduccion.estado.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()
def crear_orden_produccion(db: Session, esquema: OrdenProduccionCreate, usuario: Usuario | None = None):
    detalle_query = db.query(DetallePedido).join(Pedido, Pedido.id == DetallePedido.pedido_id).filter(
        DetallePedido.id == esquema.detalle_pedido_id
    )
    if usuario is not None and not tiene_alcance_total(usuario):
        detalle_query = detalle_query.filter(Pedido.creado_por_id == usuario.id)
    if not detalle_query.first():
        raise ValueError("El detalle de pedido no existe o no está disponible para este usuario.")

    db_orden = OrdenProduccion(
        detalle_pedido_id=esquema.detalle_pedido_id,
        estado=esquema.estado,
        fecha_inicio=esquema.fecha_inicio,
        fecha_fin=esquema.fecha_fin,
        creado_por_id=usuario.id if usuario is not None else None,
        actualizado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_orden)
    db.flush()
    record_event(db, actor=usuario, action="CREATE", entity_type="orden_produccion", entity_id=db_orden.id, after=_snapshot_orden(db_orden))
    db.commit()
    db.refresh(db_orden)
    return db_orden
def crear_orden_desde_detalle_pedido(db: Session, detalle_pedido_id: int, usuario: Usuario | None = None):
    # Verificar que el detalle del pedido exista.
    # FOR UPDATE sobre el detalle: dos requests simultáneos para el mismo detalle
    # se serializan y solo el primero crea la orden (evita IntegrityError 500).
    detalle_query = db.query(DetallePedido).join(Pedido, Pedido.id == DetallePedido.pedido_id).filter(DetallePedido.id == detalle_pedido_id)
    if usuario is not None and not tiene_alcance_total(usuario):
        detalle_query = detalle_query.filter(Pedido.creado_por_id == usuario.id)
    detalle = detalle_query.with_for_update().first()
    if not detalle:
        raise ValueError("El detalle de pedido especificado no existe.")
    
    # Verificar si ya existe una orden de producción para este detalle
    existente = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id == detalle_pedido_id).first()
    if existente:
        return existente
        
    db_orden = OrdenProduccion(
        detalle_pedido_id=detalle_pedido_id,
        estado="PENDIENTE",
        fecha_inicio=None,
        fecha_fin=None,
        creado_por_id=usuario.id if usuario is not None else (detalle.pedido.creado_por_id if detalle.pedido else None),
        actualizado_por_id=usuario.id if usuario is not None else (detalle.pedido.creado_por_id if detalle.pedido else None),
    )
    db.add(db_orden)
    db.commit()
    db.refresh(db_orden)
    return db_orden
def actualizar_orden_produccion(db: Session, id_orden: int, esquema: OrdenProduccionUpdate, usuario: Usuario | None = None):
    db_orden = obtener_orden_produccion(db, id_orden, usuario)
    if not db_orden:
        return None
    antes = _snapshot_orden(db_orden)
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_orden, clave, valor)
    if usuario is not None:
        db_orden.actualizado_por_id = usuario.id
    record_event(db, actor=usuario, action="UPDATE", entity_type="orden_produccion", entity_id=db_orden.id, before=antes, after=_snapshot_orden(db_orden))
    db.commit()
    db.refresh(db_orden)
    return db_orden
def cambiar_estado_orden_produccion(db: Session, id_orden: int, nuevo_estado: str, usuario: Usuario | None = None):
    db_orden = obtener_orden_produccion(db, id_orden, usuario)
    if not db_orden:
        return None
    
    estados_validos = ['PENDIENTE', 'EN_PRODUCCION', 'PAUSADA', 'FINALIZADA', 'CANCELADA']
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado de orden invalido. Debe ser uno de: {estados_validos}")
    
    antes = _snapshot_orden(db_orden)
    db_orden.estado = nuevo_estado
    if nuevo_estado == 'EN_PRODUCCION' and not db_orden.fecha_inicio:
        db_orden.fecha_inicio = date.today()
    elif nuevo_estado == 'FINALIZADA':
        db_orden.fecha_fin = date.today()

        # C2: no se puede finalizar una orden sin ninguna etapa creada
        n_etapas = db.query(EtapaProduccion).filter(
            EtapaProduccion.orden_produccion_id == id_orden
        ).count()
        if n_etapas == 0:
            raise ValueError(
                "No se puede finalizar una orden de producción sin etapas. "
                "Cree al menos una etapa antes de finalizar."
            )

        # C4: calcular y guardar costos al finalizar SOLO si no existe un costo
        # ya calculado manualmente (no pisar la ganancia/gastos del supervisor).
        if not obtener_costo_por_orden(db, id_orden):
            try:
                calcular_y_guardar_costo(db, id_orden)
            except Exception as e:
                # Imprimir error pero no bloquear la finalización
                print(f"Error al calcular costos automáticos al finalizar orden {id_orden}: {e}")

        # Sincronizar estado del Pedido a TERMINADO si TODAS las líneas del pedido
        # tienen una orden de producción FINALIZADA (no solo las que tienen orden).
        # FOR UPDATE sobre el pedido: dos finalizaciones simultáneas de órdenes del
        # mismo pedido se serializan, evitando que ambas lean "no todas finalizadas"
        # y que el pedido nunca pase a TERMINADO (o que se cree envío dos veces).
        try:
            detalle = db.query(DetallePedido).filter(DetallePedido.id == db_orden.detalle_pedido_id).first()
            if detalle:
                pedido = db.query(Pedido).filter(Pedido.id == detalle.pedido_id).with_for_update().first()
                if pedido:
                    # C3: TODAS las líneas del pedido deben tener su orden FINALIZADA.
                    # Si alguna línea no tiene orden de producción, el pedido NO termina.
                    n_detalles = db.query(DetallePedido).filter(
                        DetallePedido.pedido_id == pedido.id
                    ).count()
                    n_ordenes_finalizadas = db.query(OrdenProduccion).join(
                        DetallePedido, DetallePedido.id == OrdenProduccion.detalle_pedido_id
                    ).filter(
                        DetallePedido.pedido_id == pedido.id,
                        OrdenProduccion.estado == "FINALIZADA",
                    ).count()
                    todas_finalizadas = n_detalles > 0 and n_ordenes_finalizadas == n_detalles

                    if todas_finalizadas:
                        pedido.estado = "TERMINADO"
                        # Generar envío automático
                        from app.modules.envios.service import crear_envio_automatico
                        crear_envio_automatico(db, pedido.id, usuario)
        except Exception as e:
            print(f"Error al verificar estado del pedido e iniciar envío para orden {id_orden}: {e}")

    if usuario is not None:
        db_orden.actualizado_por_id = usuario.id
    record_event(db, actor=usuario, action="STATE_CHANGE", entity_type="orden_produccion", entity_id=db_orden.id, before=antes, after=_snapshot_orden(db_orden))
    db.commit()
    db.refresh(db_orden)
    return db_orden
def eliminar_orden_produccion(db: Session, id_orden: int, usuario: Usuario | None = None):
    db_orden = obtener_orden_produccion(db, id_orden, usuario)
    if not db_orden:
        return False
    record_event(db, actor=usuario, action="DELETE", entity_type="orden_produccion", entity_id=db_orden.id, before=_snapshot_orden(db_orden))
    db.delete(db_orden)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Etapas de Producción
# ------------------------------------------------------------
def obtener_etapa_produccion(db: Session, id_etapa: int, usuario: Usuario | None = None):
    query = db.query(EtapaProduccion).filter(EtapaProduccion.id == id_etapa)
    return _scope_stages(query, usuario).first()


def crear_etapa_produccion(db: Session, esquema: EtapaProduccionCreate, usuario: Usuario | None = None):
    db_etapa = EtapaProduccion(
        orden_produccion_id=esquema.orden_produccion_id,
        area_id=esquema.area_id,
        empleado_responsable_id=esquema.empleado_responsable_id,
        estado=esquema.estado,
        observaciones=esquema.observaciones,
        fecha_inicio=esquema.fecha_inicio,
        fecha_fin=esquema.fecha_fin
    )
    orden = _scope_orders(
        db.query(OrdenProduccion).filter(OrdenProduccion.id == esquema.orden_produccion_id),
        usuario,
    ).with_for_update().first()
    if not orden:
        raise ValueError("La orden de producción no existe o no está disponible para este usuario.")
    db.add(db_etapa)

    # Si la orden está en estado PENDIENTE, cambiarla a EN_PRODUCCION al crear su primera etapa.
    # FOR UPDATE: dos primeras etapas simultáneas se serializan y no pisan fecha/estado.
    if orden and orden.estado == "PENDIENTE":
        orden.estado = "EN_PRODUCCION"
        if not orden.fecha_inicio:
            orden.fecha_inicio = date.today()
            
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def actualizar_etapa_produccion(db: Session, id_etapa: int, esquema: EtapaProduccionUpdate, usuario: Usuario | None = None):
    db_etapa = obtener_etapa_produccion(db, id_etapa, usuario)
    if not db_etapa:
        return None
    data = esquema.model_dump(exclude_unset=True)
    for clave, valor in data.items():
        setattr(db_etapa, clave, valor)
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def cambiar_estado_etapa_produccion(db: Session, id_etapa: int, nuevo_estado: str, usuario: Usuario | None = None):
    # FOR UPDATE: evita el lost-update cuando dos finalizaciones/cambios de estado
    # concurrentes leen el mismo estado base y se pisan entre sí.
    db_etapa = _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == id_etapa),
        usuario,
    ).with_for_update().first()
    if not db_etapa:
        return None
    
    estados_validos = ['ASIGNADA', 'EN_PROCESO', 'PAUSADA', 'COMPLETADA']
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado de etapa invalido. Debe ser uno de: {estados_validos}")
        
    db_etapa.estado = nuevo_estado
    if nuevo_estado == 'EN_PROCESO' and not db_etapa.fecha_inicio:
        db_etapa.fecha_inicio = datetime.now()
    elif nuevo_estado == 'COMPLETADA':
        db_etapa.fecha_fin = datetime.now()
        
    db.commit()
    db.refresh(db_etapa)
    return db_etapa
def eliminar_etapa_produccion(db: Session, id_etapa: int, usuario: Usuario | None = None):
    db_etapa = obtener_etapa_produccion(db, id_etapa, usuario)
    if not db_etapa:
        return False
    db.delete(db_etapa)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Consumo de Material
# ------------------------------------------------------------
def obtener_consumo_material(db: Session, id_consumo: int):
    return db.query(ConsumoMaterial).filter(ConsumoMaterial.id == id_consumo).first()
def crear_consumo_material(db: Session, esquema: ConsumoMaterialCreate):
    # 0. Validar que la cantidad sea positiva
    if esquema.cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero")
    # 1. Validar que la etapa exista (evita IntegrityError 500 por FK)
    etapa = db.query(EtapaProduccion).filter(
        EtapaProduccion.id == esquema.etapa_produccion_id
    ).first()
    if not etapa:
        raise ValueError("La etapa de producción especificada no existe.")
    # 2. Obtener la ubicación del depósito principal (búsqueda dinámica)
    ubicacion = db.query(Ubicacion).filter(Ubicacion.nombre == "Depósito Principal").first()
    if not ubicacion:
        # Si no existe, usamos fallback
        ubicacion_id = 1
    else:
        ubicacion_id = ubicacion.id
    # 3. Obtener el costo unitario actual del material para congelarlo
    material = db.query(Material).filter(Material.id == esquema.material_id).first()
    if not material:
        raise ValueError("El material especificado no existe.")
    # 4. Crear el registro de consumo
    db_consumo = ConsumoMaterial(
        etapa_produccion_id=esquema.etapa_produccion_id,
        material_id=esquema.material_id,
        cantidad=esquema.cantidad,
        costo_unitario=material.costo_base,
        fecha=esquema.fecha,
        observaciones=esquema.observaciones
    )
    db.add(db_consumo)
    db.flush()  # para obtener db_consumo.id
    # 4. Registrar el movimiento de inventario (SALIDA)
    movimiento = MovimientoCreate(
        material_id=esquema.material_id,
        ubicacion_id=ubicacion_id,
        tipo="SALIDA",
        cantidad=Decimal(str(esquema.cantidad)),
        referencia_tipo="produccion",
        referencia_id=db_consumo.id,
        observaciones=f"Consumo en etapa {esquema.etapa_produccion_id}"
    )
    try:
        registrar_movimiento(db, movimiento)
    except ValueError as e:
        db.rollback()
        raise ValueError(f"Error al descontar inventario: {e}")

    tipo_gasto_consumo = db.query(TipoGasto).filter(
        TipoGasto.nombre == "Consumo de Materia Prima en Producción"
    ).first()
    if tipo_gasto_consumo:
        costo_total = Decimal(str(esquema.cantidad)) * material.costo_base
        from app.modules.gastos.model import Gasto
        db_gasto = Gasto(
            tipo_gasto_id=tipo_gasto_consumo.id,
            moneda_id=1,
            fecha=esquema.fecha or date.today(),
            descripcion=f"Consumo {material.nombre} ({esquema.cantidad}) - Etapa #{esquema.etapa_produccion_id}",
            monto=costo_total,
            tasa_cambio=Decimal("1.0"),
            monto_en_moneda_base=costo_total,
            observaciones=f"Generado automáticamente al descontar inventario en producción (Etapa #{esquema.etapa_produccion_id})"
        )
        db.add(db_gasto)

    db.commit()
    db.refresh(db_consumo)
    return db_consumo
def obtener_referencia_receta(db: Session, id_etapa: int) -> dict | None:
    """
    Retorna la receta completa del producto asociado a la etapa,
    con cantidad_base como cantidad_esperada (sin escalar aún).
    Incluye dimensiones del pedido para escalado futuro.
    """
    from app.modules.productos.model import ProductoMaterial, Material as MatModel

    etapa = db.query(EtapaProduccion).options(
        joinedload(EtapaProduccion.orden).joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
    ).filter(EtapaProduccion.id == id_etapa).first()

    if not etapa or not etapa.orden or not etapa.orden.detalle_pedido:
        return None

    detalle = etapa.orden.detalle_pedido
    producto = detalle.producto
    if not producto:
        return None

    receta = (
        db.query(ProductoMaterial)
        .filter(ProductoMaterial.producto_id == producto.id)
        .all()
    )

    materiales = []
    for pm in receta:
        mat = db.query(MatModel).filter(MatModel.id == pm.material_id).first()
        if not mat:
            continue
        materiales.append({
            "material_id": mat.id,
            "nombre": mat.nombre,
            "seccion": pm.seccion or "EBANISTERIA",
            "cantidad_base": float(pm.cantidad_base),
            "cantidad_esperada": float(pm.cantidad_base),
            "unidad": mat.unidad_medida.abreviatura if mat.unidad_medida else "",
            "costo_unitario": float(mat.costo_base),
        })

    return {
        "producto_id": producto.id,
        "producto_nombre": producto.nombre,
        "dimensiones": {
            "ancho": float(detalle.ancho) if detalle.ancho else None,
            "largo": float(detalle.largo) if detalle.largo else None,
        },
        "materiales": materiales,
    }


def eliminar_consumo_material(db: Session, id_consumo: int):
    db_consumo = obtener_consumo_material(db, id_consumo)
    if not db_consumo:
        return False

    etapa_id = db_consumo.etapa_produccion_id
    material_id = db_consumo.material_id
    cantidad = db_consumo.cantidad

    # C6: reponer el stock descontado por el consumo (movimiento inverso ENTRADA)
    try:
        from app.modules.inventory.schemas import MovimientoCreate
        ubicacion = db.query(Ubicacion).filter(Ubicacion.nombre == "Depósito Principal").first()
        movimiento = MovimientoCreate(
            material_id=material_id,
            ubicacion_id=ubicacion.id if ubicacion else 1,
            tipo="ENTRADA",
            cantidad=cantidad,
            referencia_tipo="produccion",
            referencia_id=db_consumo.id,
            observaciones=f"Reversa de consumo en etapa {etapa_id}",
        )
        registrar_movimiento(db, movimiento)
    except Exception as e:  # noqa: BLE001 — no romper la eliminación si la reversa falla
        print(f"Error al reponer stock al eliminar consumo {id_consumo}: {e}")

    # Revertir el gasto generado automáticamente por el consumo
    from app.modules.gastos.model import Gasto
    material = db.query(Material).filter(Material.id == material_id).first()
    if material:
        descripcion = (
            f"Consumo {material.nombre} ({cantidad}) - Etapa #{etapa_id}"
        )
        db.query(Gasto).filter(Gasto.descripcion == descripcion).delete(
            synchronize_session=False
        )

    db.delete(db_consumo)
    db.commit()
    return True
def obtener_consumos_por_orden(db: Session, orden_id: int):
    return db.query(ConsumoMaterial).join(EtapaProduccion).filter(EtapaProduccion.orden_produccion_id == orden_id).all()
# ------------------------------------------------------------
# Servicios para Mano de Obra
# ------------------------------------------------------------
def obtener_mano_obra(db: Session, id_mano_obra: int):
    return db.query(ManoObra).filter(ManoObra.id == id_mano_obra).first()
def crear_mano_obra(db: Session, esquema: ManoObraCreate):
    db_mano_obra = ManoObra(
        etapa_produccion_id=esquema.etapa_produccion_id,
        empleado_id=esquema.empleado_id,
        monto=esquema.monto,
        porcentaje_recargo=esquema.porcentaje_recargo,
        pagado=getattr(esquema, "pagado", False),
        observaciones=esquema.observaciones
    )
    db.add(db_mano_obra)
    db.commit()
    db.refresh(db_mano_obra)
    return db_mano_obra

def marcar_mano_obra_pagada(db: Session, mano_obra_id: int, pagado: bool = True):
    db_mano = obtener_mano_obra(db, mano_obra_id)
    if not db_mano:
        return None
    db_mano.pagado = pagado
    db.commit()
    db.refresh(db_mano)
    return db_mano
def eliminar_mano_obra(db: Session, id_mano_obra: int):
    db_mano = obtener_mano_obra(db, id_mano_obra)
    if not db_mano:
        return False
    db.delete(db_mano)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Costo de Producción (Lógica Financiera)
# ------------------------------------------------------------
def obtener_costo_por_orden(db: Session, orden_id: int):
    return db.query(CostoProduccion).filter(CostoProduccion.orden_produccion_id == orden_id).first()
def calcular_y_guardar_costo(db: Session, orden_id: int, ganancia_porcentaje: float = 0.0, costo_gastos: float = 0.0, precio_impuestos_base: float = 0.0):
    # FOR UPDATE: serializa los cálculos concurrentes sobre la misma orden para
    # que el get-or-create de CostoProduccion no genere duplicados.
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).with_for_update().first()
    if not orden:
        raise ValueError("La orden de produccion especificada no existe.")
    # Calcular costo de materiales
    consumos = obtener_consumos_por_orden(db, orden_id)
    costo_material = 0.0
    for c in consumos:
        costo_u = c.costo_unitario
        if costo_u is None:
            # Fallback a costo_base si no está congelado (para registros antiguos)
            material = db.query(Material).filter(Material.id == c.material_id).first()
            costo_u = material.costo_base if material else 0.0
        costo_material += float(c.cantidad) * float(costo_u)
    # Calcular costo de mano de obra
    mano_obras = db.query(ManoObra).join(EtapaProduccion).filter(EtapaProduccion.orden_produccion_id == orden_id).all()
    costo_mano_obra = 0.0
    for mo in mano_obras:
        recargo = float(mo.porcentaje_recargo) / 100.0 if mo.porcentaje_recargo else 0.0
        costo_mano_obra += float(mo.monto) * (1.0 + recargo)
    # Calcular costo total y precio de venta
    costo_total = costo_material + costo_mano_obra + float(costo_gastos)
    ganancia_factor = float(ganancia_porcentaje) / 100.0
    precio_venta_calculado = costo_total * (1.0 + ganancia_factor) + float(precio_impuestos_base)
    # Buscar o crear registro de CostoProduccion
    db_costo = obtener_costo_por_orden(db, orden_id)
    if not db_costo:
        db_costo = CostoProduccion(orden_produccion_id=orden_id)
        db.add(db_costo)
    db_costo.costo_material = costo_material
    db_costo.costo_mano_obra = costo_mano_obra
    db_costo.costo_gastos = costo_gastos
    db_costo.precio_impuestos_base = precio_impuestos_base
    db_costo.ganancia_porcentaje = ganancia_porcentaje
    db_costo.costo_total = costo_total
    db_costo.precio_venta_calculado = precio_venta_calculado
    db.commit()
    db.refresh(db_costo)
    return db_costo
