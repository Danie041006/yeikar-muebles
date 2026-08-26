from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, exists
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from app.modules.production.model import OrdenProduccion, EtapaProduccion, ConsumoMaterial, ManoObra, CostoProduccion
from app.modules.production.schemas import (
    OrdenProduccionCreate, OrdenProduccionUpdate,
    EtapaProduccionCreate, EtapaProduccionUpdate,
    ConsumoMaterialCreate, ManoObraCreate, CostoProduccionCreate
)
from app.modules.orders.model import DetallePedido
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.productos.model import Material, Producto, ProductoMaterial
from app.modules.empleados.model import Empleado
from app.modules.clients.model import Client
from app.modules.catalogos.model import Ubicacion, TipoGasto
from app.modules.inventory.service import registrar_movimiento
from app.modules.inventory.schemas import MovimientoCreate
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios, tiene_alcance_total
from app.modules.users.model import Usuario
from app.core.state_machine import (
    TRANSICIONES_ORDEN_PRODUCCION,
    TRANSICIONES_ETAPA_PRODUCCION,
    validar_transicion,
)
from app.modules.productos.cost_service import _calcular_cantidad_material, _normalizar_seccion


def _redondear2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _scope_orders(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return filtrar_registros_propios(query, OrdenProduccion.creado_por_id, usuario)


def _scope_stages(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return query.join(EtapaProduccion.orden).filter(OrdenProduccion.creado_por_id == usuario.id)


def _scope_consumos(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return (
        query.join(ConsumoMaterial.etapa)
        .join(EtapaProduccion.orden)
        .filter(OrdenProduccion.creado_por_id == usuario.id)
    )


def _scope_mano_obras(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    return (
        query.join(ManoObra.etapa)
        .join(EtapaProduccion.orden)
        .filter(OrdenProduccion.creado_por_id == usuario.id)
    )


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
        term = f"%{buscar}%"
        condiciones = [OrdenProduccion.estado.ilike(term)]
        if buscar.isdigit():
            n = int(buscar)
            condiciones.append(OrdenProduccion.id == n)
            condiciones.append(OrdenProduccion.detalle_pedido_id == n)
        condiciones.append(
            exists().where(
                DetallePedido.id == OrdenProduccion.detalle_pedido_id,
                or_(
                    DetallePedido.producto.has(Producto.nombre.ilike(term)),
                    DetallePedido.pedido.has(
                        Pedido.cliente.has(Client.nombre.ilike(term))
                    ),
                    DetallePedido.pedido_id == (int(buscar) if buscar.isdigit() else -1),
                ),
            )
        )
        query = query.filter(or_(*condiciones))
    return query.offset(salto).limit(limite).all()
def crear_orden_produccion(db: Session, esquema: OrdenProduccionCreate, usuario: Usuario | None = None):
    # Los estados terminales no se pueden crear directamente: FINALIZADA exige
    # etapas completas + costos (la máquina de estados la valida), CANCELADA
    # es un estado terminal que debe pasar por la transición.
    if esquema.estado not in ("PENDIENTE", "EN_PRODUCCION", "PAUSADA"):
        raise ValueError(
            f"No se puede crear una orden directamente en estado '{esquema.estado}'. "
            "Use PENDIENTE, EN_PRODUCCION o PAUSADA; los cambios a FINALIZADA/CANCELADA "
            "se hacen por el endpoint de estado."
        )
    detalle_query = db.query(DetallePedido).join(Pedido, Pedido.id == DetallePedido.pedido_id).filter(
        DetallePedido.id == esquema.detalle_pedido_id
    )
    if usuario is not None and not tiene_alcance_total(usuario):
        detalle_query = detalle_query.filter(Pedido.creado_por_id == usuario.id)
    # Los productos de REVENTA no se fabrican: se venden del inventario.
    _detalle = detalle_query.first()
    if not _detalle:
        raise ValueError("El detalle de pedido no existe o no está disponible para este usuario.")
    if _detalle.producto is not None and _detalle.producto.es_reventa:
        raise ValueError(
            f"El producto '{_detalle.producto.nombre}' es de reventa: no entra a producción. "
            "Su venta descuenta stock del inventario al facturar."
        )

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

    # Los productos de REVENTA no se fabrican: se venden del inventario.
    # Nunca deben entrar al tablero de producción.
    if detalle.producto is not None and detalle.producto.es_reventa:
        raise ValueError(
            f"El producto '{detalle.producto.nombre}' es de reventa: no entra a producción. "
            "Su venta descuenta stock del inventario al facturar."
        )

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
    validar_transicion(TRANSICIONES_ORDEN_PRODUCCION, db_orden.estado, nuevo_estado, "orden de producción")

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

        # C5: no se puede finalizar con etapas sin completar (trabajo a medias
        # no puede quedar marcado como terminado).
        n_etapas_incompletas = db.query(EtapaProduccion).filter(
            EtapaProduccion.orden_produccion_id == id_orden,
            EtapaProduccion.estado != "COMPLETADA",
        ).count()
        if n_etapas_incompletas > 0:
            raise ValueError(
                f"No se puede finalizar la orden: hay {n_etapas_incompletas} etapa(s) "
                "sin completar. Todas las etapas deben estar COMPLETADA."
            )

        # C4: calcular y guardar costos al finalizar SOLO si no existe un costo
        # ya calculado manualmente (no pisar la ganancia/gastos del supervisor).
        # Si el cálculo falla, la orden NO se finaliza: nunca quedan órdenes
        # cerradas sin costos (antes el error se tragaba con print()).
        if not obtener_costo_por_orden(db, id_orden):
            calcular_y_guardar_costo(db, id_orden)

        # Sincronizar estado del Pedido a TERMINADO si TODAS las líneas del pedido
        # tienen una orden de producción FINALIZADA (no solo las que tienen orden).
        # FOR UPDATE sobre el pedido: dos finalizaciones simultáneas de órdenes del
        # mismo pedido se serializan, evitando que ambas lean "no todas finalizadas"
        # y que el pedido nunca pase a TERMINADO (o que se cree envío dos veces).
        # IMPORTANTE: la sesión usa autoflush=False; el flush garantiza que el
        # estado recién asignado (FINALIZADA) sea visible para el count() que
        # decide si el pedido pasa a TERMINADO (antes contaba 0 siempre y la
        # cadena producción→terminado→envío estaba rota en silencio).
        db.flush()
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

                if todas_finalizadas and pedido.estado not in ("TERMINADO", "ENTREGADO"):
                    pedido.estado = "TERMINADO"
                    # Generar envío automático
                    from app.modules.envios.service import crear_envio_automatico
                    crear_envio_automatico(db, pedido.id, usuario)

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
    # Bloquear eliminación si la orden tiene etapas (y por tanto consumos y
    # mano de obra): borrarla en cascada dejaría stock descontado y gastos
    # automáticos huérfanos en el P&L.
    n_etapas = db.query(EtapaProduccion).filter(
        EtapaProduccion.orden_produccion_id == id_orden
    ).count()
    if n_etapas > 0:
        raise ValueError(
            "No se puede eliminar una orden de producción con etapas registradas. "
            "Elimine primero las etapas o mantenga la orden para preservar el "
            "historial de consumos, stock y gastos."
        )
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

    # Bloquear etapas duplicadas de la misma área mientras haya una activa:
    # dos etapas de Ebanistería simultáneas permitían doble/triple consumo de
    # material y mano de obra en la misma área. El retrabajo se modela pasando
    # la etapa por pasar-a-area (que exige área diferente), no duplicando.
    activa_misma_area = db.query(EtapaProduccion).filter(
        EtapaProduccion.orden_produccion_id == esquema.orden_produccion_id,
        EtapaProduccion.area_id == esquema.area_id,
        EtapaProduccion.estado.in_(["ASIGNADA", "EN_PROCESO", "PAUSADA"]),
    ).first()
    if activa_misma_area:
        raise ValueError(
            f"Ya existe una etapa activa en el área {activa_misma_area.area_id} "
            f"para esta orden (etapa #{activa_misma_area.id}). Completa esa etapa "
            "antes de crear otra en la misma área."
        )

    db.add(db_etapa)

    # Retrabajo: si el área ya tiene una etapa COMPLETADA para esta orden, la
    # nueva etapa es retrabajo y la nómina destajo NO la paga (evita el doble
    # pago del mismo trabajo).
    ya_completada_misma_area = db.query(EtapaProduccion).filter(
        EtapaProduccion.orden_produccion_id == esquema.orden_produccion_id,
        EtapaProduccion.area_id == esquema.area_id,
        EtapaProduccion.estado == "COMPLETADA",
    ).first()
    db_etapa.es_retrabajo = ya_completada_misma_area is not None

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
    validar_transicion(TRANSICIONES_ETAPA_PRODUCCION, db_etapa.estado, nuevo_estado, "etapa de producción")

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
    n_consumos = db.query(ConsumoMaterial).filter(
        ConsumoMaterial.etapa_produccion_id == id_etapa
    ).count()
    n_mano_obras = db.query(ManoObra).filter(
        ManoObra.etapa_produccion_id == id_etapa
    ).count()
    if n_consumos > 0 or n_mano_obras > 0:
        raise ValueError(
            "No se puede eliminar una etapa con consumos o mano de obra registrados: "
            "quedarían descuentos de inventario y gastos sin revertir. "
            "Elimine primero los consumos y la mano de obra."
        )
    db.delete(db_etapa)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Consumo de Material
# ------------------------------------------------------------
def obtener_consumo_material(db: Session, id_consumo: int, usuario: Usuario | None = None):
    query = db.query(ConsumoMaterial).filter(ConsumoMaterial.id == id_consumo)
    return _scope_consumos(query, usuario).first()


def crear_consumo_material(db: Session, esquema: ConsumoMaterialCreate, usuario: Usuario | None = None):
    # 0. Validar que la cantidad sea positiva
    if esquema.cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero")
    # 1. Validar que la etapa exista (evita IntegrityError 500 por FK) y que
    #    pertenezca al alcance del usuario.
    etapa = _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == esquema.etapa_produccion_id),
        usuario,
    ).first()
    if not etapa:
        raise ValueError("La etapa de producción especificada no existe o no está disponible para este usuario.")
    # Los consumos solo tienen sentido mientras la etapa está EN_PROCESO:
    # registrar material en etapas ASIGNADA/COMPLETADA corrompe el "cuándo"
    # contable del costo.
    if etapa.estado != "EN_PROCESO":
        raise ValueError(
            f"No se puede registrar consumo en una etapa en estado '{etapa.estado}'. "
            "La etapa debe estar EN_PROCESO."
        )
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
    # 3.5 Validar el SOLICITANTE (quién pide el material). Es obligatorio:
    # queda registrado el empleado que solicita, no solo el usuario que digita.
    solicitante = db.query(Empleado).filter(Empleado.id == esquema.solicitante_empleado_id).first()
    if not solicitante:
        raise ValueError("Debe indicar quién solicita el material (solicitante inválido).")
    # 4. Crear el registro de consumo
    seccion = esquema.seccion or _normalizar_seccion(etapa.area.nombre if etapa.area else None)
    db_consumo = ConsumoMaterial(
        etapa_produccion_id=esquema.etapa_produccion_id,
        material_id=esquema.material_id,
        cantidad=esquema.cantidad,
        costo_unitario=material.costo_base,
        seccion=seccion,
        solicitante_empleado_id=solicitante.id,
        creado_por_id=usuario.id if usuario is not None else None,
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
        observaciones=f"Consumo en etapa {esquema.etapa_produccion_id} — Solicitante: {solicitante.nombre}"
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
            descripcion=f"Consumo {material.nombre} ({esquema.cantidad}) - Etapa #{esquema.etapa_produccion_id} — Solicita: {solicitante.nombre}",
            monto=costo_total,
            tasa_cambio=Decimal("1.0"),
            monto_en_moneda_base=costo_total,
            # El marcador [consumo {id}] permite revertir el gasto EXACTO al
            # eliminar el consumo (antes se comparaba por float y podía fallar).
            observaciones=f"Generado automáticamente al descontar inventario en producción (Etapa #{esquema.etapa_produccion_id}) [consumo {db_consumo.id}]"
        )
        db.add(db_gasto)

    record_event(
        db, actor=usuario, action="CREATE", entity_type="consumo_material",
        entity_id=db_consumo.id,
        after={
            "material_id": db_consumo.material_id,
            "cantidad": float(db_consumo.cantidad),
            "etapa_produccion_id": db_consumo.etapa_produccion_id,
            "solicitante_empleado_id": db_consumo.solicitante_empleado_id,
            "solicitante": solicitante.nombre,
        },
    )
    db.commit()
    db.refresh(db_consumo)
    return db_consumo
def obtener_referencia_receta(db: Session, id_etapa: int, usuario: Usuario | None = None) -> dict | None:
    """
    Retorna la receta del producto asociado a la etapa con las cantidades
    ESCALADAS a las dimensiones del pedido (tipo_escala: LINEAL/AREA/
    ESPACIADO/POR_RANGO/...), usando el mismo motor de costeo paramétrico
    de `cost_service` (antes se mostraba cantidad_base sin escalar, lo que
    confundía al operario con materiales variables como la pintura).
    """
    from app.modules.productos.model import Material as MatModel

    etapa = _scope_stages(
        db.query(EtapaProduccion).options(
            joinedload(EtapaProduccion.area),
            joinedload(EtapaProduccion.orden).joinedload(OrdenProduccion.detalle_pedido).joinedload(DetallePedido.producto)
        ).filter(EtapaProduccion.id == id_etapa),
        usuario,
    ).first()

    if not etapa or not etapa.orden or not etapa.orden.detalle_pedido:
        return None

    detalle = etapa.orden.detalle_pedido
    producto = detalle.producto
    if not producto:
        return None

    ancho_base = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
    largo_base = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
    nuevo_ancho = Decimal(str(detalle.ancho)) if detalle.ancho else ancho_base
    nuevo_largo = Decimal(str(detalle.largo)) if detalle.largo else largo_base
    area_base = ancho_base * largo_base
    area_nueva = nuevo_ancho * nuevo_largo

    receta = (
        db.query(ProductoMaterial)
        .options(joinedload(ProductoMaterial.material).joinedload(MatModel.unidad_medida))
        .filter(ProductoMaterial.producto_id == producto.id)
        .all()
    )

    materiales = []
    for pm in receta:
        mat = pm.material
        if not mat:
            continue
        cantidad = _calcular_cantidad_material(
            pm, nuevo_ancho, nuevo_largo, ancho_base, largo_base, area_base, area_nueva, None
        )
        materiales.append({
            "material_id": mat.id,
            "nombre": mat.nombre,
            "seccion": _normalizar_seccion(pm.seccion),
            "tipo_escala": pm.tipo_escala or "FIJO",
            "condicion_cumplida": bool(cantidad > 0 or not pm.condicion_activacion),
            "cantidad_base": float(pm.cantidad_base),
            "cantidad_esperada": float(cantidad),
            "unidad": mat.unidad_medida.abreviatura if mat.unidad_medida else "",
            "costo_unitario": float(mat.costo_base),
        })

    return {
        "producto_id": producto.id,
        "producto_nombre": producto.nombre,
        "dimensiones": {
            "ancho": float(nuevo_ancho),
            "largo": float(nuevo_largo),
        },
        "seccion_actual": _normalizar_seccion(etapa.area.nombre) if etapa.area else None,
        "materiales": materiales,
    }


def eliminar_consumo_material(db: Session, id_consumo: int, usuario: Usuario | None = None):
    db_consumo = obtener_consumo_material(db, id_consumo, usuario)
    if not db_consumo:
        return False

    etapa_id = db_consumo.etapa_produccion_id
    material_id = db_consumo.material_id
    cantidad = db_consumo.cantidad

    # C6: reponer el stock descontado por el consumo (movimiento inverso ENTRADA).
    # Si la reversa falla, la eliminación FALLA (rollback): nunca se deja el
    # inventario descontado en silencio (antes se imprimía y se seguía).
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

    # Revertir el gasto generado automáticamente por el consumo. El marcador
    # [consumo {id}] identifica el gasto EXACTO (antes se comparaba descripción
    # + monto float y podía fallar dejando gastos fantasma en el P&L).
    from app.modules.gastos.model import Gasto
    db.query(Gasto).filter(
        Gasto.observaciones.like(f"%[consumo {id_consumo}]%"),
    ).delete(synchronize_session=False)

    record_event(
        db, actor=usuario, action="DELETE", entity_type="consumo_material",
        entity_id=id_consumo,
        before={"material_id": material_id, "cantidad": float(cantidad), "etapa_produccion_id": etapa_id},
    )
    db.delete(db_consumo)
    db.commit()
    return True


def obtener_consumos_por_orden(db: Session, orden_id: int, usuario: Usuario | None = None):
    query = (
        db.query(ConsumoMaterial)
        .join(EtapaProduccion)
        .filter(EtapaProduccion.orden_produccion_id == orden_id)
    )
    return _scope_consumos(query, usuario).all()
# ------------------------------------------------------------
# Servicios para Mano de Obra
# ------------------------------------------------------------
def obtener_mano_obra(db: Session, id_mano_obra: int, usuario: Usuario | None = None):
    query = db.query(ManoObra).filter(ManoObra.id == id_mano_obra)
    return _scope_mano_obras(query, usuario).first()


def crear_mano_obra(db: Session, esquema: ManoObraCreate, usuario: Usuario | None = None):
    etapa = _scope_stages(
        db.query(EtapaProduccion).filter(EtapaProduccion.id == esquema.etapa_produccion_id),
        usuario,
    ).first()
    if not etapa:
        raise ValueError("La etapa de producción especificada no existe o no está disponible para este usuario.")
    if etapa.estado != "EN_PROCESO":
        raise ValueError(
            f"No se puede registrar mano de obra en una etapa en estado '{etapa.estado}'. "
            "La etapa debe estar EN_PROCESO."
        )
    # Tarifa del listado de costos de producción (trazabilidad opcional).
    precio_produccion_id = getattr(esquema, "precio_produccion_id", None)
    if precio_produccion_id is not None:
        from app.modules.costos_produccion.model import PrecioProduccion
        tarifa = db.query(PrecioProduccion).filter(PrecioProduccion.id == precio_produccion_id).first()
        if not tarifa:
            raise ValueError(f"El costo de producción #{precio_produccion_id} no existe.")
    db_mano_obra = ManoObra(
        etapa_produccion_id=esquema.etapa_produccion_id,
        empleado_id=esquema.empleado_id,
        monto=esquema.monto,
        porcentaje_recargo=esquema.porcentaje_recargo,
        pagado=getattr(esquema, "pagado", False),
        observaciones=esquema.observaciones,
        precio_produccion_id=precio_produccion_id,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_mano_obra)
    db.flush()
    record_event(
        db, actor=usuario, action="CREATE", entity_type="mano_obra",
        entity_id=db_mano_obra.id,
        after={"empleado_id": db_mano_obra.empleado_id, "monto": float(db_mano_obra.monto), "etapa_produccion_id": db_mano_obra.etapa_produccion_id},
    )
    db.commit()
    db.refresh(db_mano_obra)
    return db_mano_obra


def _egreso_mano_obra(db: Session, db_mano: ManoObra, pagado: bool):
    """Crea/elimina el egreso de mano de obra (solo cambia el bool no contaba
    como egreso en el P&L; ahora el pago efectiviza el gasto)."""
    from app.modules.gastos.model import Gasto
    marcador = f"[mano_obra {db_mano.id}]"
    if pagado:
        tipo_gasto = db.query(TipoGasto).filter(
            TipoGasto.nombre == "Mano de Obra de Producción"
        ).first()
        if not tipo_gasto:
            return
        existe = db.query(Gasto).filter(Gasto.observaciones.like(f"%{marcador}%")).first()
        if existe:
            return
        recargo = Decimal(str(db_mano.porcentaje_recargo or 0)) / Decimal("100")
        monto = _redondear2(Decimal(str(db_mano.monto)) * (Decimal("1") + recargo))
        db.add(Gasto(
            tipo_gasto_id=tipo_gasto.id,
            moneda_id=1,
            fecha=date.today(),
            descripcion=f"Mano de obra #{db_mano.id} - Etapa #{db_mano.etapa_produccion_id}",
            monto=monto,
            tasa_cambio=Decimal("1.0"),
            monto_en_moneda_base=monto,
            observaciones=f"Generado automáticamente al marcar pagada la mano de obra {marcador}",
        ))
    else:
        db.query(Gasto).filter(Gasto.observaciones.like(f"%{marcador}%")).delete(synchronize_session=False)


def marcar_mano_obra_pagada(db: Session, mano_obra_id: int, pagado: bool = True, usuario: Usuario | None = None):
    db_mano = obtener_mano_obra(db, mano_obra_id, usuario)
    if not db_mano:
        return None
    db_mano.pagado = pagado
    _egreso_mano_obra(db, db_mano, pagado)
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="mano_obra",
        entity_id=mano_obra_id,
        after={"pagado": pagado},
    )
    db.commit()
    db.refresh(db_mano)
    return db_mano


def eliminar_mano_obra(db: Session, id_mano_obra: int, usuario: Usuario | None = None):
    db_mano = obtener_mano_obra(db, id_mano_obra, usuario)
    if not db_mano:
        return False
    if db_mano.pagado:
        raise ValueError(
            "No se puede eliminar una mano de obra ya pagada (su egreso está "
            "registrado en Gastos). Revierta el pago antes de eliminarla."
        )
    record_event(
        db, actor=usuario, action="DELETE", entity_type="mano_obra",
        entity_id=id_mano_obra,
        before={"empleado_id": db_mano.empleado_id, "monto": float(db_mano.monto)},
    )
    db.delete(db_mano)
    db.commit()
    return True
# ------------------------------------------------------------
# Servicios para Costo de Producción (Lógica Financiera)
# ------------------------------------------------------------
def obtener_costo_por_orden(db: Session, orden_id: int, usuario: Usuario | None = None):
    query = db.query(CostoProduccion).filter(CostoProduccion.orden_produccion_id == orden_id)
    if usuario is not None and not tiene_alcance_total(usuario):
        query = query.join(CostoProduccion.orden).filter(OrdenProduccion.creado_por_id == usuario.id)
    return query.first()


def calcular_y_guardar_costo(db: Session, orden_id: int, ganancia_porcentaje: float = 0.0, costo_gastos: float = 0.0, precio_impuestos_base: float = 0.0):
    # FOR UPDATE: serializa los cálculos concurrentes sobre la misma orden para
    # que el get-or-create de CostoProduccion no genere duplicados.
    orden = db.query(OrdenProduccion).filter(OrdenProduccion.id == orden_id).with_for_update().first()
    if not orden:
        raise ValueError("La orden de produccion especificada no existe.")
    # Calcular costo de materiales (todo en Decimal: los floats de los esquemas
    # se convierten una sola vez y el cálculo no acumula errores de redondeo).
    consumos = obtener_consumos_por_orden(db, orden_id)
    costo_material = Decimal("0")
    for c in consumos:
        costo_u = c.costo_unitario
        if costo_u is None:
            # Fallback a costo_base si no está congelado (para registros antiguos)
            material = db.query(Material).filter(Material.id == c.material_id).first()
            costo_u = material.costo_base if material else Decimal("0")
        costo_material += Decimal(str(c.cantidad)) * Decimal(str(costo_u))
    # Calcular costo de mano de obra
    mano_obras = db.query(ManoObra).join(EtapaProduccion).filter(EtapaProduccion.orden_produccion_id == orden_id).all()
    costo_mano_obra = Decimal("0")
    for mo in mano_obras:
        recargo = Decimal(str(mo.porcentaje_recargo)) / Decimal("100") if mo.porcentaje_recargo else Decimal("0")
        costo_mano_obra += Decimal(str(mo.monto)) * (Decimal("1") + recargo)
    # Calcular costo total y precio de venta
    costo_total = costo_material + costo_mano_obra + Decimal(str(costo_gastos))
    ganancia_factor = Decimal(str(ganancia_porcentaje)) / Decimal("100")
    precio_venta_calculado = _redondear2(
        costo_total * (Decimal("1") + ganancia_factor) + Decimal(str(precio_impuestos_base))
    )
    # Buscar o crear registro de CostoProduccion
    db_costo = obtener_costo_por_orden(db, orden_id)
    if not db_costo:
        db_costo = CostoProduccion(orden_produccion_id=orden_id)
        db.add(db_costo)
    db_costo.costo_material = _redondear2(costo_material)
    db_costo.costo_mano_obra = _redondear2(costo_mano_obra)
    db_costo.costo_gastos = Decimal(str(costo_gastos))
    db_costo.precio_impuestos_base = Decimal(str(precio_impuestos_base))
    db_costo.ganancia_porcentaje = Decimal(str(ganancia_porcentaje))
    db_costo.costo_total = _redondear2(costo_total)
    db_costo.precio_venta_calculado = precio_venta_calculado
    db.commit()
    db.refresh(db_costo)
    return db_costo
