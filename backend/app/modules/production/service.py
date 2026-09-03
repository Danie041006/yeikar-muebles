from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, exists
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)
from app.modules.production.model import (
    TIPO_PEDIDO, TIPO_EXHIBICION, TIPO_STOCK, TIPOS_ORDEN,
    OrdenProduccion, EtapaProduccion, ConsumoMaterial, ManoObra, CostoProduccion,
    ProductoCrudoInventario, ProduccionCrudo, ProduccionCrudoConsumo,
    ProduccionCrudoManoObra, ProduccionCrudoUso,
)
from app.modules.production.schemas import (
    OrdenProduccionCreate, OrdenProduccionUpdate,
    EtapaProduccionCreate, EtapaProduccionUpdate,
    ConsumoMaterialCreate, ConsumoConfirmarCreate, ManoObraCreate, CostoProduccionCreate,
    CrudoCreate, ProduccionCrudoCreate, ProduccionCrudoEstadoUpdate, CrudoConsumoCreate,
    ProduccionCrudoManoObraCreate, ProduccionCrudoManoObraUpdate
)
from app.modules.orders.model import DetallePedido
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.productos.model import Material, Producto, ProductoMaterial, ReglaGastoSeccion
from app.modules.empleados.model import Empleado
from app.modules.clients.model import Client
from app.modules.catalogos.model import Ubicacion, TipoGasto, Area
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
from app.modules.production.unidades import resolver_cantidad_consumo, nota_captura


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
        "producto_id": orden.producto_id,
        "es_stock": orden.es_stock,
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
def _validar_tipo_solicitado(tipo_solicitado: str | None, tipo_derivado: str) -> str:
    """El tipo lo determina el destino real de la orden (pedido vs producto en
    catálogo). Si el cliente envía uno explícito debe coincidir: evita órdenes
    mal etiquetadas (p. ej. una exhibición sin producto de exhibición)."""
    if tipo_solicitado is None:
        return tipo_derivado
    if tipo_solicitado not in TIPOS_ORDEN:
        raise ValueError(
            f"Tipo de orden inválido: {tipo_solicitado}. "
            f"Debe ser uno de: {', '.join(TIPOS_ORDEN)}."
        )
    if tipo_solicitado != tipo_derivado:
        raise ValueError(
            f"El tipo de esta orden debe ser '{tipo_derivado}' según su destino "
            f"(se recibió '{tipo_solicitado}')."
        )
    return tipo_derivado


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

    # Órdenes de STOCK (producir "en crudo" sin un pedido): requieren producto.
    if esquema.es_stock:
        if not esquema.producto_id:
            raise ValueError("Para crear una orden de stock (en crudo) debe indicar el producto_id.")
        producto = db.query(Producto).filter(Producto.id == esquema.producto_id).first()
        if not producto:
            raise ValueError("El producto especificado no existe.")
        if producto.es_reventa:
            raise ValueError(
                f"El producto '{producto.nombre}' es de reventa: no se fabrica en crudo."
            )
        db_orden = OrdenProduccion(
            detalle_pedido_id=None,
            producto_id=esquema.producto_id,
            estado=esquema.estado,
            fecha_inicio=esquema.fecha_inicio,
            fecha_fin=esquema.fecha_fin,
            es_stock=True,
            tipo=_validar_tipo_solicitado(
                esquema.tipo,
                TIPO_EXHIBICION if producto.es_exhibicion else TIPO_STOCK,
            ),
            creado_por_id=usuario.id if usuario is not None else None,
            actualizado_por_id=usuario.id if usuario is not None else None,
        )
        db.add(db_orden)
        db.flush()
        record_event(db, actor=usuario, action="CREATE", entity_type="orden_produccion", entity_id=db_orden.id, after=_snapshot_orden(db_orden))
        db.commit()
        db.refresh(db_orden)
        return db_orden

    if not esquema.detalle_pedido_id:
        raise ValueError("Debe indicar el detalle de pedido (o marcar es_stock=True para producir en crudo).")
    detalle_query = db.query(DetallePedido).join(Pedido, Pedido.id == DetallePedido.pedido_id).filter(
        DetallePedido.id == esquema.detalle_pedido_id
    )
    if usuario is not None and not tiene_alcance_total(usuario):
        detalle_query = detalle_query.filter(Pedido.creado_por_id == usuario.id)
    # Los productos de REVENTA no se fabrican: se venden del inventario.
    _detalle = detalle_query.first()
    if not _detalle:
        raise ValueError("El detalle de pedido no existe o no está disponible para este usuario.")
    if _detalle.producto is not None and (_detalle.producto.es_reventa or _detalle.producto.es_exhibicion):
        raise ValueError(
            f"El producto '{_detalle.producto.nombre}' no entra a producción desde un pedido. "
            "Su venta descuenta stock del inventario al facturar."
        )

    db_orden = OrdenProduccion(
        detalle_pedido_id=esquema.detalle_pedido_id,
        estado=esquema.estado,
        fecha_inicio=esquema.fecha_inicio,
        fecha_fin=esquema.fecha_fin,
        es_stock=False,
        tipo=_validar_tipo_solicitado(esquema.tipo, TIPO_PEDIDO),
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

    # Los productos de REVENTA y de EXHIBICIÓN no se fabrican desde un pedido:
    # se venden del inventario. Nunca deben entrar al tablero de producción
    # por esta vía (una pieza de exhibición ya se fabricó; si se necesita otra,
    # se registra como pieza nueva y se produce como orden de stock).
    if detalle.producto is not None and (detalle.producto.es_reventa or detalle.producto.es_exhibicion):
        raise ValueError(
            f"El producto '{detalle.producto.nombre}' no entra a producción desde un pedido. "
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
        tipo=TIPO_PEDIDO,
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

        # ── Estructura de costes desde producción ──
        # Si el producto NO tiene estructura, se genera con lo que se usó de
        # verdad (consumos + mano de obra). Nunca pisa estructuras existentes
        # y un fallo aquí NO bloquea la finalización de la orden.
        estructura_generada = False
        try:
            from app.modules.production.estructura_generador import _producto_de_orden, generar_estructura_desde_orden
            estructura_generada = generar_estructura_desde_orden(db, id_orden)
            db.flush()
            if estructura_generada:
                # El costo recién generado se vuelve el costo base del producto
                # (precio_costo_base / precio_venta_base): insumos + producción
                # con su recargo + gastos por sección, como en el Excel.
                producto_gen = _producto_de_orden(db, db_orden)
                if producto_gen:
                    from app.modules.productos.cost_service import actualizar_snapshot_desde_estructura
                    actualizar_snapshot_desde_estructura(db, producto_gen.id)
                    db.flush()
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo generar la estructura de costes desde la orden #%s", id_orden)
            estructura_generada = False

        db.flush()

        # ── Pieza de exhibición: al finalizar, entra al stock del showroom ──
        # La orden EXHIBICION genera la ENTRADA automática en la ubicación
        # EXHIBICIÓN con el costo real de producción. Idempotente: la
        # referencia marca que ya se contabilizó.
        if db_orden.tipo == TIPO_EXHIBICION and db_orden.producto_id:
            from app.modules.inventory.model import MovimientoProductoInventario
            ya_contado = db.query(MovimientoProductoInventario.id).filter(
                MovimientoProductoInventario.producto_id == db_orden.producto_id,
                MovimientoProductoInventario.tipo == "ENTRADA",
                MovimientoProductoInventario.referencia_tipo == "PRODUCCION_EXHIBICION",
                MovimientoProductoInventario.referencia_id == id_orden,
            ).first()
            if not ya_contado:
                pieza = db.query(Producto).filter(Producto.id == db_orden.producto_id).first()
                ubi = db.query(Ubicacion).filter(Ubicacion.nombre == "EXHIBICIÓN").first()
                costo_orden = obtener_costo_por_orden(db, id_orden)
                costo_total_cop = costo_orden.costo_total if costo_orden else Decimal("0")
                # costo_promedio vive en la moneda del producto (igual que las
                # compras de reventa y las altas manuales), pero el costo de la
                # producción se calcula en moneda base (COP): se convierte.
                from app.modules.productos.service import convertir_desde_moneda_base
                costo_pieza = (
                    convertir_desde_moneda_base(db, pieza.moneda_id, float(costo_total_cop))
                    if pieza and costo_total_cop > 0
                    else None
                )
                if ubi:
                    from app.modules.inventory.service import registrar_movimiento_producto
                    from app.modules.inventory.schemas import MovimientoProductoCreate
                    registrar_movimiento_producto(
                        db,
                        MovimientoProductoCreate(
                            producto_id=db_orden.producto_id,
                            ubicacion_id=ubi.id,
                            tipo="ENTRADA",
                            cantidad=Decimal("1"),
                            costo_unitario=costo_pieza,
                            referencia_tipo="PRODUCCION_EXHIBICION",
                            referencia_id=id_orden,
                            observaciones=f"Producción de pieza de exhibición (orden #{id_orden})",
                        ),
                        usuario=usuario,
                    )
                    db.flush()

        db.flush()

        # Sincronizar estado del Pedido a TERMINADO si TODAS las líneas del pedido
        # tienen una orden de producción FINALIZADA (no solo las que tienen orden).
        # FOR UPDATE sobre el pedido: dos finalizaciones simultáneas de órdenes del
        # mismo pedido se serializan, evitando que ambas lean "no todas finalizadas"
        # y que el pedido nunca pase a TERMINADO (o que se cree envío dos veces).
        # IMPORTANTE: la sesión usa autoflush=False; el flush garantiza que el
        # estado recién asignado (FINALIZADA) sea visible para el count() que
        # decide si el pedido pasa a TERMINADO (antes contaba 0 siempre y la
        # cadena producción→terminado→envío estaba rota en silencio).
        detalle = db.query(DetallePedido).filter(DetallePedido.id == db_orden.detalle_pedido_id).first()
        if detalle:
            pedido = db.query(Pedido).filter(Pedido.id == detalle.pedido_id).with_for_update().first()
            if pedido:
                # C3: TODAS las líneas FABRICABLES del pedido deben tener su orden
                # FINALIZADA. Las de REVENTA/INSUMO/EXHIBICIÓN no entran a
                # producción (se venden/despachan del inventario), así que no
                # bloquean el cierre: igual que la ruta manual de actualizar_pedido.
                # (Antes contaba TODAS las líneas: un pedido mixto nunca terminaba.)
                n_detalles = db.query(DetallePedido).filter(
                    DetallePedido.pedido_id == pedido.id,
                    or_(
                        DetallePedido.tipo_item == "FABRICADO",
                        DetallePedido.tipo_item.is_(None),
                    ),
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
    # Atributo transitorio para la API (no es columna): avisa a la UI si la
    # estructura de costes del producto se generó al finalizar.
    db_orden.estructura_generada = estructura_generada if nuevo_estado == 'FINALIZADA' else None
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
    corte_activo = bool(getattr(esquema, "ancho_corte_cm", None) and getattr(esquema, "largo_corte_cm", None))
    lamina_completa = bool(getattr(esquema, "es_lamina_completa", False))
    # 4.0 El consumo por corte de láminas NO admite captura flexible: ahí la
    #     cantidad es N.º de cortes y el motor de láminas hace su propia math.
    if corte_activo and (
        esquema.unidad_captura or esquema.pieza_largo or esquema.pieza_ancho or esquema.pieza_espesor
    ):
        raise ValueError("El consumo por corte de láminas no admite captura en cm ni por pieza.")
    # 4.0.0 Pedido de LÁMINA COMPLETA: sale la lámina entera hoy (stock apartado,
    #     costo provisional N × costo_base) y queda PENDIENTE hasta confirmar por
    #     cortes cuánto se usó. El corte NO se digita aquí (se confirma después).
    if lamina_completa:
        if corte_activo:
            raise ValueError("El modo lámina completa no admite medidas de corte: se confirman después.")
        if (
            esquema.unidad_captura or esquema.pieza_largo or esquema.pieza_ancho or esquema.pieza_espesor
        ):
            raise ValueError("El pedido de láminas completas no admite captura en cm ni por pieza.")
        if not material.largo_cm or not material.ancho_cm:
            raise ValueError(
                f"El material '{material.nombre}' no tiene dimensiones de lámina (largo_cm/ancho_cm). "
                "Configúralas en Productos para pedirlo por láminas completas."
            )
        cantidad_base = Decimal(str(esquema.cantidad))  # N.º de láminas enteras
    else:
        # 4.0.1 Captura flexible: convertir a la unidad base del material ANTES de
        #     descontar inventario o costear (cm→m; pieza L×A×E → m³ con la
        #     fórmula de la casa). Punto único de conversión: production/unidades.py
        cantidad_base = resolver_cantidad_consumo(
            material,
            esquema.cantidad,
            esquema.unidad_captura,
            esquema.pieza_largo,
            esquema.pieza_ancho,
            esquema.pieza_espesor,
        )
    db_consumo = ConsumoMaterial(
        etapa_produccion_id=esquema.etapa_produccion_id,
        material_id=esquema.material_id,
        cantidad=cantidad_base,
        costo_unitario=material.costo_base,
        seccion=seccion,
        estado="PENDIENTE" if lamina_completa else "CONFIRMADO",
        ancho_corte_cm=Decimal(str(esquema.ancho_corte_cm)) if corte_activo else None,
        largo_corte_cm=Decimal(str(esquema.largo_corte_cm)) if corte_activo else None,
        origen_sobrante_id=esquema.origen_sobrante_id if corte_activo else None,
        unidad_captura=esquema.unidad_captura,
        pieza_largo=Decimal(str(esquema.pieza_largo)) if esquema.pieza_largo else None,
        pieza_ancho=Decimal(str(esquema.pieza_ancho)) if esquema.pieza_ancho else None,
        pieza_espesor=Decimal(str(esquema.pieza_espesor)) if esquema.pieza_espesor else None,
        componente=(esquema.componente or "").strip().upper() or None,
        es_excedente=bool(getattr(esquema, "es_excedente", False)),
        motivo_exceso=(esquema.motivo_exceso or "").strip().upper() or None,
        solicitante_empleado_id=solicitante.id,
        creado_por_id=usuario.id if usuario is not None else None,
        fecha=esquema.fecha,
        observaciones=esquema.observaciones
    )
    db.add(db_consumo)
    db.flush()  # para obtener db_consumo.id
    # 4. Registrar el movimiento de inventario (SALIDA)
    if lamina_completa:
        # Pedido de láminas enteras: SALIDA simple de N láminas. El costo es
        # PROVISIONAL (N × costo_base); el real se fija al confirmar por cortes.
        movimiento = MovimientoCreate(
            material_id=esquema.material_id,
            ubicacion_id=ubicacion_id,
            tipo="SALIDA",
            cantidad=cantidad_base,
            referencia_tipo="produccion",
            referencia_id=db_consumo.id,
            observaciones=f"Pedido de {cantidad_base.normalize()} lámina(s) completa(s) en etapa "
                          f"{esquema.etapa_produccion_id} — Solicitante: {solicitante.nombre} "
                          "(pendiente de confirmar uso)"
        )
        try:
            registrar_movimiento(db, movimiento)
        except ValueError as e:
            db.rollback()
            raise ValueError(f"Error al descontar inventario: {e}")
        costo_total_consumo = cantidad_base * material.costo_base
        detalle_corte = None
    elif corte_activo:
        # Material laminar: consumo por CORTES con registro de sobrantes.
        # El movimiento de SALIDA (láminas enteras) lo genera consumir_por_cortes.
        from app.modules.inventory.cortes_service import consumir_por_cortes
        try:
            resultado_corte = consumir_por_cortes(
                db,
                material=material,
                cantidad_cortes=esquema.cantidad,
                largo_corte_cm=esquema.largo_corte_cm,
                ancho_corte_cm=esquema.ancho_corte_cm,
                ubicacion_id=ubicacion_id,
                referencia_tipo="produccion",
                referencia_id=db_consumo.id,
                consumo_origen_tipo="produccion",
                origen_sobrante_id=esquema.origen_sobrante_id,
                sobrante_largo_cm=getattr(esquema, "sobrante_largo_cm", None),
                sobrante_ancho_cm=getattr(esquema, "sobrante_ancho_cm", None),
            )
        except ValueError as e:
            db.rollback()
            raise ValueError(f"Error al descontar inventario: {e}")
        db_consumo.costo_unitario = resultado_corte["costo_unitario"]
        db_consumo.laminas_consumidas = resultado_corte["laminas_consumidas"]
        costo_total_consumo = resultado_corte["costo_total"]
        detalle_corte = resultado_corte["detalle"]
    else:
        movimiento = MovimientoCreate(
            material_id=esquema.material_id,
            ubicacion_id=ubicacion_id,
            tipo="SALIDA",
            cantidad=cantidad_base,
            referencia_tipo="produccion",
            referencia_id=db_consumo.id,
            observaciones=f"Consumo en etapa {esquema.etapa_produccion_id} — Solicitante: {solicitante.nombre}"
        )
        try:
            registrar_movimiento(db, movimiento)
        except ValueError as e:
            db.rollback()
            raise ValueError(f"Error al descontar inventario: {e}")
        costo_total_consumo = cantidad_base * material.costo_base
        detalle_corte = None

    tipo_gasto_consumo = db.query(TipoGasto).filter(
        TipoGasto.nombre == "Consumo de Materia Prima en Producción"
    ).first()
    if tipo_gasto_consumo:
        costo_total = costo_total_consumo
        from app.modules.gastos.model import Gasto
        if lamina_completa:
            descripcion_gasto = (
                f"Pedido lámina {material.nombre} ({cantidad_base.normalize()} lámina(s)) - "
                f"Etapa #{esquema.etapa_produccion_id} — Solicita: {solicitante.nombre} "
                "(uso pendiente de confirmar)"
            )
        else:
            descripcion_gasto = f"Consumo {material.nombre} ({cantidad_base}) - Etapa #{esquema.etapa_produccion_id} — Solicita: {solicitante.nombre}"
        nota = nota_captura(
            esquema.cantidad, esquema.unidad_captura,
            esquema.pieza_largo, esquema.pieza_ancho, esquema.pieza_espesor,
        )
        if nota:
            descripcion_gasto += f" — {nota}"
        if detalle_corte:
            descripcion_gasto += f" — {detalle_corte}"
        db_gasto = Gasto(
            tipo_gasto_id=tipo_gasto_consumo.id,
            moneda_id=1,
            fecha=esquema.fecha or date.today(),
            descripcion=descripcion_gasto,
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
            "captura": nota_captura(
                esquema.cantidad, esquema.unidad_captura,
                esquema.pieza_largo, esquema.pieza_ancho, esquema.pieza_espesor,
            ),
            "etapa_produccion_id": db_consumo.etapa_produccion_id,
            "solicitante_empleado_id": db_consumo.solicitante_empleado_id,
            "solicitante": solicitante.nombre,
        },
    )
    db.commit()
    db.refresh(db_consumo)
    return db_consumo


def confirmar_consumo_material(
    db: Session,
    id_consumo: int,
    esquema: ConsumoConfirmarCreate,
    usuario: Usuario | None = None,
):
    """Confirma el uso real de una lámina pedida completa: N cortes de L×A cm
    salieron de las láminas. Recalcula el costo real (proporcional al área de
    corte), devuelve al depósito las láminas que no se abrieron (o descuenta
    las que falten, validando stock), crea el sobrante reutilizable y ajusta
    el gasto automático. El consumo pasa de PENDIENTE a CONFIRMADO.

    No bloquea nada: puede confirmarse aunque la etapa esté COMPLETADA o la
    orden FINALIZADA (el costo real se congela al confirmar).
    """
    from app.modules.inventory import laminas
    from app.modules.inventory.model import Inventario, SobranteLamina

    db_consumo = obtener_consumo_material(db, id_consumo, usuario)
    if not db_consumo:
        raise ValueError("El consumo no existe o no está disponible para este usuario.")
    if db_consumo.estado != "PENDIENTE":
        raise ValueError(
            f"El consumo #{id_consumo} no está pendiente de confirmación (estado '{db_consumo.estado}')."
        )

    material = db.query(Material).filter(Material.id == db_consumo.material_id).first()
    if not material:
        raise ValueError("El material del consumo ya no existe.")
    if not material.largo_cm or not material.ancho_cm:
        raise ValueError(
            f"El material '{material.nombre}' no tiene dimensiones de lámina (largo_cm/ancho_cm). "
            "Configúralas en Productos para confirmar el uso."
        )

    lc, ac = laminas.validar_corte(material, esquema.largo_corte_cm, esquema.ancho_corte_cm)
    cantidad_cortes = Decimal(str(esquema.cantidad_cortes))
    if cantidad_cortes <= 0:
        raise ValueError("El número de cortes debe ser mayor que cero.")

    por_lamina = laminas.cortes_que_caban(material.largo_cm, material.ancho_cm, lc, ac)
    if por_lamina == 0:
        raise ValueError(
            f"Un corte de {lc.normalize()}×{ac.normalize()} cm no cabe en la lámina de "
            f"{material.largo_cm.normalize()}×{material.ancho_cm.normalize()} cm de '{material.nombre}'."
        )
    n_laminas = Decimal(laminas.laminas_necesarias(cantidad_cortes, por_lamina))

    area_corte = lc * ac
    area_lamina = Decimal(str(material.largo_cm)) * Decimal(str(material.ancho_cm))
    costo_unit = laminas.costo_por_corte(material.costo_base, area_corte, area_lamina)
    costo_total = (costo_unit * cantidad_cortes).quantize(Decimal("0.01"))

    # ── Ajuste de stock: láminas pedidas vs. láminas que realmente se abren ──
    ubicacion = db.query(Ubicacion).filter(Ubicacion.nombre == "Depósito Principal").first()
    ubicacion_id = ubicacion.id if ubicacion else 1
    pedidas = Decimal(str(db_consumo.cantidad))
    diferencia = pedidas - n_laminas
    if diferencia > 0:
        # Se pidieron láminas de más: las que no se abrieron vuelven al depósito.
        registrar_movimiento(db, MovimientoCreate(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            tipo="ENTRADA",
            cantidad=diferencia,
            referencia_tipo="produccion",
            referencia_id=db_consumo.id,
            observaciones=f"Confirmación de consumo #{db_consumo.id}: devolución de "
                          f"{diferencia.normalize()} lámina(s) no abierta(s) "
                          f"(cortes {lc.normalize()}×{ac.normalize()} cm, {por_lamina} por lámina)",
        ))
    elif diferencia < 0:
        # Faltan láminas: validar stock antes de descontar las que falten.
        faltan = -diferencia
        stock = db.query(Inventario).filter(
            Inventario.material_id == material.id,
            Inventario.ubicacion_id == ubicacion_id,
        ).first()
        disponible = Decimal(str(stock.cantidad)) if stock else Decimal("0")
        if disponible < faltan:
            raise ValueError(
                f"Los cortes necesitan {n_laminas.normalize()} lámina(s) y se pidieron "
                f"{pedidas.normalize()}: faltan {faltan.normalize()}. "
                f"Stock disponible: {disponible.normalize()}."
            )
        registrar_movimiento(db, MovimientoCreate(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            tipo="SALIDA",
            cantidad=faltan,
            referencia_tipo="produccion",
            referencia_id=db_consumo.id,
            observaciones=f"Confirmación de consumo #{db_consumo.id}: lámina(s) adicional(es) "
                          f"para cortes {lc.normalize()}×{ac.normalize()} cm",
        ))

    # ── Sobrante del pedazo restante de la ÚLTIMA lámina abierta ──
    cortes_en_ultima = cantidad_cortes - (n_laminas - 1) * por_lamina
    area_restante = area_lamina - cortes_en_ultima * area_corte
    dims = None
    if esquema.sobrante_largo_cm and esquema.sobrante_ancho_cm:
        dims = (Decimal(str(esquema.sobrante_largo_cm)), Decimal(str(esquema.sobrante_ancho_cm)))
    else:
        dims = laminas.proponer_sobrante(material.largo_cm, material.ancho_cm, area_restante)
    if dims is not None:
        db.add(SobranteLamina(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            largo_cm=dims[0],
            ancho_cm=dims[1],
            estado="DISPONIBLE",
            consumo_origen_id=db_consumo.id,
            consumo_origen_tipo="produccion",
            observaciones=f"Restante de confirmar consumo #{db_consumo.id}: "
                          f"{cantidad_cortes.normalize()} corte(s) de {lc.normalize()}×{ac.normalize()} cm",
        ))
        db.flush()

    # ── Congelar el costo real y marcar CONFIRMADO ──
    db_consumo.cantidad = cantidad_cortes
    db_consumo.ancho_corte_cm = lc
    db_consumo.largo_corte_cm = ac
    db_consumo.costo_unitario = costo_unit
    db_consumo.laminas_consumidas = n_laminas
    db_consumo.estado = "CONFIRMADO"

    # ── Ajustar el gasto automático al monto real ──
    from app.modules.gastos.model import Gasto
    gasto = db.query(Gasto).filter(Gasto.observaciones.like(f"%[consumo {db_consumo.id}]%")).first()
    if gasto:
        gasto.monto = costo_total
        gasto.monto_en_moneda_base = costo_total
        gasto.descripcion = (
            f"Consumo {material.nombre} (Corte {cantidad_cortes.normalize()}x("
            f"{lc.normalize()}×{ac.normalize()} cm) — {n_laminas.normalize()} lámina(s))"
            f" - Etapa #{db_consumo.etapa_produccion_id} — Solicita: {db_consumo.solicitante_nombre or '—'}"
        )

    record_event(
        db, actor=usuario, action="UPDATE", entity_type="consumo_material",
        entity_id=db_consumo.id,
        after={
            "estado": "CONFIRMADO",
            "cantidad_cortes": float(cantidad_cortes),
            "largo_corte_cm": float(lc),
            "ancho_corte_cm": float(ac),
            "laminas_consumidas": float(n_laminas),
            "costo_total": float(costo_total),
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
    from app.modules.inventory import laminas as laminas_motor
    for pm in receta:
        mat = pm.material
        if not mat:
            continue
        cantidad = _calcular_cantidad_material(
            pm, nuevo_ancho, nuevo_largo, ancho_base, largo_base, area_base, area_nueva, None
        )
        item = {
            "material_id": mat.id,
            "nombre": mat.nombre,
            "seccion": _normalizar_seccion(pm.seccion),
            "tipo_escala": pm.tipo_escala or "FIJO",
            "condicion_cumplida": bool(cantidad > 0 or not pm.condicion_activacion),
            "cantidad_base": float(pm.cantidad_base),
            "cantidad_esperada": float(cantidad),
            "unidad": mat.unidad_medida.abreviatura if mat.unidad_medida else "",
            "costo_unitario": float(mat.costo_base),
        }
        if (pm.tipo_escala or "").upper() == "CORTE" and pm.ancho_corte_cm and pm.largo_corte_cm:
            item["es_corte"] = True
            item["ancho_corte_cm"] = float(pm.ancho_corte_cm)
            item["largo_corte_cm"] = float(pm.largo_corte_cm)
            if laminas_motor.es_laminar(mat):
                cpl = laminas_motor.cortes_que_caban(mat.largo_cm, mat.ancho_cm, pm.largo_corte_cm, pm.ancho_corte_cm)
                item["cortes_por_lamina"] = cpl
                area_corte = Decimal(str(pm.largo_corte_cm)) * Decimal(str(pm.ancho_corte_cm))
                area_lamina = Decimal(str(mat.largo_cm)) * Decimal(str(mat.ancho_cm))
                if area_lamina > 0:
                    item["laminas_equivalentes"] = float((cantidad * area_corte / area_lamina).quantize(Decimal("0.0001")))
                item["costo_por_corte"] = float(laminas_motor.costo_por_corte(mat.costo_base, area_corte, area_lamina)) if area_lamina > 0 else float(mat.costo_base)
        materiales.append(item)

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
    ubicacion_id = ubicacion.id if ubicacion else 1

    if db_consumo.largo_corte_cm and db_consumo.ancho_corte_cm:
        # Consumo por cortes: reversa exacta de láminas/sobrantes.
        from app.modules.inventory.cortes_service import revertir_consumo_por_cortes
        material_rev = db.query(Material).filter(Material.id == material_id).first()
        if material_rev is None:
            raise ValueError("El material del consumo ya no existe; no se puede revertir.")
        revertir_consumo_por_cortes(
            db,
            material=material_rev,
            consumo_id=db_consumo.id,
            consumo_tipo="produccion",
            cantidad_cortes=cantidad,
            largo_corte_cm=db_consumo.largo_corte_cm,
            ancho_corte_cm=db_consumo.ancho_corte_cm,
            origen_sobrante_id=db_consumo.origen_sobrante_id,
            laminas_consumidas=db_consumo.laminas_consumidas,
            ubicacion_id=ubicacion_id,
        )
    else:
        movimiento = MovimientoCreate(
            material_id=material_id,
            ubicacion_id=ubicacion_id,
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
        listo_nomina=getattr(esquema, "listo_nomina", True),
        observaciones=esquema.observaciones,
        precio_produccion_id=precio_produccion_id,
        creado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_mano_obra)
    db.flush()
    record_event(
        db, actor=usuario, action="CREATE", entity_type="mano_obra",
        entity_id=db_mano_obra.id,
        after={"empleado_id": db_mano_obra.empleado_id, "monto": float(db_mano_obra.monto), "etapa_produccion_id": db_mano_obra.etapa_produccion_id, "listo_nomina": db_mano_obra.listo_nomina},
    )
    db.commit()
    db.refresh(db_mano_obra)
    return db_mano_obra


def alternar_listo_nomina_mano_obra(db: Session, mano_obra_id: int, listo: bool, usuario: Usuario | None = None):
    db_mano = obtener_mano_obra(db, mano_obra_id, usuario)
    if not db_mano:
        return None
    db_mano.listo_nomina = listo
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="mano_obra",
        entity_id=mano_obra_id,
        after={"listo_nomina": listo},
    )
    db.commit()
    db.refresh(db_mano)
    return db_mano


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


def _costo_estimado_orden(db: Session, orden: OrdenProduccion) -> Optional[Decimal]:
    """Estimado del costo de la orden: precio_costo_base del producto (costo
    de producción del Excel) × unidades del detalle. None si el producto no
    tiene costo base (no hay estimado que comparar)."""
    producto = None
    unidades = Decimal("1")
    if orden.es_stock:
        producto = db.query(Producto).filter(Producto.id == orden.producto_id).first()
    elif orden.detalle_pedido_id:
        detalle = db.query(DetallePedido).filter(DetallePedido.id == orden.detalle_pedido_id).first()
        if detalle:
            producto = db.query(Producto).filter(Producto.id == detalle.producto_id).first()
            unidades = Decimal(str(detalle.cantidad or 1))
    if not producto or producto.precio_costo_base is None:
        return None
    return Decimal(str(producto.precio_costo_base)) * unidades


def costos_en_vivo_orden(db: Session, orden_id: int, usuario: Usuario | None = None) -> Optional[dict]:
    """Desglose de costos EN VIVO de una orden (vista estilo Excel, por sección):
    insumos + producción (base × recargo) + gastos de sección → total sección
    → TOTAL PRODUCCIÓN. Mismo criterio de agrupación que el generador de
    estructura (área de la etapa → sección, componente → "SECCIÓN (PIEZA)") y
    mismo recargo de producción (registrado o 8% por defecto). A diferencia de
    la estructura generada al finalizar, aquí NO se dividen las cantidades por
    unidad (es el costo acumulado de TODA la orden) y los excedentes/retrabajos
    SÍ aparecen (marcados): el taller debe ver todo lo que se está gastando.
    """
    from app.modules.production.estructura_generador import (
        RECARGO_PRODUCCION_PCT,
        _nombre_seccion,
        _pretty_seccion,
    )

    orden = obtener_orden_produccion(db, orden_id, usuario)
    if not orden:
        return None

    producto = None
    unidades = Decimal("1")
    dims = (orden.ancho, orden.largo)
    if orden.es_stock:
        producto = db.query(Producto).filter(Producto.id == orden.producto_id).first()
    else:
        detalle = db.query(DetallePedido).filter(DetallePedido.id == orden.detalle_pedido_id).first()
        if detalle:
            producto = db.query(Producto).filter(Producto.id == detalle.producto_id).first()
            unidades = Decimal(str(detalle.cantidad or 1))
            dims = (detalle.ancho, detalle.largo)

    etapas = (
        db.query(EtapaProduccion)
        .filter(EtapaProduccion.orden_produccion_id == orden_id)
        .order_by(EtapaProduccion.id)
        .all()
    )
    seccion_de_etapa = {
        e.id: _normalizar_seccion(e.area.nombre if e.area else None) for e in etapas
    }
    orden_secciones: list[str] = []
    for sec in seccion_de_etapa.values():
        if sec not in orden_secciones:
            orden_secciones.append(sec)

    # Consumos por (sección, componente) y mano de obra por sección.
    consumos_por_seccion: dict[tuple, list[ConsumoMaterial]] = {}
    for c in db.query(ConsumoMaterial).filter(
        ConsumoMaterial.etapa_produccion_id.in_([e.id for e in etapas])
    ).all():
        etapa = next((e for e in etapas if e.id == c.etapa_produccion_id), None)
        if not etapa:
            continue
        clave = (seccion_de_etapa.get(etapa.id, "EBANISTERIA"), c.componente or None)
        consumos_por_seccion.setdefault(clave, []).append(c)

    manos_por_seccion: dict[str, list[ManoObra]] = {}
    for mo in db.query(ManoObra).filter(
        ManoObra.etapa_produccion_id.in_([e.id for e in etapas])
    ).all():
        etapa = next((e for e in etapas if e.id == mo.etapa_produccion_id), None)
        if not etapa:
            continue
        manos_por_seccion.setdefault(seccion_de_etapa.get(etapa.id, "EBANISTERIA"), []).append(mo)

    # % de gastos por sección normalizada (regla global; default 10%).
    pct_gastos: dict[str, Decimal] = {
        r.seccion: Decimal(str(r.porcentaje_gasto)) for r in db.query(ReglaGastoSeccion).all()
    }

    claves_consumos = list(consumos_por_seccion.keys())
    claves_mo = [(sec, None) for sec in manos_por_seccion]
    claves_ordenadas = sorted(
        set(claves_consumos) | set(claves_mo),
        key=lambda c: (orden_secciones.index(c[0]) if c[0] in orden_secciones else 999, c[1] or ""),
    )

    secciones = []
    totales = {
        "materiales": Decimal("0"),
        "mano_obra": Decimal("0"),
        "gastos": Decimal("0"),
        "excedentes": Decimal("0"),
    }
    for pos, clave in enumerate(claves_ordenadas, start=1):
        sec_norm, comp = clave
        nombre = _nombre_seccion(sec_norm, comp)
        pct_g = pct_gastos.get(_normalizar_seccion(nombre), Decimal("10.00"))

        insumos = []
        etapa_por_id: dict[int, EtapaProduccion] = {e.id: e for e in etapas}
        for c in consumos_por_seccion.get(clave, []):
            etapa = etapa_por_id.get(c.etapa_produccion_id)
            costo_u = c.costo_unitario
            if costo_u is None:
                costo_u = c.material.costo_base if c.material else Decimal("0")
            cantidad = Decimal(str(c.cantidad))
            total = _redondear2(cantidad * Decimal(str(costo_u)))
            totales["materiales"] += total
            if c.es_excedente:
                totales["excedentes"] += total
            unidad = ""
            if c.material and c.material.unidad_medida:
                unidad = c.material.unidad_medida.abreviatura or c.material.unidad_medida.nombre
            insumos.append({
                "nombre": c.material.nombre if c.material else f"Material #{c.material_id}",
                "cantidad": float(cantidad),
                "unidad": unidad,
                "v_unit": float(costo_u),
                "total": float(total),
                "es_excedente": bool(c.es_excedente),
                "es_retrabajo": bool(etapa and etapa.es_retrabajo),
                "motivo": c.motivo_exceso or None,
            })

        # La mano de obra cae SOLO en la sección base de su área (sin
        # componente), igual que el generador de estructura: "EBANISTERÍA" y
        # no "EBANISTERÍA (NOCHEROS)".
        produccion = []
        etapa_retrabajo: dict[int, bool] = {e.id: bool(e.es_retrabajo) for e in etapas}
        for mo in (manos_por_seccion.get(sec_norm, []) if comp is None else []):
            base = Decimal(str(mo.monto))
            recargo = (
                Decimal(str(mo.porcentaje_recargo))
                if mo.porcentaje_recargo and Decimal(str(mo.porcentaje_recargo)) > 0
                else RECARGO_PRODUCCION_PCT
            )
            total_mo = _redondear2(base * (Decimal("1") + recargo / Decimal("100")))
            totales["mano_obra"] += total_mo
            produccion.append({
                "nombre": mo.precio_produccion_descripcion or _pretty_seccion(sec_norm),
                "base": float(base),
                "porcentaje": float(recargo),
                "total": float(total_mo),
                "es_retrabajo": etapa_retrabajo.get(mo.etapa_produccion_id, False),
            })

        subtotal = _redondear2(
            sum((Decimal(str(i["total"])) for i in insumos), Decimal("0"))
            + sum((Decimal(str(p["total"])) for p in produccion), Decimal("0"))
        )
        gasto_sec = _redondear2(subtotal * pct_g / Decimal("100")) if pct_g > 0 else Decimal("0")
        totales["gastos"] += gasto_sec
        total_seccion = subtotal + gasto_sec

        secciones.append({
            "nombre": nombre,
            "orden": pos,
            "insumos": insumos,
            "produccion": produccion,
            "subtotal": float(subtotal),
            "pct_gastos": float(pct_g),
            "gastos": float(gasto_sec),
            "total": float(total_seccion),
        })

    total_produccion = _redondear2(
        sum((Decimal(str(sec["total"])) for sec in secciones), Decimal("0"))
    )
    costo = obtener_costo_por_orden(db, orden_id, usuario)
    estimado = _costo_estimado_orden(db, orden)

    return {
        "orden_id": orden_id,
        "estado": orden.estado,
        "producto_id": producto.id if producto else None,
        "producto_nombre": producto.nombre if producto else None,
        "dimensiones": {"ancho": float(dims[0]) if dims[0] else None, "largo": float(dims[1]) if dims[1] else None},
        "unidades": float(unidades),
        "estimado": float(estimado) if estimado is not None else None,
        "costo_estimado": float(costo.costo_estimado) if costo and costo.costo_estimado is not None else None,
        "costo_real_total": float(costo.costo_total) if costo else None,
        "costo_real_precio_venta": float(costo.precio_venta_calculado) if costo else None,
        "costo_real_ganancia": float(costo.ganancia_porcentaje) if costo else None,
        "secciones": secciones,
        "total_produccion": float(total_produccion),
        "totales": {k: float(v) for k, v in totales.items()},
    }


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
    # Estimado congelado la primera vez (no se pisa si se recalcula): el
    # precio_costo_base del producto × unidades, para la comparativa vs real.
    if not db_costo.costo_estimado:
        estimado = _costo_estimado_orden(db, orden)
        if estimado is not None:
            db_costo.costo_estimado = _redondear2(estimado)
    db.commit()
    db.refresh(db_costo)
    return db_costo


# ------------------------------------------------------------
# Productos en Crudo (ítem libre: catálogo + stock)
# ------------------------------------------------------------
def _ubicacion_deposito(db) -> int:
    u = db.query(Ubicacion).filter(Ubicacion.nombre == "Depósito Principal").first()
    return u.id if u else 1


def _area_default(db) -> Optional[int]:
    a = db.query(Area).filter(Area.nombre.ilike("%Ebanister%")).first()
    return a.id if a else None


def _tipo_gasto(db, nombre: str, categoria: str = "OPERATIVO"):
    """Busca un TipoGasto por nombre y lo crea (categoría OPERATIVO) si no existe,
    evitando egresos que fallan en silencio cuando el tipo aún no está sembrado."""
    tg = db.query(TipoGasto).filter(TipoGasto.nombre == nombre).first()
    if not tg:
        tg = TipoGasto(nombre=nombre, categoria=categoria)
        db.add(tg)
        db.flush()
    return tg


def _foto_crudo(db, crudo_id) -> Optional[str]:
    from app.modules.adjuntos.service import adjuntos_info
    info = adjuntos_info(db, "CRUDO", crudo_id)
    return info[0]["url"] if info else None


def crear_crudo(db, esquema: CrudoCreate, usuario=None):
    nombre = (esquema.nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del producto en crudo es obligatorio.")
    crudo = ProductoCrudoInventario(
        nombre=nombre,
        area_id=esquema.area_id if esquema.area_id else _area_default(db),
        ubicacion_id=esquema.ubicacion_id or _ubicacion_deposito(db),
        cantidad=Decimal(str(esquema.cantidad or 0)),
        activo=True,
    )
    db.add(crudo)
    record_event(
        db, actor=usuario, action="CREATE", entity_type="producto_crudo", entity_id=crudo.id,
        after={"nombre": nombre, "cantidad": float(crudo.cantidad)},
    )
    db.commit()
    db.refresh(crudo)
    crudo.foto_url = _foto_crudo(db, crudo.id)
    return crudo


def listar_crudos(db, activo=None, usuario=None):
    q = db.query(ProductoCrudoInventario).options(joinedload(ProductoCrudoInventario.area))
    if activo is not None:
        q = q.filter(ProductoCrudoInventario.activo.is_(activo))
    crudos = q.order_by(ProductoCrudoInventario.id.desc()).all()
    for c in crudos:
        c.foto_url = _foto_crudo(db, c.id)
    return crudos


def obtener_crudo(db, crudo_id, usuario=None):
    c = (
        db.query(ProductoCrudoInventario)
        .options(joinedload(ProductoCrudoInventario.area))
        .filter(ProductoCrudoInventario.id == crudo_id)
        .first()
    )
    if not c:
        return None
    c.foto_url = _foto_crudo(db, c.id)
    return c


# ------------------------------------------------------------
# Producción de Crudos (segunda producción)
# ------------------------------------------------------------
def crear_produccion_crudo(db, esquema: ProduccionCrudoCreate, usuario=None):
    crudo = db.query(ProductoCrudoInventario).filter(ProductoCrudoInventario.id == esquema.crudo_id).first()
    if not crudo:
        raise ValueError("El ítem en crudo especificado no existe.")
    if not crudo.activo:
        raise ValueError("El ítem en crudo está desactivado.")
    pc = ProduccionCrudo(
        crudo_id=crudo.id,
        estado="PENDIENTE",
        cantidad=Decimal(str(esquema.cantidad or 1)),
        costo_total=Decimal("0"),
        observaciones=esquema.observaciones,
        creado_por_id=usuario.id if usuario else None,
        actualizado_por_id=usuario.id if usuario else None,
    )
    db.add(pc)
    record_event(
        db, actor=usuario, action="CREATE", entity_type="produccion_crudo", entity_id=pc.id,
        after={"crudo_id": crudo.id, "estado": pc.estado},
    )
    db.commit()
    db.refresh(pc)
    return pc


def listar_producciones_crudo(db, usuario=None):
    return (
        db.query(ProduccionCrudo)
        .options(
            joinedload(ProduccionCrudo.crudo),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.material),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.solicitante),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.creador),
            joinedload(ProduccionCrudo.mano_obras).joinedload(ProduccionCrudoManoObra.empleado),
            joinedload(ProduccionCrudo.mano_obras).joinedload(ProduccionCrudoManoObra.creador),
        )
        .order_by(ProduccionCrudo.id.desc())
        .all()
    )


def obtener_produccion_crudo(db, produccion_id, usuario=None):
    return (
        db.query(ProduccionCrudo)
        .options(
            joinedload(ProduccionCrudo.crudo),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.material),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.solicitante),
            joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.creador),
            joinedload(ProduccionCrudo.mano_obras).joinedload(ProduccionCrudoManoObra.empleado),
            joinedload(ProduccionCrudo.mano_obras).joinedload(ProduccionCrudoManoObra.creador),
        )
        .filter(ProduccionCrudo.id == produccion_id)
        .first()
    )


