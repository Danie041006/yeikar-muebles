from datetime import datetime
from decimal import Decimal

from sqlalchemy import false, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.auditoria.service import record_event
from app.modules.clients.model import Client
from app.modules.empleados.model import Empleado
from app.modules.envios import schemas
from app.modules.envios.model import Envio, EnvioAsignacion, EnvioDetalle, EnvioUbicacion
from app.modules.orders.model import DetallePedido, Pedido
from app.modules.production.model import OrdenProduccion
from app.modules.users.deps import tiene_alcance_total
from app.modules.users.model import Usuario
from app.core.state_machine import TRANSICIONES_ENVIO, validar_transicion
from app.core.hora_ve import ahora_ve

# Estados del envío que ocupan cantidades: un despacho preparado o en tránsito
# reserva sus ítems para que otro despacho no los vuelva a seleccionar.
ESTADOS_ACTIVOS = {"PREPARADO", "EN_TRANSITO"}
ESTADOS_VALIDOS = {"PREPARADO", "EN_TRANSITO", "ENTREGADO", "FALLIDO"}
# Tipos de línea que se fabrican en el taller (el resto se entrega sin orden).
TIPOS_PRODUCIDOS = {"FABRICADO", "REPARACION"}


def _scope_envios(query, usuario: Usuario | None):
    if usuario is None or tiene_alcance_total(usuario):
        return query
    if usuario.empleado_id is None:
        return query.filter(false())
    return query.filter(Envio.empleado_id == usuario.empleado_id)


def _snapshot(envio: Envio) -> dict:
    return {
        "pedido_id": envio.pedido_id,
        "empleado_id": envio.empleado_id,
        "estado": envio.estado,
        "direccion_entrega": envio.direccion_entrega,
        "guia_despacho": envio.guia_despacho,
        "observaciones": envio.observaciones,
        "fecha_salida": envio.fecha_salida,
        "fecha_entrega": envio.fecha_entrega,
        "costo_flete": float(envio.costo_flete) if envio.costo_flete is not None else None,
        "moneda_flete_id": envio.moneda_flete_id,
        "tasa_cambio_flete": float(envio.tasa_cambio_flete) if envio.tasa_cambio_flete is not None else None,
        "costo_flete_en_moneda_base": float(envio.costo_flete_en_moneda_base) if envio.costo_flete_en_moneda_base is not None else None,
        "detalles": [
            {
                "detalle_pedido_id": item.detalle_pedido_id,
                "orden_produccion_id": item.orden_produccion_id,
                "cantidad": float(item.cantidad),
            }
            for item in (envio.detalles or [])
        ],
    }


def _procesar_flete(db: Session, envio: Envio) -> None:
    """Calcula y guarda el costo del flete en moneda base (COP). Si la moneda
    del flete es la base o no se indica, tasa = 1.0 y base = monto. En cualquier
    otro caso usa la TRM recibida (o 1.0 como mejor esfuerzo) para dejar el
    monto comparable con los costos de producción (todos en moneda base)."""
    monto = envio.costo_flete
    if monto is None:
        return
    moneda = envio.moneda_flete_id
    if not moneda or moneda == 1:
        envio.tasa_cambio_flete = Decimal("1.000000")
        envio.costo_flete_en_moneda_base = Decimal(str(monto)).quantize(Decimal("0.01"))
        return
    tasa = envio.tasa_cambio_flete if envio.tasa_cambio_flete is not None else Decimal("1.000000")
    envio.costo_flete_en_moneda_base = (Decimal(str(monto)) * Decimal(str(tasa))).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Entregas parciales: qué falta, qué está listo y cuánto se puede despachar
# ---------------------------------------------------------------------------

def _d(valor) -> Decimal:
    return Decimal(str(valor if valor is not None else 0))


def _descripcion_item(detalle: DetallePedido, orden: OrdenProduccion | None) -> str:
    base = None
    if detalle.producto is not None:
        base = detalle.producto.nombre
    elif detalle.material is not None:
        base = detalle.material.nombre
    base = base or detalle.descripcion_especifica or detalle.observaciones or "Servicio"
    if orden is not None and orden.pieza_nombre:
        return f"{base} — {orden.pieza_nombre}"
    return base


