from sqlalchemy.orm import Session
from sqlalchemy import or_, extract
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


def obtener_cotizacion(db: Session, id_cotizacion: int, usuario: Usuario | None = None):
    query = db.query(model.Cotizacion).filter(model.Cotizacion.id == id_cotizacion)
    if usuario is not None:
        query = filtrar_registros_propios(query, model.Cotizacion.creado_por_id, usuario)
    return query.first()

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

    # Date/history filters
    if mes is not None or anio is not None:
        if mes is not None:
            query = query.filter(extract('month', model.Cotizacion.fecha) == mes)
        if anio is not None:
            query = query.filter(extract('year', model.Cotizacion.fecha) == anio)
    elif solo_mes_actual:
        today = date.today()
        query = query.filter(
            extract('month', model.Cotizacion.fecha) == today.month,
            extract('year', model.Cotizacion.fecha) == today.year
        )

    return query.offset(salto).limit(limite).all()

def crear_cotizacion(db: Session, esquema: schemas.CotizacionCreate, usuario: Usuario | None = None):
    datos = esquema.model_dump(exclude={"detalles"})
    detalles_datos = esquema.detalles

    if datos.get("moneda_id", MONEDA_BASE_ID) != MONEDA_BASE_ID:
        datos["total_en_moneda_base"] = float(datos.get("total_estimado", 0)) * float(datos.get("tasa_cambio", 1))
    else:
        datos["tasa_cambio"] = 1.0
        datos["total_en_moneda_base"] = datos.get("total_estimado", 0)
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
