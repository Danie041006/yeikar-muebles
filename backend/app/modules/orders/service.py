from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.orders import model, schemas
from app.modules.quotes.model import Cotizacion
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda
from app.modules.sales import service as venta_service
from app.modules.sales.schemas import VentaCreate, PagoCreate
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios, tiene_alcance_total
from app.modules.users.model import Usuario
from app.core.state_machine import (
    TRANSICIONES_ORDEN_PRODUCCION,
    TRANSICIONES_PEDIDO,
    validar_transicion,
)
from app.core.hora_ve import hoy_ve

# Tipos de línea que entran a producción (fabricar un mueble nuevo o reparar
# uno existente). REPARACION crea una OrdenProduccion SIN producto (la pieza es
# del cliente); SERVICIO (flete/instalación) NO se fabrica.
def _es_producible(tipo_item) -> bool:
    return (tipo_item or "FABRICADO") in ("FABRICADO", "REPARACION")


def _auto_agregar_obsequios(db: Session, db_pedido: model.Pedido, detalles_dicts: list):
    """Promo obsequio: por cada renglón REVENTA cuyo producto tenga una promo
    activa se agrega 1 obsequio por unidad comprada (precio 0, es_obsequio=True).

    Idempotente: si el renglón del obsequio ya existe (venga marcado o no) no
    se duplica. Si varios colchones comparten el mismo plástico, sus cantidades
    se acumulan en UNA sola línea de regalo. Corre DESPUÉS de crear los
    detalles y antes del flush/venta final.
    """
    from app.modules.productos.model import PromocionObsequio

    promos = {
        p.colchon_id: p.obsequio_id
        for p in db.query(PromocionObsequio).filter(PromocionObsequio.activo.is_(True)).all()
    }
    if not promos:
        return
    presentes = {d.producto_id for d in db_pedido.detalles if d.producto_id}
    pendientes: dict[int, float] = {}
    for det in detalles_dicts:
        producto_id = det.get("producto_id")
        if not producto_id:
            continue
        if det.get("tipo_item", "FABRICADO") != "REVENTA":
            continue
        obsequio_id = promos.get(producto_id)
        if obsequio_id is None or obsequio_id in presentes:
            continue
        pendientes[obsequio_id] = pendientes.get(obsequio_id, 0.0) + float(det.get("cantidad", 1) or 1)
    for obsequio_id, cantidad in pendientes.items():
        # append a la relación (no solo db.add): la factura automática de la
        # conversión se construye con pedido.detalles en la MISMA transacción
        # y sin esto el regalo no llegaría a la venta/descuento de stock.
        db_pedido.detalles.append(model.DetallePedido(
            producto_id=obsequio_id,
            tipo_item="REVENTA",
            cantidad=cantidad,
            precio=0.0,
            descripcion_especifica="OBSEQUIO PROMO",
            es_obsequio=True,
        ))


def _snapshot(pedido: model.Pedido) -> dict:
    return {
        "cotizacion_id": pedido.cotizacion_id,
        "cliente_id": pedido.cliente_id,
        "fecha": pedido.fecha,
        "estado": pedido.estado,
        "fecha_entrega_estimada": pedido.fecha_entrega_estimada,
        "observaciones": pedido.observaciones,
    }


def _auto_agregar_obsequios(db: Session, db_pedido: model.Pedido, detalles_dicts: list):
    """Promo obsequio: por cada renglón REVENTA cuyo producto tenga una promo
    activa se agrega 1 obsequio por unidad comprada (precio 0, es_obsequio=True).

    Idempotente: si el renglón del obsequio ya existe (venga marcado o no) no
    se duplica. Si varios colchones comparten el mismo plástico, sus cantidades
    se acumulan en UNA sola línea de regalo. Corre DESPUÉS de crear los
    detalles y antes del flush/venta final.
    """
    from app.modules.productos.model import PromocionObsequio

    promos = {
        p.colchon_id: p.obsequio_id
        for p in db.query(PromocionObsequio).filter(PromocionObsequio.activo.is_(True)).all()
    }
    if not promos:
        return
    presentes = {d.producto_id for d in db_pedido.detalles if d.producto_id}
    pendientes: dict[int, float] = {}
    for det in detalles_dicts:
        producto_id = det.get("producto_id")
        if not producto_id:
            continue
        if det.get("tipo_item", "FABRICADO") != "REVENTA":
            continue
        obsequio_id = promos.get(producto_id)
        if obsequio_id is None or obsequio_id in presentes:
            continue
        pendientes[obsequio_id] = pendientes.get(obsequio_id, 0.0) + float(det.get("cantidad", 1) or 1)
    for obsequio_id, cantidad in pendientes.items():
        # append a la relación (no solo db.add): la factura automática de la
        # conversión se construye con pedido.detalles en la MISMA transacción
        # y sin esto el regalo no llegaría a la venta/descuento de stock.
        db_pedido.detalles.append(model.DetallePedido(
            producto_id=obsequio_id,
            tipo_item="REVENTA",
            cantidad=cantidad,
            precio=0.0,
            descripcion_especifica="OBSEQUIO PROMO",
            es_obsequio=True,
        ))