def _consumos_por_item(db: Session, pedido_id: int) -> dict[tuple[int, int | None], dict[str, Decimal]]:
    """Suma entregado/reservado por (detalle, orden) de todos los despachos.

    Un envío PREPARADO o EN_TRANSITO RESERVA sus cantidades; uno ENTREGADO las
    da por entregadas. FALLIDO no ocupa nada (se puede reprogramar).
    """
    filas = (
        db.query(
            EnvioDetalle.detalle_pedido_id,
            EnvioDetalle.orden_produccion_id,
            Envio.estado,
            func.coalesce(func.sum(EnvioDetalle.cantidad), 0),
        )
        .join(Envio, Envio.id == EnvioDetalle.envio_id)
        .filter(Envio.pedido_id == pedido_id)
        .group_by(EnvioDetalle.detalle_pedido_id, EnvioDetalle.orden_produccion_id, Envio.estado)
        .all()
    )
    consumos: dict[tuple[int, int | None], dict[str, Decimal]] = {}
    for detalle_id, orden_id, estado, cantidad in filas:
        clave = (int(detalle_id), int(orden_id) if orden_id is not None else None)
        acumulado = consumos.setdefault(
            clave, {"entregado": Decimal("0"), "reservado": Decimal("0")}
        )
        if estado == "ENTREGADO":
            acumulado["entregado"] += _d(cantidad)
        elif estado in ESTADOS_ACTIVOS:
            acumulado["reservado"] += _d(cantidad)
    return consumos


def _items_entrega(db: Session, pedido: Pedido) -> list[dict]:
    """Una fila por unidad entregable: renglón normal o pieza con orden propia.

    Cada fila trae total, entregado, reservado, pendiente y `cantidad_lista`
    (la parte que ya salió de producción y se puede llevar en un despacho).
    """
    detalles = (
        db.query(DetallePedido)
        .options(
            joinedload(DetallePedido.producto),
            joinedload(DetallePedido.material),
            selectinload(DetallePedido.ordenes),
        )
        .filter(DetallePedido.pedido_id == pedido.id)
        .order_by(DetallePedido.id)
        .all()
    )
    consumos = _consumos_por_item(db, pedido.id)
    items: list[dict] = []

    for detalle in detalles:
        tipo = detalle.tipo_item or "FABRICADO"
        ordenes = [
            orden for orden in (detalle.ordenes or [])
            if orden.estado != "CANCELADA"
        ]
        if tipo in TIPOS_PRODUCIDOS and ordenes:
            for orden in ordenes:
                total = _d(
                    orden.cantidad if orden.cantidad is not None else detalle.cantidad
                )
                if total <= 0:
                    continue
                consumo = consumos.get((detalle.id, orden.id), {})
                items.append({
                    "detalle": detalle,
                    "orden": orden,
                    "total": total,
                    "entregado": consumo.get("entregado", Decimal("0")),
                    "reservado": consumo.get("reservado", Decimal("0")),
                    "listo_total": total if orden.estado == "FINALIZADA" else Decimal("0"),
                    "estado_produccion": orden.estado,
                    "descripcion": _descripcion_item(detalle, orden),
                    "pieza_nombre": orden.pieza_nombre,
                })
        else:
            total = _d(detalle.cantidad)
            if total <= 0:
                continue
            consumo = consumos.get((detalle.id, None), {})
            # Sin orden (reventa/insumo/servicio o pedido histórico ya terminado):
            # se puede despachar de una vez. Un FABRICADO sin orden en producción
            # no se puede entregar hasta que el pedido esté TERMINADO (legacy).
            if tipo in TIPOS_PRODUCIDOS and pedido.estado not in ("TERMINADO", "ENTREGADO"):
                listo_total = Decimal("0")
            else:
                listo_total = total
            items.append({
                "detalle": detalle,
                "orden": None,
                "total": total,
                "entregado": consumo.get("entregado", Decimal("0")),
                "reservado": consumo.get("reservado", Decimal("0")),
                "listo_total": listo_total,
                "estado_produccion": None,
                "descripcion": _descripcion_item(detalle, None),
                "pieza_nombre": None,
            })

    # Compatibilidad con envíos anteriores a la entrega parcial: no tienen
    # detalle y cubrían todo el pedido. Se tratan como entrega/reserva total.
    legacy = (
        db.query(Envio)
        .filter(Envio.pedido_id == pedido.id, ~Envio.detalles.any())
        .all()
    )
    for envio in legacy:
        if envio.estado == "ENTREGADO":
            for item in items:
                item["entregado"] = item["total"]
                item["reservado"] = Decimal("0")
        elif envio.estado in ESTADOS_ACTIVOS:
            for item in items:
                item["reservado"] = item["total"]
                item["entregado"] = Decimal("0")

    for item in items:
        ocupado = item["entregado"] + item["reservado"]
        item["pendiente"] = max(Decimal("0"), item["total"] - ocupado)
        disponible_listo = max(Decimal("0"), item["listo_total"] - ocupado)
        item["cantidad_lista"] = min(item["pendiente"], disponible_listo)

    return items


