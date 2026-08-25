from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import or_, extract
from app.modules.orders import model, schemas
from app.modules.quotes.model import Cotizacion
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda
from app.modules.sales import service as venta_service
from app.modules.sales.schemas import VentaCreate, PagoCreate
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios, tiene_alcance_total
from app.modules.users.model import Usuario
from app.core.state_machine import TRANSICIONES_PEDIDO, validar_transicion

def _snapshot(pedido: model.Pedido) -> dict:
    return {
        "cotizacion_id": pedido.cotizacion_id,
        "cliente_id": pedido.cliente_id,
        "fecha": pedido.fecha,
        "estado": pedido.estado,
        "fecha_entrega_estimada": pedido.fecha_entrega_estimada,
        "observaciones": pedido.observaciones,
    }


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

    # Date/history filters
    if mes is not None or anio is not None:
        if mes is not None:
            query = query.filter(extract('month', model.Pedido.fecha) == mes)
        if anio is not None:
            query = query.filter(extract('year', model.Pedido.fecha) == anio)
    elif solo_mes_actual:
        today = date.today()
        query = query.filter(
            extract('month', model.Pedido.fecha) == today.month,
            extract('year', model.Pedido.fecha) == today.year
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
    for detalle_esquema in esquema.detalles:
        db_detalle = model.DetallePedido(
            pedido_id=db_pedido.id,
            **detalle_esquema.model_dump()
        )
        db.add(db_detalle)

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
        # PRODUCCION → TERMINADO manual: exigir que TODAS las órdenes de
        # producción del pedido estén FINALIZADA (no se "come" la producción).
        if estado_anterior == "PRODUCCION" and nuevo_estado == "TERMINADO":
            from app.modules.production.model import OrdenProduccion
            n_detalles = db.query(model.DetallePedido).filter(
                model.DetallePedido.pedido_id == db_pedido.id
            ).count()
            n_ordenes_finalizadas = db.query(OrdenProduccion).join(
                model.DetallePedido, model.DetallePedido.id == OrdenProduccion.detalle_pedido_id
            ).filter(
                model.DetallePedido.pedido_id == db_pedido.id,
                OrdenProduccion.estado == "FINALIZADA",
            ).count()
            if n_detalles == 0 or n_ordenes_finalizadas != n_detalles:
                raise ValueError(
                    "No se puede marcar el pedido como TERMINADO: todas las líneas del pedido "
                    "deben tener su orden de producción FINALIZADA."
                )
    
    for campo, valor in datos.items():
        setattr(db_pedido, campo, valor)
    
    # If transitioning to PRODUCCION, generate production orders and stages
    # Todo en la MISMA transacción: un crash no puede dejar el pedido en
    # PRODUCCION sin sus órdenes de producción.
    if estado_anterior != "PRODUCCION" and nuevo_estado == "PRODUCCION":
        from app.modules.production.model import OrdenProduccion
        from datetime import date
        
        for detalle in db_pedido.detalles:
            existente = db.query(OrdenProduccion).filter(OrdenProduccion.detalle_pedido_id == detalle.id).first()
            if not existente:
                db_orden = OrdenProduccion(
                    detalle_pedido_id=detalle.id,
                    estado="EN_PRODUCCION",
                    fecha_inicio=date.today(),
                    fecha_fin=None,
                    creado_por_id=usuario.id if usuario is not None else None,
                    actualizado_por_id=usuario.id if usuario is not None else None,
                )
                db.add(db_orden)

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
    if usuario is not None:
        cotizacion_query = filtrar_registros_propios(cotizacion_query, Cotizacion.creado_por_id, usuario)
    db_cotizacion = cotizacion_query.with_for_update().first()
    if not db_cotizacion:
        raise ValueError("Cotizacion no encontrada")

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

    # Validar que los precios/cantidades coincidan con los de la cotización:
    # una cotización de 2.6M no puede convertirse en una factura de 1 peso.
    detalles_cotizacion = {dc.producto_id: dc for dc in (db_cotizacion.detalles or [])}
    for detalle in detalles:
        detalle_dict = detalle if isinstance(detalle, dict) else detalle.model_dump()
        dc = detalles_cotizacion.get(detalle_dict.get("producto_id"))
        if dc is None:
            raise ValueError(
                f"El producto {detalle_dict.get('producto_id')} no forma parte de la cotización. "
                "El pedido debe copiar exactamente los renglones cotizados."
            )
        precio_enviado = float(detalle_dict.get("precio", 0) or 0)
        precio_cotizado = float(dc.precio)
        cantidad_enviada = float(detalle_dict.get("cantidad", 0) or 0)
        cantidad_cotizada = float(dc.cantidad)
        if abs(precio_enviado - precio_cotizado) > 0.01 or abs(cantidad_enviada - cantidad_cotizada) > 0.001:
            raise ValueError(
                f"El detalle del producto {dc.producto_id} no coincide con la cotización: "
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

    # Crear la cabecera de pedido basada en la cotización
    db_pedido = model.Pedido(
        cotizacion_id=db_cotizacion.id,
        cliente_id=db_cotizacion.cliente_id,
        fecha=date.today(),
        estado="COTIZADO",
        observaciones=db_cotizacion.observaciones,
        fecha_entrega_estimada=fecha_entrega_estimada,
        creado_por_id=usuario.id if usuario is not None else None,
        actualizado_por_id=usuario.id if usuario is not None else None,
    )
    db.add(db_pedido)
    db.flush()

    for detalle in detalles:
        # Validar que el producto exista (evita IntegrityError 500/409 engañoso)
        detalle_dict = dict(detalle) if isinstance(detalle, dict) else detalle.model_dump()
        from app.modules.productos.model import Producto as ProductoModel
        producto_existe = db.query(ProductoModel.id).filter(
            ProductoModel.id == detalle_dict.get("producto_id")
        ).first()
        if not producto_existe:
            raise ValueError(
                f"El producto con id {detalle_dict.get('producto_id')} no existe. "
                "No se puede convertir la cotización con un producto inexistente."
            )
        # Si el detalle no trae costo, intentar completarlo desde la cotización.
        # Nunca escribir 0.0: el fallback al precio_costo_base del producto en la
        # venta exige NULL (0.0 es un costo falso que rompe el margen).
        if detalle_dict.get("costo_unitario") is None:
            for dc in (db_cotizacion.detalles or []):
                if dc.producto_id == detalle_dict.get("producto_id"):
                    detalle_dict["costo_unitario"] = float(dc.costo_total) if dc.costo_total else None
                    break
        # Las dimensiones (ancho/largo) cotizadas deben pasar al pedido: son las
        # que usa producción para escalar la receta y mostrar el tamaño en el
        # kanban. Antes se perdían en la conversión y el tablero las mostraba vacías.
        if detalle_dict.get("ancho") is None or detalle_dict.get("largo") is None:
            for dc in (db_cotizacion.detalles or []):
                if dc.producto_id == detalle_dict.get("producto_id"):
                    if detalle_dict.get("ancho") is None:
                        detalle_dict["ancho"] = float(dc.ancho) if dc.ancho else None
                    if detalle_dict.get("largo") is None:
                        detalle_dict["largo"] = float(dc.largo) if dc.largo else None
                    break
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

    # ── Factura automática en la moneda de la cotización ──────────────────
    db_venta = venta_service.crear_venta_desde_pedido(
        db,
        VentaCreate(
            pedido_id=db_pedido.id,
            moneda_id=db_cotizacion.moneda_id,
            fecha=date.today(),
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
                fecha=date.today(),
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