def obtener_pedido(db: Session, id_pedido: int, usuario: Usuario | None = None):
    query = db.query(model.Pedido).filter(model.Pedido.id == id_pedido)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Pedido.creado_por_id, usuario)
    return query.first()

def obtener_pedidos(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    solo_mes_actual: bool = True,
    mes: int = None,
    anio: int = None,
    usuario: Usuario | None = None,
):
    query = db.query(model.Pedido)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Pedido.creado_por_id, usuario)
    if buscar:
        query = query.join(Client).filter(
            or_(
                model.Pedido.observaciones.ilike(f"%{buscar}%"),
                model.Pedido.estado.ilike(f"%{buscar}%"),
                Client.nombre.ilike(f"%{buscar}%")
            )
        )

    # Date/history filters: rango [inicio, fin) para que el índice (fecha, id)
    # sea usable (extract(month/year) no puede usar un índice btree).
    if mes is not None or anio is not None:
        if mes is not None and anio is not None:
            inicio = date(anio, mes, 1)
            if mes == 12:
                fin = date(anio + 1, 1, 1)
            else:
                fin = date(anio, mes + 1, 1)
            query = query.filter(model.Pedido.fecha >= inicio, model.Pedido.fecha < fin)
        elif anio is not None:
            query = query.filter(
                model.Pedido.fecha >= date(anio, 1, 1),
                model.Pedido.fecha < date(anio + 1, 1, 1),
            )
        else:
            # Solo mes sin año: se asume el año en curso.
            today = hoy_ve()
            inicio = date(today.year, mes, 1)
            if mes == 12:
                fin = date(today.year + 1, 1, 1)
            else:
                fin = date(today.year, mes + 1, 1)
            query = query.filter(model.Pedido.fecha >= inicio, model.Pedido.fecha < fin)
    elif solo_mes_actual:
        today = hoy_ve()
        if today.month == 12:
            fin = date(today.year + 1, 1, 1)
        else:
            fin = date(today.year, today.month + 1, 1)
        query = query.filter(
            model.Pedido.fecha >= date(today.year, today.month, 1),
            model.Pedido.fecha < fin,
        )

    query = query.order_by(model.Pedido.fecha.desc(), model.Pedido.id.desc())

    return query.offset(salto).limit(limite).all()

def crear_pedido(db: Session, esquema: schemas.PedidoCreate, usuario: Usuario | None = None):
    # Crear cabecera de pedido
    pedido_datos = esquema.model_dump(exclude={"detalles"})
    if usuario is not None:
        pedido_datos["creado_por_id"] = usuario.id
        pedido_datos["actualizado_por_id"] = usuario.id
    db_pedido = model.Pedido(**pedido_datos)
    db.add(db_pedido)
    db.flush()  # Para obtener el db_pedido.id

    # Crear detalles
    detalles_creados = []
    for detalle_esquema in esquema.detalles:
        db_detalle = model.DetallePedido(
            pedido_id=db_pedido.id,
            **detalle_esquema.model_dump()
        )
        db.add(db_detalle)
        detalles_creados.append(detalle_esquema.model_dump())

    db.flush()
    _auto_agregar_obsequios(db, db_pedido, detalles_creados)

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="pedido",
        entity_id=db_pedido.id,
        after=_snapshot(db_pedido),
    )
    db.commit()
    db.refresh(db_pedido)
    return db_pedido