def _resumen_entrega(db: Session, pedido: Pedido) -> dict:
    items = _items_entrega(db, pedido)
    total = sum((item["total"] for item in items), Decimal("0"))
    entregado = sum((item["entregado"] for item in items), Decimal("0"))
    pendiente = max(Decimal("0"), total - entregado)
    if total > 0 and pendiente <= 0:
        estado = "COMPLETO"
    elif entregado > 0:
        estado = "PARCIAL"
    else:
        estado = "PENDIENTE"
    return {
        "total": total,
        "entregado": entregado,
        "pendiente": pendiente,
        "estado": estado,
        "items": items,
    }


def pedido_entregado_completo(db: Session, pedido: Pedido) -> bool:
    resumen = _resumen_entrega(db, pedido)
    return resumen["total"] > 0 and resumen["pendiente"] <= 0


def _resolver_items_envio(
    db: Session,
    pedido: Pedido,
    payload: list[schemas.EnvioDetalleCreate],
) -> list[tuple[DetallePedido, OrdenProduccion | None, Decimal]]:
    """Valida y normaliza los ítems de un despacho contra lo que está listo.

    - Con `detalles`: valida pertenencia, orden FINALIZADA y cantidad disponible.
    - Sin `detalles` (envío automático/compatibilidad): exige que TODO lo
      pendiente esté listo y despacha el pedido completo restante.
    """
    items = _items_entrega(db, pedido)
    por_clave = {
        (item["detalle"].id, item["orden"].id if item["orden"] else None): item
        for item in items
    }
    por_detalle: dict[int, list[dict]] = {}
    for item in items:
        por_detalle.setdefault(item["detalle"].id, []).append(item)

    resueltos: list[tuple[DetallePedido, OrdenProduccion | None, Decimal]] = []

    if not payload:
        pendientes = [item for item in items if item["pendiente"] > 0]
        if not pendientes:
            raise ValueError("El pedido no tiene ítems pendientes por entregar.")
        faltan = [
            item for item in pendientes
            if item["cantidad_lista"] < item["pendiente"]
        ]
        if faltan:
            nombres = ", ".join(item["descripcion"] for item in faltan[:5])
            raise ValueError(
                "Todavía hay ítems en producción o sin orden terminada "
                f"({nombres}). Indica solo los ítems listos para una entrega parcial."
            )
        for item in pendientes:
            resueltos.append((item["detalle"], item["orden"], item["pendiente"]))
        return resueltos

    agrupados: dict[tuple[int, int | None], Decimal] = {}
    for linea in payload:
        clave = (linea.detalle_pedido_id, linea.orden_produccion_id)
        agrupados[clave] = agrupados.get(clave, Decimal("0")) + _d(linea.cantidad)

    for (detalle_id, orden_id), cantidad in agrupados.items():
        if cantidad <= 0:
            raise ValueError("Las cantidades a entregar deben ser mayores que cero.")
        if orden_id is not None:
            item = por_clave.get((detalle_id, orden_id))
            if item is None:
                raise ValueError(
                    f"La pieza/orden #{orden_id} no pertenece al pedido o fue cancelada."
                )
            if item["estado_produccion"] != "FINALIZADA":
                raise ValueError(
                    f"La orden #{orden_id} todavía no está FINALIZADA "
                    f"(estado: {item['estado_produccion'] or 'sin orden'})."
                )
        else:
            candidatos = por_detalle.get(detalle_id, [])
            if not candidatos:
                raise ValueError(f"La línea #{detalle_id} no pertenece al pedido.")
            if len(candidatos) > 1:
                raise ValueError(
                    f"La línea #{detalle_id} tiene varias piezas/órdenes: "
                    "indica cuál pieza se entrega."
                )
            item = candidatos[0]

        if item["cantidad_lista"] <= 0:
            raise ValueError(f"'{item['descripcion']}' todavía no está listo para entregar.")
        if cantidad > item["cantidad_lista"]:
            raise ValueError(
                f"De '{item['descripcion']}' solo hay {float(item['cantidad_lista']):g} "
                f"disponible(s) para entregar (pediste {float(cantidad):g})."
            )
        resueltos.append((item["detalle"], item["orden"], cantidad))

    return resueltos


