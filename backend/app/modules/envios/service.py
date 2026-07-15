from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from datetime import datetime
from app.modules.envios.model import Envio
from app.modules.envios import schemas
from app.modules.orders.model import Pedido
from app.modules.clients.model import Client
from app.modules.empleados.model import Empleado
def obtener_envio(db: Session, id_envio: int):
    return db.query(Envio).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        joinedload(Envio.empleado)
    ).filter(Envio.id == id_envio).first()
def obtener_envios(db: Session, salto: int = 0, limite: int = 100, buscar: str = None, estado: str = None):
    query = db.query(Envio).options(
        joinedload(Envio.pedido).joinedload(Pedido.cliente),
        joinedload(Envio.pedido).joinedload(Pedido.detalles),
        joinedload(Envio.empleado)
    )
    
    if estado:
        query = query.filter(Envio.estado == estado)
        
    if buscar:
        # Join to filter by client name or other properties
        query = query.join(Envio.pedido).join(Pedido.cliente).filter(
            or_(
                Client.nombre.ilike(f"%{buscar}%"),
                Envio.guia_despacho.ilike(f"%{buscar}%"),
                Envio.direccion_entrega.ilike(f"%{buscar}%"),
                Envio.observaciones.ilike(f"%{buscar}%")
            )
        )
        
    return query.offset(salto).limit(limite).all()
def crear_envio(db: Session, esquema: schemas.EnvioCreate):
    # Verificar si ya existe envío para este pedido
    existente = db.query(Envio).filter(Envio.pedido_id == esquema.pedido_id).first()
    if existente:
        raise ValueError("Ya existe un registro de envío para este pedido.")
        
    # Crear envío
    db_envio = Envio(**esquema.model_dump())
    db.add(db_envio)
    
    # Asegurar que el estado del pedido esté sincronizado si se entrega
    if esquema.estado == "ENTREGADO":
        db_envio.fecha_entrega = datetime.now()
        pedido = db.query(Pedido).filter(Pedido.id == esquema.pedido_id).first()
        if pedido:
            pedido.estado = "ENTREGADO"
    elif esquema.estado == "EN_TRANSITO":
        db_envio.fecha_salida = datetime.now()
        
    db.commit()
    db.refresh(db_envio)
    return db_envio
def crear_envio_automatico(db: Session, pedido_id: int):
    # Verificar si ya existe envío
    existente = db.query(Envio).filter(Envio.pedido_id == pedido_id).first()
    if existente:
        return existente
        
    # Obtener el pedido y dirección del cliente
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    direccion = ""
    if pedido and pedido.cliente:
        direccion = pedido.cliente.direccion or ""
        
    db_envio = Envio(
        pedido_id=pedido_id,
        estado="PREPARADO",
        direccion_entrega=direccion,
        empleado_id=None,
        fecha_salida=None,
        fecha_entrega=None,
        guia_despacho=None,
        observaciones="Creado automáticamente tras finalizar producción."
    )
    
    db.add(db_envio)
    db.commit()
    db.refresh(db_envio)
    return db_envio
def actualizar_envio(db: Session, id_envio: int, esquema: schemas.EnvioUpdate):
    db_envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not db_envio:
        return None
        
    datos = esquema.model_dump(exclude_unset=True)
    estado_anterior = db_envio.estado
    nuevo_estado = datos.get("estado")
    
    for campo, valor in datos.items():
        setattr(db_envio, campo, valor)
        
    # Lógica de transición de fechas y estados
    if nuevo_estado and nuevo_estado != estado_anterior:
        if nuevo_estado == "EN_TRANSITO" and not db_envio.fecha_salida:
            db_envio.fecha_salida = datetime.now()
        elif nuevo_estado == "ENTREGADO":
            db_envio.fecha_entrega = datetime.now()
            # Si se entrega el despacho, el pedido asociado pasa a ENTREGADO
            pedido = db.query(Pedido).filter(Pedido.id == db_envio.pedido_id).first()
            if pedido:
                pedido.estado = "ENTREGADO"
                
    db.commit()
    db.refresh(db_envio)
    return db_envio
def eliminar_envio(db: Session, id_envio: int):
    db_envio = db.query(Envio).filter(Envio.id == id_envio).first()
    if not db_envio:
        return False
    db.delete(db_envio)
    db.commit()
    return True