def registrar_consumo_crudo(db, produccion_id, esquema: CrudoConsumoCreate, usuario=None):
    pc = obtener_produccion_crudo(db, produccion_id)
    if not pc:
        raise ValueError("La producción de crudo no existe.")
    if pc.estado in ("COMPLETADA", "CANCELADA"):
        raise ValueError(f"No se puede registrar consumo en una producción '{pc.estado}'.")
    material = db.query(Material).filter(Material.id == esquema.material_id).first()
    if not material:
        raise ValueError("El material especificado no existe.")
    solicitante = db.query(Empleado).filter(Empleado.id == esquema.solicitante_empleado_id).first()
    if not solicitante:
        raise ValueError("Debe indicar quién solicita el material (solicitante inválido).")
    now = datetime.utcnow()
    corte_activo = bool(getattr(esquema, "ancho_corte_cm", None) and getattr(esquema, "largo_corte_cm", None))
    # El motor de cortes no admite captura flexible (igual que producción por pedidos).
    if corte_activo and (
        esquema.unidad_captura or esquema.pieza_largo or esquema.pieza_ancho or esquema.pieza_espesor
    ):
        raise ValueError("El consumo por corte de láminas no admite captura en cm ni por pieza.")
    # Captura flexible → unidad base del material ANTES de descontar/costear.
    cantidad_base = resolver_cantidad_consumo(
        material,
        esquema.cantidad,
        esquema.unidad_captura,
        esquema.pieza_largo,
        esquema.pieza_ancho,
        esquema.pieza_espesor,
    )
    consumo = ProduccionCrudoConsumo(
        produccion_crudo_id=pc.id,
        material_id=material.id,
        cantidad=cantidad_base,
        costo_unitario=material.costo_base,
        seccion=esquema.seccion,
        ancho_corte_cm=Decimal(str(esquema.ancho_corte_cm)) if corte_activo else None,
        largo_corte_cm=Decimal(str(esquema.largo_corte_cm)) if corte_activo else None,
        origen_sobrante_id=esquema.origen_sobrante_id if corte_activo else None,
        unidad_captura=esquema.unidad_captura,
        pieza_largo=Decimal(str(esquema.pieza_largo)) if esquema.pieza_largo else None,
        pieza_ancho=Decimal(str(esquema.pieza_ancho)) if esquema.pieza_ancho else None,
        pieza_espesor=Decimal(str(esquema.pieza_espesor)) if esquema.pieza_espesor else None,
        componente=(esquema.componente or "").strip().upper() or None,
        es_excedente=bool(getattr(esquema, "es_excedente", False)),
        motivo_exceso=(esquema.motivo_exceso or "").strip().upper() or None,
        solicitante_empleado_id=solicitante.id,
        creado_por_id=usuario.id if usuario else None,
        fecha=now,
        observaciones=esquema.observaciones,
    )
    db.add(consumo)
    db.flush()
    ubicacion_id = _ubicacion_deposito(db)
    if corte_activo:
        from app.modules.inventory.cortes_service import consumir_por_cortes
        try:
            resultado_corte = consumir_por_cortes(
                db,
                material=material,
                cantidad_cortes=esquema.cantidad,
                largo_corte_cm=esquema.largo_corte_cm,
                ancho_corte_cm=esquema.ancho_corte_cm,
                ubicacion_id=ubicacion_id,
                referencia_tipo="produccion_crudo",
                referencia_id=consumo.id,
                consumo_origen_tipo="produccion_crudo",
                origen_sobrante_id=esquema.origen_sobrante_id,
                sobrante_largo_cm=getattr(esquema, "sobrante_largo_cm", None),
                sobrante_ancho_cm=getattr(esquema, "sobrante_ancho_cm", None),
            )
        except ValueError as e:
            db.rollback()
            raise ValueError(f"Error al descontar inventario: {e}")
        consumo.costo_unitario = resultado_corte["costo_unitario"]
        consumo.laminas_consumidas = resultado_corte["laminas_consumidas"]
        costo_total_consumo = resultado_corte["costo_total"]
        detalle_corte = resultado_corte["detalle"]
    else:
        movimiento = MovimientoCreate(
            material_id=material.id,
            ubicacion_id=ubicacion_id,
            tipo="SALIDA",
            cantidad=cantidad_base,
            referencia_tipo="produccion_crudo",
            referencia_id=consumo.id,
            observaciones=f"Consumo en producción de crudo {pc.id} — Solicitante: {solicitante.nombre}",
        )
        try:
            registrar_movimiento(db, movimiento)
        except ValueError as e:
            db.rollback()
            raise ValueError(f"Error al descontar inventario: {e}")
        costo_total_consumo = cantidad_base * material.costo_base
        detalle_corte = None
    tipo_gasto = db.query(TipoGasto).filter(TipoGasto.nombre == "Consumo de Materia Prima en Producción").first()
    if tipo_gasto:
        from app.modules.gastos.model import Gasto
        costo_total = costo_total_consumo
        descripcion_gasto = f"Consumo {material.nombre} ({cantidad_base}) - Producción Crudo #{pc.id} — Solicita: {solicitante.nombre}"
        nota = nota_captura(
            esquema.cantidad, esquema.unidad_captura,
            esquema.pieza_largo, esquema.pieza_ancho, esquema.pieza_espesor,
        )
        if nota:
            descripcion_gasto += f" — {nota}"
        if detalle_corte:
            descripcion_gasto += f" — {detalle_corte}"
        db.add(Gasto(
            tipo_gasto_id=tipo_gasto.id,
            moneda_id=1,
            fecha=date.today(),
            descripcion=descripcion_gasto,
            monto=costo_total,
            tasa_cambio=Decimal("1.0"),
            monto_en_moneda_base=costo_total,
            observaciones=f"Generado automáticamente al descontar inventario en producción de crudo #{pc.id} [consumo_crudo {consumo.id}]",
        ))
    pc.costo_total = Decimal(str(pc.costo_total or 0)) + costo_total_consumo
    record_event(
        db, actor=usuario, action="CREATE", entity_type="produccion_crudo_consumo", entity_id=consumo.id,
        after={
            "material_id": material.id,
            "cantidad": float(consumo.cantidad),
            "captura": nota_captura(
                esquema.cantidad, esquema.unidad_captura,
                esquema.pieza_largo, esquema.pieza_ancho, esquema.pieza_espesor,
            ),
            "produccion_crudo_id": pc.id,
            "solicitante": solicitante.nombre,
        },
    )
    db.commit()
    db.refresh(consumo)
    return consumo