def _crear_detalles_envio(
    envio: Envio,
    items: list[tuple[DetallePedido, OrdenProduccion | None, Decimal]],
) -> None:
    for detalle, orden, cantidad in items:
        envio.detalles.append(
            EnvioDetalle(
                detalle_pedido_id=detalle.id,
                orden_produccion_id=orden.id if orden else None,
                cantidad=cantidad,
            )
        )


def _actualizar_estado_pedido_por_entregas(
    db: Session,
    pedido: Pedido,
    usuario: Usuario | None = None,
) -> dict:
    """Cierra el pedido como ENTREGADO solo cuando ya salió TODO.

    Mientras falte algo, el pedido conserva su estado de producción/terminado;
    el progreso se expone en `entrega_resumen` (PARCIAL/PENDIENTE).
    """
    db.flush()
    resumen = _resumen_entrega(db, pedido)
    if resumen["total"] > 0 and resumen["pendiente"] <= 0:
        if pedido.estado != "ENTREGADO":
            estado_anterior = pedido.estado
            pedido.estado = "ENTREGADO"
            record_event(
                db,
                actor=usuario,
                action="STATE_CHANGE",
                entity_type="pedido",
                entity_id=pedido.id,
                before={"estado": estado_anterior},
                after={"estado": "ENTREGADO", "motivo": "todas las entregas registradas"},
            )
    return resumen


def _registrar_asignacion(db: Session, envio: Envio, empleado_id: int | None, usuario: Usuario | None) -> None:
    if envio.empleado_id == empleado_id:
        return

    activa = db.query(EnvioAsignacion).filter(
        EnvioAsignacion.envio_id == envio.id,
        EnvioAsignacion.desasignado_en.is_(None),
    ).all()
    ahora = ahora_ve()
    for asignacion in activa:
        asignacion.desasignado_en = ahora

    envio.empleado_id = empleado_id
    envio.asignado_por_usuario_id = usuario.id if usuario else None
    if empleado_id is not None:
        db.add(
            EnvioAsignacion(
                envio_id=envio.id,
                empleado_id=empleado_id,
                asignado_por_usuario_id=usuario.id if usuario else None,
                motivo="Asignación operativa",
            )
        )


def obtener_envio(db: Session, id_envio: int, usuario: Usuario | None = None):
    query = db.query(Envio).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.detalle_pedido).joinedload(DetallePedido.producto),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.detalle_pedido).joinedload(DetallePedido.material),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.orden),
        joinedload(Envio.empleado),
        joinedload(Envio.creador),
        joinedload(Envio.asignado_por),
    ).filter(Envio.id == id_envio)
    return _scope_envios(query, usuario).first()


