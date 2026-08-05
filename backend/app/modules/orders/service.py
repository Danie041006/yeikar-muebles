from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import or_, extract
from app.modules.orders import model, schemas
from app.modules.quotes.model import Cotizacion
from app.modules.clients.model import Client
from app.modules.catalogos.model import Moneda
from app.modules.sales import service as venta_service
from app.modules.sales.schemas import VentaCreate, PagoCreate

def obtener_pedido(db: Session, id_pedido: int):
    return db.query(model.Pedido).filter(model.Pedido.id == id_pedido).first()

def obtener_pedidos(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    solo_mes_actual: bool = True,
    mes: int = None,
    anio: int = None
):
    query = db.query(model.Pedido)
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

    return query.offset(salto).limit(limite).all()

def crear_pedido(db: Session, esquema: schemas.PedidoCreate):
    # Crear cabecera de pedido
    pedido_datos = esquema.model_dump(exclude={"detalles"})
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

    db.commit()
    db.refresh(db_pedido)
    return db_pedido

def actualizar_pedido(db: Session, id_pedido: int, esquema: schemas.PedidoUpdate):
    # FOR UPDATE: dos transiciones simultáneas a PRODUCCION se serializan; el
    # segundo request ve el estado ya cambiado y no duplica las órdenes.
    db_pedido = db.query(model.Pedido).filter(model.Pedido.id == id_pedido).with_for_update().first()
    if not db_pedido:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    
    estado_anterior = db_pedido.estado
    nuevo_estado = datos.get("estado")
    
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
                    fecha_fin=None
                )
                db.add(db_orden)

    db.commit()
    db.refresh(db_pedido)
    return db_pedido

def eliminar_pedido(db: Session, id_pedido: int):
    db_pedido = obtener_pedido(db, id_pedido)
    if not db_pedido:
        return False
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
):
    # Buscar la cotización con FOR UPDATE: dos conversiones simultáneas quedan
    # serializadas; la segunda detecta el pedido ya creado en vez de lanzar 500.
    db_cotizacion = db.query(Cotizacion).filter(Cotizacion.id == id_cotizacion).with_for_update().first()
    if not db_cotizacion:
        raise ValueError("Cotizacion no encontrada")

    # Idempotencia: si la cotización ya fue convertida, devolver el pedido existente
    pedido_existente = db.query(model.Pedido).filter(model.Pedido.cotizacion_id == id_cotizacion).first()
    if pedido_existente:
        raise ValueError("Esta cotización ya fue convertida a pedido")

    # Validar detalles
    if not detalles:
        raise ValueError("El pedido requiere al menos un detalle de producto")

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
        tasa_pago, derivada = _derivar_tasa_pago(db, db_cotizacion.moneda_id, moneda_pago, db_cotizacion.tasa_cambio)
        if not derivada:
            if not tasa_cambio_adelanto or float(tasa_cambio_adelanto) <= 0:
                raise ValueError(
                    "La moneda del abono no se puede convertir con la tasa de la cotización. "
                    "Indica la tasa de cambio (TRM) del abono."
                )
            # La TRM indicada es COP por unidad de moneda del abono (p.ej. 1 VES = 10 COP).
            # Convertirla a "unidades de la moneda de la venta" usando la tasa congelada de la
            # cotización (COP por unidad de la moneda de la venta): tasa_pago = TRM / tasa_venta.
            tasa_venta = float(db_cotizacion.tasa_cambio or 1.0)
            if tasa_venta <= 0:
                raise ValueError(
                    "La cotización no tiene una tasa de cambio válida para convertir la TRM del abono."
                )
            tasa_pago = float(tasa_cambio_adelanto) / tasa_venta

    # Cambiar estado de la cotización a APROBADA
    db_cotizacion.estado = "APROBADA"

    # Crear la cabecera de pedido basada en la cotización
    db_pedido = model.Pedido(
        cotizacion_id=db_cotizacion.id,
        cliente_id=db_cotizacion.cliente_id,
        fecha=date.today(),
        estado="COTIZADO",
        observaciones=db_cotizacion.observaciones,
        fecha_entrega_estimada=fecha_entrega_estimada
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
        # Si el detalle no trae costo, intentar completarlo desde la cotización
        if not detalle_dict.get("costo_unitario"):
            for dc in (db_cotizacion.detalles or []):
                if dc.producto_id == detalle_dict.get("producto_id"):
                    detalle_dict["costo_unitario"] = float(dc.costo_total or 0.0)
                    break
        if not detalle_dict.get("porcentaje_ganancia"):
            costo = detalle_dict.get("costo_unitario")
            precio = detalle_dict.get("precio", 0.0)
            if costo:
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
        )

    db.commit()
    db.refresh(db_pedido)
    return db_pedido