def cambiar_estado_produccion_crudo(db, produccion_id, estado: str, usuario=None):
    pc = obtener_produccion_crudo(db, produccion_id)
    if not pc:
        raise ValueError("La producción de crudo no existe.")
    estado = estado.upper()
    if estado not in ("PENDIENTE", "EN_PRODUCCION", "COMPLETADA", "CANCELADA"):
        raise ValueError(f"Estado inválido: {estado}")
    if estado == pc.estado:
        return pc
    if estado == "COMPLETADA":
        if pc.estado == "CANCELADA":
            raise ValueError("Una producción cancelada no puede completarse.")
        # Serializa dos "finalizar" simultáneos: re-lee con FOR UPDATE para no
        # generar egresos duplicados por una carrera de lecturas.
        pc = (
            db.query(ProduccionCrudo)
            .options(
                joinedload(ProduccionCrudo.crudo),
                joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.material),
                joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.solicitante),
                joinedload(ProduccionCrudo.consumos).joinedload(ProduccionCrudoConsumo.creador),
                joinedload(ProduccionCrudo.mano_obras),
            )
            .filter(ProduccionCrudo.id == produccion_id)
            .with_for_update(of=ProduccionCrudo)
            .first()
        )
        if not pc:
            raise ValueError("La producción de crudo no existe.")
        if pc.estado == "COMPLETADA":
            return pc
        crudo = (
            db.query(ProductoCrudoInventario)
            .filter(ProductoCrudoInventario.id == pc.crudo_id)
            .with_for_update()
            .first()
        )
        crudo.cantidad = Decimal(str(crudo.cantidad)) + Decimal(str(pc.cantidad))
        crudo.activo = True
        # Materializa el egreso de toda la mano de obra aún sin pagar (costo de
        # producción que alimenta la nómina). Idempotente: las ya pagadas se omiten.
        _egresar_mano_obra_crudo(db, pc, usuario)
        pc.estado = "COMPLETADA"
        pc.fecha_fin = datetime.utcnow()
        pc.actualizado_por_id = usuario.id if usuario else None
        db.add(crudo)
    elif estado == "CANCELADA":
        if pc.estado == "COMPLETADA":
            raise ValueError("No se puede cancelar una producción ya completada (revierte inventario y gastos).")
        pc.estado = "CANCELADA"
        pc.actualizado_por_id = usuario.id if usuario else None
    elif estado == "EN_PRODUCCION":
        pc.estado = "EN_PRODUCCION"
        pc.fecha_inicio = pc.fecha_inicio or datetime.utcnow()
        pc.actualizado_por_id = usuario.id if usuario else None
    else:  # PENDIENTE
        pc.estado = "PENDIENTE"
        pc.actualizado_por_id = usuario.id if usuario else None
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="produccion_crudo", entity_id=pc.id,
        after={"estado": estado, "costo_total": float(pc.costo_total)},
    )
    db.commit()
    db.refresh(pc)
    return pc