def _query_envios(
    db: Session,
    buscar: str | None = None,
    estado: str | None = None,
    estados: list[str] | None = None,
    pedido_id: int | None = None,
    usuario: Usuario | None = None,
):
    """Query base con scope y filtros, compartida por listado y conteo."""
    query = db.query(Envio)
    query = _scope_envios(query, usuario)

    if pedido_id is not None:
        query = query.filter(Envio.pedido_id == pedido_id)

    if estado:
        query = query.filter(Envio.estado == estado)

    if estados:
        query = query.filter(Envio.estado.in_(estados))

    if buscar:
        query = query.join(Envio.pedido).join(Pedido.cliente).filter(
            or_(
                Client.nombre.ilike(f"%{buscar}%"),
                Envio.guia_despacho.ilike(f"%{buscar}%"),
                Envio.direccion_entrega.ilike(f"%{buscar}%"),
                Envio.observaciones.ilike(f"%{buscar}%"),
            )
        )

    return query


def obtener_envios(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str | None = None,
    estado: str | None = None,
    estados: list[str] | None = None,
    pedido_id: int | None = None,
    usuario: Usuario | None = None,
):
    query = _query_envios(
        db,
        buscar=buscar,
        estado=estado,
        estados=estados,
        pedido_id=pedido_id,
        usuario=usuario,
    ).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.detalle_pedido).joinedload(DetallePedido.producto),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.detalle_pedido).joinedload(DetallePedido.material),
        selectinload(Envio.detalles).joinedload(EnvioDetalle.orden),
        joinedload(Envio.empleado),
        joinedload(Envio.creador),
        joinedload(Envio.asignado_por),
    )
    return query.order_by(Envio.id.desc()).offset(salto).limit(limite).all()


def contar_envios(
    db: Session,
    buscar: str | None = None,
    estado: str | None = None,
    estados: list[str] | None = None,
    pedido_id: int | None = None,
    usuario: Usuario | None = None,
) -> int:
    return _query_envios(
        db,
        buscar=buscar,
        estado=estado,
        estados=estados,
        pedido_id=pedido_id,
        usuario=usuario,
    ).count()


