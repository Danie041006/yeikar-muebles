from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import or_, extract
from app.modules.orders import model, schemas
from app.modules.quotes.model import Cotizacion
from app.modules.clients.model import Client

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
    db_pedido = obtener_pedido(db, id_pedido)
    if not db_pedido:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    
    estado_anterior = db_pedido.estado
    nuevo_estado = datos.get("estado")
    
    for campo, valor in datos.items():
        setattr(db_pedido, campo, valor)
    db.commit()
    db.refresh(db_pedido)
    
    # If transitioning to PRODUCCION, generate production orders and stages
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
                db.flush()
        db.commit()
        
    return db_pedido

def eliminar_pedido(db: Session, id_pedido: int):
    db_pedido = obtener_pedido(db, id_pedido)
    if not db_pedido:
        return False
    db.delete(db_pedido)
    db.commit()
    return True

def convertir_cotizacion_a_pedido(db: Session, id_cotizacion: int, fecha_entrega_estimada = None, detalles = []):
    # Buscar la cotización
    db_cotizacion = db.query(Cotizacion).filter(Cotizacion.id == id_cotizacion).first()
    if not db_cotizacion:
        raise ValueError("Cotizacion no encontrada")

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

    # Si se pasan detalles, usarlos. Si no, lanzar error de que requiere detalles
    if not detalles:
        raise ValueError("El pedido requiere al menos un detalle de producto")

    for detalle in detalles:
        db_detalle = model.DetallePedido(
            pedido_id=db_pedido.id,
            **detalle
        )
        db.add(db_detalle)

    db.commit()
    db.refresh(db_pedido)
    return db_pedido