# ------------------------------------------------------------
# Mano de obra en producción de crudo
# ------------------------------------------------------------
def _egresar_mano_obra_crudo(db, pc, usuario=None):
    """Materializa el egreso de toda la mano de obra sin pagar de una producción
    de crudo (costo de producción que alimenta la nómina). Es idempotente: las MO
    ya pagadas se omiten, así "finalizar" no duplica gastos aunque se re-ejecute."""
    from app.modules.gastos.model import Gasto
    tipo_gasto = _tipo_gasto(db, "Mano de Obra de Producción")
    for mo in pc.mano_obras or []:
        if mo.pagado:
            continue
        marcador = f"[mano_obra_crudo {mo.id}]"
        monto = _redondear2(
            Decimal(str(mo.monto)) * (Decimal("1") + Decimal(str(mo.porcentaje_recargo or 0)) / Decimal("100"))
        )
        db.add(Gasto(
            tipo_gasto_id=tipo_gasto.id,
            moneda_id=1,
            fecha=date.today(),
            descripcion=f"Mano de obra #{mo.id} - Producción Crudo #{pc.id} - {mo.empleado_nombre or 'Empleado'}",
            monto=monto,
            tasa_cambio=Decimal("1.0"),
            monto_en_moneda_base=monto,
            observaciones=f"Generado automáticamente al finalizar la producción de crudo {marcador}",
            creado_por_id=usuario.id if usuario else None,
        ))
        mo.pagado = True
        mo.listo_nomina = True
        mo.actualizado_por_id = usuario.id if usuario else None


