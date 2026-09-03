from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date
from app.modules.quotes import model, schemas
from app.modules.clients.model import Client
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario

MONEDA_BASE_ID = 1  # COP

def _snapshot(cotizacion: model.Cotizacion) -> dict:
    return {
        "cliente_id": cotizacion.cliente_id,
        "fecha": cotizacion.fecha,
        "estado": cotizacion.estado,
        "total_estimado": cotizacion.total_estimado,
        "moneda_id": cotizacion.moneda_id,
        "observaciones": cotizacion.observaciones,
    }


def _anotar_pedido(db: Session, cotizaciones: list):
    """Marca en cada cotización su pedido asociado (si ya fue convertida).

    No es una columna: se anota sobre el objeto ORM como atributo transitorio
    para que la API (from_attributes) lo exponga como pedido_id/pedido_estado.
    Un solo query batch para toda la página, no N+1.
    """
    if not cotizaciones:
        return
    from app.modules.orders.model import Pedido
    ids = [c.id for c in cotizaciones]
    filas = db.query(Pedido.cotizacion_id, Pedido.id, Pedido.estado).filter(
        Pedido.cotizacion_id.in_(ids)
    ).all()
    por_cotizacion = {cot_id: (pid, estado) for cot_id, pid, estado in filas}
    for cot in cotizaciones:
        pareja = por_cotizacion.get(cot.id)
        cot.pedido_id = pareja[0] if pareja else None
        cot.pedido_estado = pareja[1] if pareja else None


def obtener_cotizacion(db: Session, id_cotizacion: int, usuario: Usuario | None = None):
    query = db.query(model.Cotizacion).filter(model.Cotizacion.id == id_cotizacion)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Cotizacion.creado_por_id, usuario)
    cotizacion = query.first()
    if cotizacion:
        _anotar_pedido(db, [cotizacion])
    return cotizacion