def actualizar_pedido(
    db: Session,
    id_pedido: int,
    esquema: schemas.PedidoUpdate,
    usuario: Usuario | None = None,
):
    # FOR UPDATE: dos transiciones simultáneas a PRODUCCION se serializan; el
    # segundo request ve el estado ya cambiado y no duplica las órdenes.
    query = db.query(model.Pedido).filter(model.Pedido.id == id_pedido)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Pedido.creado_por_id, usuario)
    db_pedido = query.with_for_update().first()
    if not db_pedido:
        return None
    antes = _snapshot(db_pedido)
    datos = esquema.model_dump(exclude_unset=True)
    
    estado_anterior = db_pedido.estado
    nuevo_estado = datos.get("estado")

    # Máquina de estados: no se pueden saltar etapas del proceso ni revivir
    # pedidos cancelados/entregados.
    if nuevo_estado and nuevo_estado != estado_anterior:
        validar_transicion(TRANSICIONES_PEDIDO, estado_anterior, nuevo_estado, "pedido")
        # Atajo sin producción: un pedido SIN líneas FABRICADO (solo reventa,
        # insumos o piezas de exhibición) no necesita pasar por PRODUCCION:
        # puede ir APROBADO → TERMINADO directamente. Con fabricables se exige
        # el flujo normal (PRODUCCION → TERMINADO).
        if estado_anterior == "APROBADO" and nuevo_estado == "TERMINADO":
            fabricables = [d for d in db_pedido.detalles if _es_producible(d.tipo_item)]
            if fabricables:
                raise ValueError(
                    "Este pedido tiene muebles a fabricar: debe pasar por PRODUCCION "
                    "antes de marcarlo TERMINADO."
                )
        # PRODUCCION → TERMINADO manual: exigir que TODAS las órdenes de
        # producción del pedido estén FINALIZADA (no se "come" la producción).
        # Solo cuentan las líneas FABRICABLES: los productos de REVENTA no
        # entran a producción (se venden del inventario), así que no deben
        # bloquear el cierre del pedido.
        if estado_anterior == "PRODUCCION" and nuevo_estado == "TERMINADO":
            from app.modules.production.model import OrdenProduccion
            detalles_fabricables = [d for d in db_pedido.detalles if _es_producible(d.tipo_item)]
            n_ordenes_finalizadas = db.query(OrdenProduccion).join(
                model.DetallePedido, model.DetallePedido.id == OrdenProduccion.detalle_pedido_id
            ).filter(
                model.DetallePedido.pedido_id == db_pedido.id,
                OrdenProduccion.estado == "FINALIZADA",
            ).count()
            if not detalles_fabricables:
                pass
            elif n_ordenes_finalizadas < len(detalles_fabricables):
                raise ValueError(
                    "No se puede marcar el pedido como TERMINADO: todas las líneas a fabricar "
                    "del pedido deben tener su orden de producción FINALIZADA."
                )
    
    for campo, valor in datos.items():
        setattr(db_pedido, campo, valor)
    
    # Envío automático al TERMINADO (cualquier ruta: manual, atajo sin
    # producción o producción finalizada). crear_envio_automatico es
    # idempotente (si ya existe el envío, no duplica).
    if nuevo_estado == "TERMINADO" and estado_anterior != "TERMINADO":
        from app.modules.envios.service import crear_envio_automatico
        crear_envio_automatico(db, db_pedido.id, usuario)
    
    # If transitioning to PRODUCCION, generate production orders and stages
    # Solo los ítems FABRICADO generan orden; REVENTA e INSUMO no se fabrican.
    if estado_anterior != "PRODUCCION" and nuevo_estado == "PRODUCCION":
        from app.modules.production.model import OrdenProduccion
        from datetime import date

        for detalle in db_pedido.detalles:
            if not _es_producible(detalle.tipo_item):
                continue
            existente = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id == detalle.id).first()
            if not existente:
                db_orden = OrdenProduccion(
                    detalle_pedido_id=detalle.id,
                    estado="EN_PRODUCCION",
                    fecha_inicio=hoy_ve(),
                    fecha_fin=None,
                    creado_por_id=usuario.id if usuario is not None else None,
                    actualizado_por_id=usuario.id if usuario is not None else None,
                )
                db.add(db_orden)

    # Cancelar el pedido detiene sus derivados vivos: la producción no puede
    # seguir trabajándose/finalizándose y la venta no sigue cobrable/facturable.
    if nuevo_estado == "CANCELADO" and estado_anterior != "CANCELADO":
        from app.modules.production.model import OrdenProduccion
        from app.modules.sales.model import Venta

        for detalle in db_pedido.detalles:
            ordenes = db.query(OrdenProduccion).filter(
                OrdenProduccion.detalle_pedido_id == detalle.id,
                OrdenProduccion.estado.notin_(("FINALIZADA", "CANCELADA")),
            ).all()
            for orden in ordenes:
                validar_transicion(
                    TRANSICIONES_ORDEN_PRODUCCION, orden.estado, "CANCELADA", "orden_produccion"
                )
                orden.estado = "CANCELADA"
                orden.actualizado_por_id = usuario.id if usuario is not None else None
        venta = db.query(Venta).filter(Venta.pedido_id == db_pedido.id).first()
        if venta and venta.estado != "PAGADA":
            venta.estado = "CANCELADA"

    if usuario is not None:
        db_pedido.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE" if "estado" in datos else "UPDATE",
        entity_type="pedido",
        entity_id=db_pedido.id,
        before=antes,
        after=_snapshot(db_pedido),
    )
    db.commit()
    db.refresh(db_pedido)
    return db_pedido