def _produccion_mo_abierta(db, produccion_id):
    """Devuelve la producción de crudo si existe y admite registrar mano de obra,
    o lanza ValueError acorde. Evita escribir en producciones cerradas."""
    pc = obtener_produccion_crudo(db, produccion_id)
    if not pc:
        raise ValueError("La producción de crudo no existe.")
    if pc.estado in ("COMPLETADA", "CANCELADA"):
        raise ValueError(
            f"No se puede registrar mano de obra en una producción '{pc.estado}'."
        )
    return pc


def crear_mano_obra_crudo(db, produccion_id, esquema: ProduccionCrudoManoObraCreate, usuario=None):
    pc = _produccion_mo_abierta(db, produccion_id)
    empleado = db.query(Empleado).filter(Empleado.id == esquema.empleado_id).first()
    if not empleado:
        raise ValueError("El empleado especificado no existe.")
    if not empleado.activo:
        raise ValueError("El empleado está inactivo.")
    if esquema.monto < 0:
        raise ValueError("El monto no puede ser negativo.")
    # El monto ingresado es POR UNIDAD; se multiplica por la cantidad indicada (o la cantidad total de la producción).
    cant_unidades = Decimal(str(esquema.cantidad)) if esquema.cantidad is not None else Decimal(str(pc.cantidad or 1))
    monto_unitario = Decimal(str(esquema.monto))
    monto_total = monto_unitario * cant_unidades
    mo = ProduccionCrudoManoObra(
        produccion_crudo_id=pc.id,
        empleado_id=empleado.id,
        monto=monto_total,
        porcentaje_recargo=Decimal(str(esquema.porcentaje_recargo or 0)),
        listo_nomina=bool(esquema.listo_nomina),
        pagado=False,
        observaciones=esquema.observaciones or f"MO unitaria ${monto_unitario:g} × {cant_unidades:g} und",
        creado_por_id=usuario.id if usuario else None,
    )
    db.add(mo)
    db.flush()
    record_event(
        db, actor=usuario, action="CREATE", entity_type="produccion_crudo_mano_obra",
        entity_id=mo.id,
        after={"empleado_id": empleado.id, "monto": float(mo.monto), "produccion_crudo_id": pc.id, "cantidad": float(cant_unidades)},
    )
    db.commit()
    db.refresh(mo)
    return mo