def crear_envio(db: Session, esquema: schemas.EnvioCreate, usuario: Usuario | None = None):
    if usuario is not None and not tiene_alcance_total(usuario):
        raise PermissionError("Solo un supervisor puede crear y asignar despachos.")

    if esquema.estado not in ESTADOS_VALIDOS:
        raise ValueError(f"Estado de envío inválido. Debe ser uno de: {sorted(ESTADOS_VALIDOS)}")

    pedido = db.query(Pedido).filter(Pedido.id == esquema.pedido_id).with_for_update().first()
    if not pedido:
        raise ValueError("El pedido especificado no existe.")
    if pedido.estado not in ("APROBADO", "PRODUCCION", "PAUSADO", "TERMINADO"):
        raise ValueError(
            f"No se puede despachar un pedido en estado '{pedido.estado}'. "
            "Debe estar aprobado o en producción."
        )

    datos = esquema.model_dump()
    datos.pop("detalles", None)
    items = _resolver_items_envio(db, pedido, esquema.detalles or [])

    db_envio = Envio(
        **datos,
        creado_por_id=usuario.id if usuario else pedido.creado_por_id,
        actualizado_por_id=usuario.id if usuario else pedido.creado_por_id,
        asignado_por_usuario_id=usuario.id if usuario and datos.get("empleado_id") else None,
    )
    if not db_envio.direccion_entrega:
        db_envio.direccion_entrega = pedido.cliente.direccion if pedido.cliente else ""
    _procesar_flete(db, db_envio)
    db.add(db_envio)
    db.flush()

    if db_envio.empleado_id is not None:
        db.add(
            EnvioAsignacion(
                envio_id=db_envio.id,
                empleado_id=db_envio.empleado_id,
                asignado_por_usuario_id=usuario.id if usuario else None,
                motivo="Asignación inicial",
            )
        )

    _crear_detalles_envio(db_envio, items)
    db.flush()

    if esquema.estado == "ENTREGADO":
        db_envio.fecha_entrega = esquema.fecha_entrega or ahora_ve()
        _actualizar_estado_pedido_por_entregas(db, pedido, usuario)
    elif esquema.estado == "EN_TRANSITO":
        db_envio.fecha_salida = esquema.fecha_salida or ahora_ve()

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="envio",
        entity_id=db_envio.id,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def crear_envio_automatico(db: Session, pedido_id: int, usuario: Usuario | None = None):
    """Crea el despacho de lo que ya está listo y pendiente de entregar.

    - Si no quedan ítems listos, devuelve el despacho activo o el último.
    - Si hay ítems listos no reservados, crea un nuevo despacho (aunque ya
      exista otro activo para otra tanda).
    """
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).with_for_update().first()
    if not pedido:
        return None

    activo = (
        db.query(Envio)
        .filter(Envio.pedido_id == pedido_id, Envio.estado.in_(ESTADOS_ACTIVOS))
        .order_by(Envio.id.desc())
        .first()
    )

    # `_items_entrega` ya descuenta lo reservado por despachos activos: si
    # quedan ítems listos, se crea un nuevo despacho para esa tanda. Así el
    # envío automático no se pierde cuando ya había una entrega parcial activa.
    items = [item for item in _items_entrega(db, pedido) if item["cantidad_lista"] > 0]
    if not items:
        if activo:
            return activo
        return (
            db.query(Envio)
            .filter(Envio.pedido_id == pedido_id)
            .order_by(Envio.id.desc())
            .first()
        )

    direccion = pedido.cliente.direccion if pedido.cliente else ""
    db_envio = Envio(
        pedido_id=pedido_id,
        estado="PREPARADO",
        direccion_entrega=direccion or "",
        empleado_id=None,
        fecha_salida=None,
        fecha_entrega=None,
        guia_despacho=None,
        observaciones="Creado automáticamente tras finalizar producción.",
        creado_por_id=usuario.id if usuario else pedido.creado_por_id,
        actualizado_por_id=usuario.id if usuario else pedido.creado_por_id,
    )
    db.add(db_envio)
    db.flush()
    _crear_detalles_envio(
        db_envio,
        [(item["detalle"], item["orden"], item["cantidad_lista"]) for item in items],
    )
    db.flush()
    record_event(
        db,
        actor=usuario,
        action="SYSTEM_CREATE",
        entity_type="envio",
        entity_id=db_envio.id,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def actualizar_envio(
    db: Session,
    id_envio: int,
    esquema: schemas.EnvioUpdate,
    usuario: Usuario | None = None,
):
    query = db.query(Envio).filter(Envio.id == id_envio).with_for_update()
    db_envio = _scope_envios(query, usuario).first()
    if not db_envio:
        return None

    datos = esquema.model_dump(exclude_unset=True)
    if usuario is not None and not tiene_alcance_total(usuario):
        if "empleado_id" in datos and datos["empleado_id"] != db_envio.empleado_id:
            raise PermissionError("No puedes reasignar un despacho.")
        campos_restringidos = {"direccion_entrega", "guia_despacho", "empleado_id"}
        if campos_restringidos.intersection(datos):
            raise PermissionError("Tu rol solo puede actualizar el estado y las novedades de tu despacho.")

    antes = _snapshot(db_envio)
    estado_anterior = db_envio.estado
    nuevo_estado = datos.get("estado")

    # Máquina de estados del envío: PREPARADO→EN_TRANSITO→ENTREGADO/FALLIDO.
    # Prohíbe retrocesos (ENTREGADO→PREPARADO) y transiciones inventadas.
    # Se valida SIEMPRE (aunque el estado no cambie): re-marcar un estado
    # terminal (ENTREGADO/FALLIDO) es rechazado por validar_transicion.
    if nuevo_estado:
        validar_transicion(TRANSICIONES_ENVIO, estado_anterior, nuevo_estado, "envío")

    empleado_nuevo = datos.get("empleado_id", db_envio.empleado_id)
    if empleado_nuevo != db_envio.empleado_id:
        _registrar_asignacion(db, db_envio, empleado_nuevo, usuario)

    for campo, valor in datos.items():
        setattr(db_envio, campo, valor)

    _procesar_flete(db, db_envio)

    if nuevo_estado and nuevo_estado != estado_anterior:
        if nuevo_estado == "EN_TRANSITO" and not db_envio.fecha_salida:
            db_envio.fecha_salida = ahora_ve()
        elif nuevo_estado == "ENTREGADO":
            # La fecha real del pago/entrega puede venir en el body (entregas
            # históricas); si no, se usa HOY en hora Venezuela.
            db_envio.fecha_entrega = db_envio.fecha_entrega or ahora_ve()
            pedido = (
                db.query(Pedido)
                .filter(Pedido.id == db_envio.pedido_id)
                .with_for_update()
                .first()
            )
            if pedido:
                _actualizar_estado_pedido_por_entregas(db, pedido, usuario)

    if usuario is not None:
        db_envio.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE" if nuevo_estado and nuevo_estado != estado_anterior else "UPDATE",
        entity_type="envio",
        entity_id=db_envio.id,
        before=antes,
        after=_snapshot(db_envio),
    )
    db.commit()
    db.refresh(db_envio)
    return db_envio


