from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.clients import model, schemas
from app.modules.auditoria.service import record_event
from app.modules.users.deps import filtrar_registros_propios
from app.modules.users.model import Usuario

def _snapshot(client: model.Client) -> dict:
    return {
        "nombre": client.nombre,
        "telefono": client.telefono,
        "direccion": client.direccion,
        "ciudad": client.ciudad,
    }


def get_client(
    db: Session,
    client_id: int,
    usuario: Usuario | None = None,
    solo_propios: bool = False,
):
    query = db.query(model.Client).filter(model.Client.id == client_id)
    # El directorio de clientes es compartido para que cualquier vendedor pueda
    # identificar clientes existentes. La escritura continúa siendo propia.
    if solo_propios and usuario is not None:
        query = filtrar_registros_propios(query, model.Client.creado_por_id, usuario)
    return query.first()

def get_clients(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search: str = None,
    usuario: Usuario | None = None,
):
    # Los nombres de clientes son un catálogo operativo compartido. No se
    # filtra por creador en lectura; los mutadores sí validan propiedad.
    query = db.query(model.Client)
    
    if search:
        query = query.filter(
            or_(
                model.Client.nombre.ilike(f"%{search}%"),
                model.Client.telefono.ilike(f"%{search}%")
            )
        )
    
    return query.order_by(model.Client.id.desc()).offset(skip).limit(limit).all()

def create_client(db: Session, client: schemas.ClientCreate, usuario: Usuario | None = None):
    datos = client.model_dump()
    if usuario is not None:
        datos["creado_por_id"] = usuario.id
        datos["actualizado_por_id"] = usuario.id
    db_client = model.Client(**datos)
    db.add(db_client)
    db.flush()
    record_event(
        db,
        actor=usuario,
        action="CREATE",
        entity_type="cliente",
        entity_id=db_client.id,
        after=_snapshot(db_client),
    )
    db.commit()
    db.refresh(db_client)
    return db_client

def update_client(
    db: Session,
    client_id: int,
    client_update: schemas.ClientUpdate,
    usuario: Usuario | None = None,
):
    db_client = get_client(db, client_id, usuario, solo_propios=True)
    if not db_client:
        return None
    
    antes = _snapshot(db_client)
    update_data = client_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_client, field, value)
    
    if usuario is not None:
        db_client.actualizado_por_id = usuario.id
    record_event(
        db,
        actor=usuario,
        action="UPDATE",
        entity_type="cliente",
        entity_id=db_client.id,
        before=antes,
        after=_snapshot(db_client),
    )
    db.commit()
    db.refresh(db_client)
    return db_client

def delete_client(db: Session, client_id: int, usuario: Usuario | None = None):
    db_client = get_client(db, client_id, usuario, solo_propios=True)
    if not db_client:
        return False
    
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="cliente",
        entity_id=db_client.id,
        before=_snapshot(db_client),
    )
    db.delete(db_client)
    db.commit()
    return True