def eliminar_pedido(db: Session, id_pedido: int, usuario: Usuario | None = None):
    db_pedido = obtener_pedido(db, id_pedido, usuario)
    if not db_pedido:
        return False
    # Un pedido en curso o con documentos derivados se cancela, no se borra:
    # borrar en cascada destruía el envío (evidencia de entrega) y, con venta/
    # factura/orden, reventaba con un 400/500 genérico de FK.
    if db_pedido.estado not in ("COTIZADO", "APROBADO"):
        raise ValueError(
            f"No se puede eliminar el pedido #{id_pedido} en estado '{db_pedido.estado}': cancélalo."
        )
    from app.modules.envios.model import Envio
    from app.modules.facturacion.model import Factura
    from app.modules.production.model import OrdenProduccion
    from app.modules.sales.model import Venta

    tiene_derivados = (
        db.query(Envio.id).filter(Envio.pedido_id == id_pedido).first()
        or db.query(Venta.id).filter(Venta.pedido_id == id_pedido).first()
        or db.query(Factura.id).filter(Factura.pedido_id == id_pedido).first()
        or db.query(OrdenProduccion.id)
        .join(model.DetallePedido, model.DetallePedido.id == OrdenProduccion.detalle_pedido_id)
        .filter(model.DetallePedido.pedido_id == id_pedido)
        .first()
    )
    if tiene_derivados:
        raise ValueError(
            "El pedido tiene producción, venta, factura o envío asociados: cancélalo en lugar de eliminarlo."
        )
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="pedido",
        entity_id=db_pedido.id,
        before=_snapshot(db_pedido),
    )
    db.delete(db_pedido)
    db.commit()
    return True

def _derivar_tasa_pago(db: Session, moneda_venta_id: int, moneda_pago_id: int, tasa_cotizacion):
    """Tasa del pago ('1 {pago} = X {venta}') usando la TRM congelada en la cotización.
    Devuelve (tasa, derivada): derivada=False si el par no es deducible (ej. VES)."""
    if moneda_pago_id == moneda_venta_id:
        return 1.0, True
    if not tasa_cotizacion:
        return None, False
    codigos = {
        m.id: m.codigo
        for m in db.query(Moneda).filter(Moneda.id.in_([moneda_venta_id, moneda_pago_id])).all()
    }
    venta_cod = codigos.get(moneda_venta_id)
    pago_cod = codigos.get(moneda_pago_id)
    # Cotización COP fija tasa_cambio = 1.0 (1 COP = 1 COP), NO una TRM USD real.
    # Deducir "1 USD = 1 COP" desde ese 1.0 convertiría 200 USD en 200 COP.
    # El par COP→USD NO es deducible: exige la TRM del abono en el request.
    if venta_cod == "USD" and pago_cod == "COP":
        # Solo es deducible si la cotización tiene una TRM real (> 1.0). Un 1.0
        # significa cotización sin tasa cargada → no deducible, exige TRM explícita.
        if float(tasa_cotizacion) > 1.0:
            return 1.0 / float(tasa_cotizacion), True
    return None, False