def obtener_cotizaciones(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    solo_mes_actual: bool = True,
    mes: int = None,
    anio: int = None,
    usuario: Usuario | None = None,
):
    query = db.query(model.Cotizacion)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Cotizacion.creado_por_id, usuario)
    if buscar:
        query = query.join(Client).filter(
            or_(
                model.Cotizacion.observaciones.ilike(f"%{buscar}%"),
                model.Cotizacion.estado.ilike(f"%{buscar}%"),
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
            query = query.filter(model.Cotizacion.fecha >= inicio, model.Cotizacion.fecha < fin)
        elif anio is not None:
            query = query.filter(
                model.Cotizacion.fecha >= date(anio, 1, 1),
                model.Cotizacion.fecha < date(anio + 1, 1, 1),
            )
        else:
            # Solo mes sin año: se asume el año en curso.
            today = date.today()
            inicio = date(today.year, mes, 1)
            if mes == 12:
                fin = date(today.year + 1, 1, 1)
            else:
                fin = date(today.year, mes + 1, 1)
            query = query.filter(model.Cotizacion.fecha >= inicio, model.Cotizacion.fecha < fin)
    elif solo_mes_actual:
        today = date.today()
        if today.month == 12:
            fin = date(today.year + 1, 1, 1)
        else:
            fin = date(today.year, today.month + 1, 1)
        query = query.filter(
            model.Cotizacion.fecha >= date(today.year, today.month, 1),
            model.Cotizacion.fecha < fin,
        )

    query = query.order_by(model.Cotizacion.fecha.desc(), model.Cotizacion.id.desc())

    cotizaciones = query.offset(salto).limit(limite).all()
    _anotar_pedido(db, cotizaciones)
    return cotizaciones

def _validar_consistencia_detalles(moneda_id, total_estimado, detalles):
    """Defensa en profundidad: cuando la cotización es en moneda extranjera, los
    precios de los detalles deben estar expresados en esa moneda. Si la suma
    precio × cantidad no cuadra con el total_estimado, el precio se envió sin
    convertir (p. ej. un monto COP guardado como USD infla el total de la factura)."""
    if moneda_id == MONEDA_BASE_ID:
        return
    if not detalles:
        return
    suma = sum(float(d.precio or 0) * float(d.cantidad or 1) for d in detalles)
    total = float(total_estimado or 0)
    if total <= 0 or suma <= 0:
        return
    tolerancia = max(total * 0.02, 1.0)
    if abs(suma - total) > tolerancia:
        raise ValueError(
            f"La suma de los precios de los detalles ({suma:,.2f}) no coincide con el "
            f"total estimado de la cotización ({total:,.2f}). En cotizaciones en moneda "
            f"extranjera los precios deben enviarse convertidos a esa moneda "
            f"(precio ÷ tasa de cambio). Revisa los precios de los productos."
        )

def crear_cotizacion(db: Session, esquema: schemas.CotizacionCreate, usuario: Usuario | None = None):
    datos = esquema.model_dump(exclude={"detalles"})
    detalles_datos = esquema.detalles

    if datos.get("moneda_id", MONEDA_BASE_ID) != MONEDA_BASE_ID:
        datos["total_en_moneda_base"] = float(datos.get("total_estimado", 0)) * float(datos.get("tasa_cambio", 1))
    else:
        datos["tasa_cambio"] = 1.0
        datos["total_en_moneda_base"] = datos.get("total_estimado", 0)
    _validar_consistencia_detalles(datos.get("moneda_id", MONEDA_BASE_ID), datos.get("total_estimado", 0), detalles_datos)
    if usuario is not None:
        datos["creado_por_id"] = usuario.id
        datos["actualizado_por_id"] = usuario.id

    db_obj = model.Cotizacion(**datos)
    db.add(db_obj)
    db.flush()

    for det in detalles_datos:
        db_det = model.DetalleCotizacion(
            cotizacion_id=db_obj.id,
            **det.model_dump()
        )
        db.add(db_det)

    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="cotizacion",
        entity_id=db_obj.id,
        after=_snapshot(db_obj),
    )
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_cotizacion(
    db: Session,
    id_cotizacion: int,
    esquema: schemas.CotizacionUpdate,
    usuario: Usuario | None = None,
):
    db_obj = obtener_cotizacion(db, id_cotizacion, usuario)
    if not db_obj:
        return None
    antes = _snapshot(db_obj)
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    # Recalcular total_en_moneda_base si cambió total, moneda o tasa (antes quedaba stale)
    if "total_estimado" in datos or "moneda_id" in datos or "tasa_cambio" in datos:
        if db_obj.moneda_id == MONEDA_BASE_ID:
            db_obj.tasa_cambio = 1.0
            db_obj.total_en_moneda_base = db_obj.total_estimado
        else:
            if not db_obj.tasa_cambio or float(db_obj.tasa_cambio) <= 0:
                raise ValueError("La cotización en moneda extranjera requiere una tasa de cambio mayor que cero.")
            db_obj.total_en_moneda_base = float(db_obj.total_estimado or 0) * float(db_obj.tasa_cambio)
    if usuario is not None:
        db_obj.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="UPDATE" if "estado" not in datos else "STATE_CHANGE",
        entity_type="cotizacion",
        entity_id=db_obj.id,
        before=antes,
        after=_snapshot(db_obj),
    )
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_cotizacion(db: Session, id_cotizacion: int, usuario: Usuario | None = None):
    db_obj = obtener_cotizacion(db, id_cotizacion, usuario)
    if not db_obj:
        return False
    
    # Verificar si está asociada a un pedido
    from app.modules.orders.model import Pedido
    pedido_asociado = db.query(Pedido).filter(Pedido.cotizacion_id == id_cotizacion).first()
    if pedido_asociado:
        raise ValueError(f"No se puede eliminar la cotización porque está asociada al pedido #{pedido_asociado.id}.")

    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="cotizacion",
        entity_id=db_obj.id,
        before=_snapshot(db_obj),
    )
    db.delete(db_obj)
    db.commit()
    return True