def _mano_obra_crudo(db, mano_obra_id):
    mo = db.query(ProduccionCrudoManoObra).filter(ProduccionCrudoManoObra.id == mano_obra_id).first()
    if not mo:
        raise ValueError("La mano de obra de crudo no existe.")
    return mo


def actualizar_mano_obra_crudo(db, mano_obra_id, esquema: ProduccionCrudoManoObraUpdate, usuario=None):
    mo = _mano_obra_crudo(db, mano_obra_id)
    if mo.pagado:
        raise ValueError(
            "No se puede modificar una mano de obra ya pagada (su egreso está registrado en Gastos)."
        )
    pc = _produccion_mo_abierta(db, mo.produccion_crudo_id)
    if esquema.monto is not None:
        if esquema.monto < 0:
            raise ValueError("El monto no puede ser negativo.")
        mo.monto = Decimal(str(esquema.monto))
    if esquema.porcentaje_recargo is not None:
        mo.porcentaje_recargo = Decimal(str(esquema.porcentaje_recargo))
    if esquema.listo_nomina is not None:
        mo.listo_nomina = bool(esquema.listo_nomina)
    if esquema.observaciones is not None:
        mo.observaciones = esquema.observaciones
    mo.actualizado_por_id = usuario.id if usuario else None
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="produccion_crudo_mano_obra",
        entity_id=mo.id, after={"monto": float(mo.monto), "pagado": mo.pagado},
    )
    db.commit()
    db.refresh(mo)
    return mo


