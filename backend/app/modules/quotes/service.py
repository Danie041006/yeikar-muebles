from sqlalchemy.orm import Session
from sqlalchemy import or_, extract
from datetime import date
from app.modules.quotes import model, schemas
from app.modules.clients.model import Client

def obtener_cotizacion(db: Session, id_cotizacion: int):
    return db.query(model.Cotizacion).filter(model.Cotizacion.id == id_cotizacion).first()

def obtener_cotizaciones(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    solo_mes_actual: bool = True,
    mes: int = None,
    anio: int = None
):
    query = db.query(model.Cotizacion)
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

def crear_cotizacion(db: Session, esquema: schemas.CotizacionCreate):
    datos = esquema.model_dump(exclude={"detalles"})
    detalles_datos = esquema.detalles
    
    db_obj = model.Cotizacion(**datos)
    db.add(db_obj)
    db.flush()  # Obtener el ID de la cotización
    
    for det in detalles_datos:
        db_det = model.DetalleCotizacion(
            cotizacion_id=db_obj.id,
            **det.model_dump()
        )
        db.add(db_det)
        
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_cotizacion(db: Session, id_cotizacion: int, esquema: schemas.CotizacionUpdate):
    db_obj = obtener_cotizacion(db, id_cotizacion)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_cotizacion(db: Session, id_cotizacion: int):
    db_obj = obtener_cotizacion(db, id_cotizacion)
    if not db_obj:
        return False
    
    # Verificar si está asociada a un pedido
    from app.modules.orders.model import Pedido
    pedido_asociado = db.query(Pedido).filter(Pedido.cotizacion_id == id_cotizacion).first()
    if pedido_asociado:
        raise ValueError(f"No se puede eliminar la cotización porque está asociada al pedido #{pedido_asociado.id}.")

    db.delete(db_obj)
    db.commit()
    return True