def convertir_cotizacion_a_pedido(
    db: Session,
    id_cotizacion: int,
    fecha_entrega_estimada=None,
    detalles=[],
    adelanto: float = None,
    moneda_adelanto_id: int = None,
    tasa_cambio_adelanto: float = None,
    metodo_pago: str = None,
    usuario: Usuario | None = None,
):
    # Buscar la cotización con FOR UPDATE: dos conversiones simultáneas quedan
    # serializadas; la segunda detecta el pedido ya creado en vez de lanzar 500.
    cotizacion_query = db.query(Cotizacion).filter(Cotizacion.id == id_cotizacion)
    db_cotizacion = cotizacion_query.with_for_update().first()
    if not db_cotizacion:
        raise ValueError("Cotizacion no encontrada")
    # Convertir es una ESCRITURA sobre la cotización (la marca APROBADA y crea
    # el pedido): solo su autor (o un rol de alcance total) puede hacerlo.
    if usuario is not None and not tiene_alcance_total(usuario) and db_cotizacion.creado_por_id != usuario.id:
        raise ValueError(
            f"No puedes convertir la cotización #{id_cotizacion}: fue creada por "
            "otro usuario. Solo su autor puede convertirla."
        )

    # Idempotencia: si la cotización ya fue convertida, devolver el pedido existente
    pedido_existente = db.query(model.Pedido).filter(model.Pedido.cotizacion_id == id_cotizacion).first()
    if pedido_existente:
        raise ValueError("Esta cotización ya fue convertida a pedido")

    # Una cotización rechazada o vencida no puede convertirse en pedido.
    if db_cotizacion.estado in ("RECHAZADA", "VENCIDA"):
        raise ValueError(
            f"No se puede convertir una cotización en estado '{db_cotizacion.estado}' a pedido. "
            "Solo se convierten cotizaciones en estado BORRADOR, ENVIADA o APROBADA."
        )

    # Validar detalles
    if not detalles:
        raise ValueError("El pedido requiere al menos un detalle de producto")

    # Validar que los precios/cantidades coincidan con los de la cotización.
    # Indexar por (tipo_item, producto_id, material_id) para mezclar fabricados, reventa e insumos.
    detalles_cotizacion = {}
    for dc in (db_cotizacion.detalles or []):
        key = (dc.tipo_item or "FABRICADO", dc.producto_id, dc.material_id)
        detalles_cotizacion[key] = dc
    for detalle in detalles:
        detalle_dict = detalle if isinstance(detalle, dict) else detalle.model_dump()
        tipo = detalle_dict.get("tipo_item", "FABRICADO")
        key = (tipo, detalle_dict.get("producto_id"), detalle_dict.get("material_id"))
        dc = detalles_cotizacion.get(key)
        if dc is None:
            ref = detalle_dict.get("material_id") or detalle_dict.get("producto_id")
            raise ValueError(
                f"El ítem (tipo={tipo}, id={ref}) no forma parte de la cotización. "
                "El pedido debe copiar exactamente los renglones cotizados."
            )
        precio_enviado = float(detalle_dict.get("precio", 0) or 0)
        precio_cotizado = float(dc.precio)
        cantidad_enviada = float(detalle_dict.get("cantidad", 0) or 0)
        cantidad_cotizada = float(dc.cantidad)
        if abs(precio_enviado - precio_cotizado) > 0.01 or abs(cantidad_enviada - cantidad_cotizada) > 0.001:
            # Muebles a la medida: producto_id y material_id son NULL, así que
            # no hay id que mostrar. Antes `ref` quedaba sin asignar y el
            # mensaje de error reventaba con UnboundLocalError.
            ref = detalle_dict.get("material_id") or detalle_dict.get("producto_id")
            ref_txt = f"id={ref}" if ref else "personalizado (sin producto asociado)"
            raise ValueError(
                f"El ítem ({ref_txt}) no coincide con la cotización: "
                f"se cotizó {cantidad_cotizada:g} × {precio_cotizado:,.2f} y se envía "
                f"{cantidad_enviada:g} × {precio_enviado:,.2f}. "
                "El pedido debe copiar exactamente los precios y cantidades cotizados."
            )

    # ── Abono inicial (opcional) ──────────────────────────────────────────
    adelanto_monto = float(adelanto or 0.0)
    if adelanto_monto < 0:
        raise ValueError("El adelanto no puede ser negativo.")
    if adelanto_monto > 0 and not metodo_pago:
        raise ValueError("Debes indicar el método de pago del adelanto.")

    # Validar la tasa del abono ANTES de tocar cualquier registro:
    # así una conversión inválida no deja pedidos/facturas a medias.
    moneda_pago = moneda_adelanto_id or db_cotizacion.moneda_id
    tasa_pago = None
    if adelanto_monto > 0:
        misma_moneda = moneda_pago == db_cotizacion.moneda_id
        if misma_moneda:
            # Misma moneda que la factura: tasa 1:1, no requiere TRM.
            tasa_pago = 1.0
        else:
            tasa_explicita = float(tasa_cambio_adelanto) if tasa_cambio_adelanto else 0.0
            if tasa_explicita > 0:
                # La TRM indicada es COP por unidad de moneda del abono (p.ej. 1 USD = 4000 COP).
                # Convertirla a "unidades de la moneda de la venta" usando la tasa congelada de la
                # cotización (COP por unidad de la moneda de la venta): tasa_pago = TRM / tasa_venta.
                # La TRM explícita SIEMPRE tiene prioridad: el cliente paga días después y la
                # tasa congelada en la cotización puede ya no corresponder.
                tasa_venta = float(db_cotizacion.tasa_cambio or 1.0)
                if tasa_venta <= 0:
                    raise ValueError(
                        "La cotización no tiene una tasa de cambio válida para convertir la TRM del abono."
                    )
                tasa_pago = tasa_explicita / tasa_venta
            else:
                # Fallback: solo pares deducibles de la tasa de la cotización (venta USD ← pago COP).
                tasa_pago, derivada = _derivar_tasa_pago(db, db_cotizacion.moneda_id, moneda_pago, db_cotizacion.tasa_cambio)
                if not derivada or tasa_pago is None:
                    raise ValueError(
                        "La moneda del abono difiere de la moneda de la cotización. "
                        "Indica la tasa de cambio (TRM) del abono."
                    )

    # Cambiar estado de la cotización a APROBADA
    estado_cotizacion_anterior = db_cotizacion.estado
    db_cotizacion.estado = "APROBADA"

    # El pedido nace DIRECTAMENTE en PRODUCCION: la conversión de la cotización
    # ES la confirmación del pedido (no hay paso intermedio "aprobado" que
    # repetir en el tablero de pedidos). Las órdenes de producción de las líneas
    # FABRICADO se generan automáticamente más abajo. Solo un pedido sin líneas
    # a fabricar (reventa/insumos/exhibición) nace APROBADO: no tiene
    # producción, y desde ahí va directo a TERMINADO (envío automático).
    tiene_fabricables = any(
        _es_producible(d.get("tipo_item", "FABRICADO") if isinstance(d, dict) else d.tipo_item)
        for d in detalles
    )
    estado_pedido = "PRODUCCION" if tiene_fabricables else "APROBADO"
    db_pedido = model.Pedido(
        cotizacion_id=db_cotizacion.id,
        cliente_id=db_cotizacion.cliente_id,
        fecha=hoy_ve(),
        estado=estado_pedido,
        observaciones=db_cotizacion.observaciones,
        fecha_entrega_estimada=fecha_entrega_estimada,
        creado_por_id=usuario.id if usuario is not None else None,
        actualizado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_pedido)
    db.flush()

    cotizacion_detalles = db_cotizacion.detalles or []
    for idx, detalle in enumerate(detalles):
        detalle_dict = dict(detalle) if isinstance(detalle, dict) else detalle.model_dump()
        tipo = detalle_dict.get("tipo_item", "FABRICADO")
        dc_cot = cotizacion_detalles[idx] if idx < len(cotizacion_detalles) else None
        # Validar que el producto o material exista (REPARACION/SERVICIO no
        # referencian producto ni material: la pieza es del cliente o es un
        # cobro de flete/instalación).
        if tipo == "INSUMO":
            from app.modules.productos.model import Material as MaterialModel
            if not db.query(MaterialModel.id).filter(MaterialModel.id == detalle_dict.get("material_id")).first():
                raise ValueError(f"El material con id {detalle_dict.get('material_id')} no existe.")
        elif tipo not in ("REPARACION", "SERVICIO"):
            from app.modules.productos.model import Producto as ProductoModel
            if not db.query(ProductoModel.id).filter(ProductoModel.id == detalle_dict.get("producto_id")).first():
                raise ValueError(f"El producto con id {detalle_dict.get('producto_id')} no existe.")
        # Costo y dimensiones: FABRICADO/REVENTA toman el costo de la
        # cotización; INSUMO también propaga su costo real (compra + pasada,
        # que el frontend guarda en costo_total en COP), dividido por la
        # cantidad para obtener el costo unitario. REPARACION/SERVICIO toman el
        # costo total de su renglón por posición (no tienen producto que
        # identificar). Las dimensiones solo aplican a FABRICADO/REVENTA/REPARACION.
        if detalle_dict.get("costo_unitario") is None:
            dc_matched = None
            if tipo in ("REPARACION", "SERVICIO"):
                if dc_cot and dc_cot.costo_total:
                    dc_matched = dc_cot
            else:
                for dc in cotizacion_detalles:
                    if (dc.producto_id == detalle_dict.get("producto_id")
                            and dc.material_id == detalle_dict.get("material_id")
                            and dc.costo_total):
                        dc_matched = dc
                        break
            if dc_matched:
                if tipo == "INSUMO" and dc_matched.cantidad:
                    detalle_dict["costo_unitario"] = float(dc_matched.costo_total) / float(dc_matched.cantidad)
                else:
                    detalle_dict["costo_unitario"] = float(dc_matched.costo_total)
        if tipo not in ("INSUMO", "SERVICIO"):
            if detalle_dict.get("ancho") is None or detalle_dict.get("largo") is None:
                dc_dims = None
                if tipo == "REPARACION":
                    dc_dims = dc_cot
                else:
                    for dc in cotizacion_detalles:
                        if dc.producto_id == detalle_dict.get("producto_id"):
                            dc_dims = dc
                            break
                if dc_dims:
                    if detalle_dict.get("ancho") is None:
                        detalle_dict["ancho"] = float(dc_dims.ancho) if dc_dims.ancho else None
                    if detalle_dict.get("largo") is None:
                        detalle_dict["largo"] = float(dc_dims.largo) if dc_dims.largo else None
        if not detalle_dict.get("porcentaje_ganancia"):
            costo = detalle_dict.get("costo_unitario")
            precio = detalle_dict.get("precio", 0.0)
            if costo:
                # El costo está en COP; si la cotización es en otra moneda, el
                # precio debe convertirse a COP con la TRM congelada antes de
                # calcular el margen (mezclar USD con COP daba márgenes absurdos
                # como -99.96%).
                if db_cotizacion.moneda_id != 1:
                    precio = float(precio) * float(db_cotizacion.tasa_cambio or 1.0)
                margen = ((float(precio) - float(costo)) / float(costo)) * 100
                # Clamp: la columna es numeric(5,2) → máx 999.99. Un margen mayor
                # es dato inválido, pero no debe romper la conversión con un 500.
                detalle_dict["porcentaje_ganancia"] = min(999.99, round(margen, 2))
        db_detalle = model.DetallePedido(
            pedido_id=db_pedido.id,
            **detalle_dict
        )
        db.add(db_detalle)
    db.flush()

    # Promo obsequio: si la cotización no trajo el plástico de regalo, se
    # agrega aquí (1 obsequio por cada colchón con promo activa).
    _auto_agregar_obsequios(db, db_pedido, [
        d if isinstance(d, dict) else d.model_dump() for d in detalles
    ])

    # El pedido nació en PRODUCCION: generar las órdenes de producción de las
    # líneas FABRICADO/REPARACION (REVENTA/INSUMO/SERVICIO no se fabrican).
    # Mismo criterio que actualizar_pedido al pasar a PRODUCCION, pero sin paso
    # intermedio. Las órdenes de REPARACION quedan SIN producto (pieza del cliente).
    if estado_pedido == "PRODUCCION":
        from app.modules.production.model import OrdenProduccion
        for detalle in db_pedido.detalles:
            if not _es_producible(detalle.tipo_item):
                continue
            existente = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id == detalle.id).first()
            if not existente:
                db.add(OrdenProduccion(
                    detalle_pedido_id=detalle.id,
                    estado="PENDIENTE",
                    fecha_inicio=None,
                    fecha_fin=None,
                    creado_por_id=usuario.id if usuario is not None else None,
                    actualizado_por_id=usuario.id if usuario is not None else None,
                ))

    # ── Factura automática en la moneda de la cotización ──────────────────
    db_venta = venta_service.crear_venta_desde_pedido(
        db,
        VentaCreate(
            pedido_id=db_pedido.id,
            moneda_id=db_cotizacion.moneda_id,
            fecha=hoy_ve(),
        ),
        permitir_estado_cotizado=True,
        commit=False,  # la conversión commitea atómicamente al final
        usuario=usuario,
    )

    # ── Registrar el adelanto como primer pago de la factura (opcional) ───
    if adelanto_monto > 0:
        venta_service.crear_pago(
            db,
            PagoCreate(
                venta_id=db_venta.id,
                moneda_id=moneda_pago,
                fecha=hoy_ve(),
                monto=adelanto_monto,
                tasa_cambio=tasa_pago,
                metodo_pago=metodo_pago,
                referencia=f"Adelanto conversión cotización #{id_cotizacion}",
            ),
            commit=False,  # la conversión commitea atómicamente al final
            usuario=usuario,
        )

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="pedido",
        entity_id=db_pedido.id,
        after=_snapshot(db_pedido),
    )
    record_event(
        db,
        actor=usuario,
        action="STATE_CHANGE",
        entity_type="cotizacion",
        entity_id=db_cotizacion.id,
        before={"estado": estado_cotizacion_anterior},
        after={"estado": db_cotizacion.estado},
    )
    db.commit()
    db.refresh(db_pedido)
    return db_pedido