def eliminar_envio(db: Session, id_envio: int, usuario: Usuario | None = None):
    if usuario is not None and not tiene_alcance_total(usuario):
        raise PermissionError("Solo un supervisor puede eliminar despachos.")
    db_envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not db_envio:
        return False
    # Borrar un envío EN_TRANSITO o ENTREGADO destruye la evidencia del despacho
    # y puede dejar el pedido "entregado" sin envío que lo respalde.
    if db_envio.estado in ("EN_TRANSITO", "ENTREGADO"):
        raise ValueError(
            f"No se puede eliminar un envío en estado '{db_envio.estado}'. "
            "Solo se eliminan envíos PREPARADO o FALLIDO."
        )
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="envio",
        entity_id=db_envio.id,
        before=_snapshot(db_envio),
    )
    db.delete(db_envio)
    db.commit()
    return True


def obtener_pendientes_entrega(db: Session, pedido_id: int):
    """Ítems del pedido con su avance de entrega y cuánto está listo ahora."""
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        return None
    items = _items_entrega(db, pedido)
    return {
        "pedido_id": pedido.id,
        "estado": pedido.estado,
        "items": [
            {
                "detalle_pedido_id": item["detalle"].id,
                "orden_produccion_id": item["orden"].id if item["orden"] else None,
                "pieza_nombre": item["pieza_nombre"],
                "descripcion": item["descripcion"],
                "tipo_item": item["detalle"].tipo_item,
                "cantidad_total": float(item["total"]),
                "cantidad_entregada": float(item["entregado"]),
                "cantidad_reservada": float(item["reservado"]),
                "cantidad_pendiente": float(item["pendiente"]),
                "cantidad_lista": float(item["cantidad_lista"]),
                "estado_produccion": item["estado_produccion"],
            }
            for item in items
        ],
    }


def registrar_ubicacion(
    db: Session,
    id_envio: int,
    datos: schemas.EnvioUbicacionCreate,
    usuario: Usuario,
):
    envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not envio:
        raise LookupError("Envío no encontrado.")
    # Primero el permiso: un no-repartidor no debe poder inferir la existencia/
    # estado de un envío ajeno a través de un 409 (fuga de información).
    if not tiene_alcance_total(usuario) and usuario.empleado_id != envio.empleado_id:
        raise PermissionError("Solo el repartidor asignado puede reportar su ubicación.")
    if envio.estado == "ENTREGADO":
        raise ValueError("El seguimiento finalizó porque el pedido ya fue entregado.")

    ubicacion = EnvioUbicacion(
        envio_id=envio.id,
        empleado_id=usuario.empleado_id,
        reportado_por_id=usuario.id,
        **datos.model_dump(),
    )
    db.add(ubicacion)
    db.flush()
    record_event(
        db,
        actor=usuario,
        action="LOCATION_UPDATE",
        entity_type="envio",
        entity_id=envio.id,
        after={"latitud": datos.latitud, "longitud": datos.longitud, "fuente": datos.fuente},
    )
    db.commit()
    db.refresh(ubicacion)
    return ubicacion


def obtener_ubicaciones(db: Session, id_envio: int, usuario: Usuario):
    envio = obtener_envio(db, id_envio, usuario)
    if not envio:
        return None, []
    ubicaciones = db.query(EnvioUbicacion).options(
        joinedload(EnvioUbicacion.reportado_por)
    ).filter(
        EnvioUbicacion.envio_id == id_envio
    ).order_by(EnvioUbicacion.recibida_en.desc()).limit(500).all()
    return envio, ubicaciones