def alternar_listo_nomina_mano_obra_crudo(db, mano_obra_id, listo: bool, usuario=None):
    mo = _mano_obra_crudo(db, mano_obra_id)
    if mo.pagado:
        raise ValueError("No se puede alternar el estado de nómina de una mano de obra ya pagada.")
    mo.listo_nomina = bool(listo)
    mo.actualizado_por_id = usuario.id if usuario else None
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="produccion_crudo_mano_obra",
        entity_id=mo.id, after={"listo_nomina": bool(listo)},
    )
    db.commit()
    db.refresh(mo)
    return mo


def eliminar_mano_obra_crudo(db, mano_obra_id, usuario=None):
    mo = _mano_obra_crudo(db, mano_obra_id)
    if mo.pagado:
        raise ValueError(
            "No se puede eliminar una mano de obra ya pagada (su egreso está registrado en Gastos)."
        )
    _produccion_mo_abierta(db, mo.produccion_crudo_id)
    record_event(
        db, actor=usuario, action="DELETE", entity_type="produccion_crudo_mano_obra",
        entity_id=mo.id, before={"empleado_id": mo.empleado_id, "monto": float(mo.monto)},
    )
    db.delete(mo)
    db.commit()
    return True


def asignar_crudo_a_detalle(db, crudo_id, detalle_pedido_id, usuario=None):
    """Asigna una pieza de crudo a un detalle de pedido: SOLO descuenta stock del
    ítem en crudo y registra trazabilidad. NO marca etapas y NO descuenta
    materiales (esos ya se descontaron al producir el crudo)."""
    detalle = db.query(DetallePedido).filter(DetallePedido.id == detalle_pedido_id).with_for_update().first()
    if not detalle:
        raise ValueError("El detalle de pedido no existe.")
    crudo = (
        db.query(ProductoCrudoInventario)
        .filter(ProductoCrudoInventario.id == crudo_id)
        .with_for_update()
        .first()
    )
    if not crudo:
        raise ValueError("El ítem en crudo no existe.")
    if not crudo.activo or crudo.cantidad <= 0:
        raise ValueError("El ítem en crudo no tiene stock disponible.")
    cantidad = Decimal("1")
    crudo.cantidad = Decimal(str(crudo.cantidad)) - cantidad
    if crudo.cantidad <= 0:
        crudo.cantidad = Decimal("0")
        crudo.activo = False
    uso = ProduccionCrudoUso(
        crudo_id=crudo.id,
        detalle_pedido_id=detalle.id,
        cantidad=cantidad,
        creado_por_id=usuario.id if usuario else None,
    )
    db.add(uso)
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="producto_crudo", entity_id=crudo.id,
        after={"descontado": float(cantidad), "detalle_pedido_id": detalle.id},
    )
    db.commit()
    db.refresh(uso)
    return uso


# ------------------------------------------------------------