def obtener_rentabilidad_pedido(db: Session, id_pedido: int, usuario: Usuario | None = None):
    """Costo real vs estimado de un pedido para conocer el margen real.

    - Costo estimado de producción: Σ DetallePedido.costo_unitario × cantidad
      (lo que se cotizó, en moneda base).
    - Costo real de producción: Σ CostoProduccion.costo_total de las órdenes
      FABRICADO/REPARACION del pedido (materiales + MO + gastos de sección).
    - Flete real: costo del envío en moneda base (opcional).
    Todo lo que no está en moneda base se convierte con la TRM congelada del
    pedido (costo_unitario del detalle ya vive en COP)."""
    from app.modules.sales.model import Venta
    from app.modules.production.model import OrdenProduccion, CostoProduccion
    from app.modules.envios.model import Envio
    from app.modules.catalogos.model import Moneda

    pedido = db.query(model.Pedido).filter(model.Pedido.id == id_pedido).first()
    if not pedido:
        return None

    venta = db.query(Venta).filter(Venta.pedido_id == id_pedido).first()
    moneda_id = venta.moneda_id if venta else 1
    trm = float(venta.tasa_cambio) if venta and venta.tasa_cambio else 1.0
    moneda_codigo = None
    if moneda_id != 1:
        m = db.query(Moneda).filter(Moneda.id == moneda_id).first()
        moneda_codigo = m.codigo if m else None

    total_cobrado = 0.0
    costo_estimado = 0.0
    flete_cobrado_base = 0.0
    for dp in pedido.detalles:
        total_cobrado += float(dp.cantidad) * float(dp.precio)
        if dp.costo_unitario is not None:
            costo_estimado += float(dp.costo_unitario) * float(dp.cantidad)
        if (dp.tipo_item or "FABRICADO") == "SERVICIO":
            flete_cobrado_base += float(dp.cantidad) * float(dp.precio) * trm

    # Costo real de producción: sumar los costos finalizados de las órdenes.
    costo_real = 0.0
    n_ordenes = 0
    ordenes = (
        db.query(OrdenProduccion)
        .join(model.DetallePedido, model.DetallePedido.id == OrdenProduccion.detalle_pedido_id)
        .filter(model.DetallePedido.pedido_id == id_pedido)
        .all()
    )
    for orden in ordenes:
        n_ordenes += 1
        costo = db.query(CostoProduccion).filter(
            CostoProduccion.orden_produccion_id == orden.id
        ).first()
        if costo and costo.costo_total is not None:
            costo_real += float(costo.costo_total)

    envio = db.query(Envio).filter(Envio.pedido_id == id_pedido).first()
    flete_real_base = float(envio.costo_flete_en_moneda_base) if envio and envio.costo_flete_en_moneda_base else 0.0

    total_cobrado_base = total_cobrado * trm
    margen_estimado = total_cobrado_base - costo_estimado
    margen_real = total_cobrado_base - costo_real - flete_real_base

    return schemas.RentabilidadPedidoResponse(
        pedido_id=pedido.id,
        moneda_id=moneda_id,
        moneda_codigo=moneda_codigo,
        total_cobrado=round(total_cobrado, 2),
        total_cobrado_base=round(total_cobrado_base, 2),
        costo_estimado_produccion=round(costo_estimado, 2),
        costo_real_produccion=round(costo_real, 2),
        diferencia_costo=round(costo_real - costo_estimado, 2),
        flete_cobrado_base=round(flete_cobrado_base, 2),
        flete_real_base=round(flete_real_base, 2),
        margen_estimado=round(margen_estimado, 2),
        margen_real=round(margen_real, 2),
        tiene_produccion=n_ordenes > 0,
    )
