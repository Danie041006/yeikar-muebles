from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.clients import model, schemas

def get_client(db: Session, client_id: int):
    return db.query(model.Client).filter(model.Client.id == client_id).first()

def get_client_by_email(db: Session, email: str):
    return db.query(model.Client).filter(model.Client.email == email).first()

def get_clients(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    search: str = None
):
    query = db.query(model.Client)
    
    if search:
        query = query.filter(
            or_(
                model.Client.nombre.ilike(f"%{search}%"),
                model.Client.email.ilike(f"%{search}%"),
                model.Client.telefono.ilike(f"%{search}%")
            )
        )
    
    return query.offset(skip).limit(limit).all()

def create_client(db: Session, client: schemas.ClientCreate):
    # Verificar si el email ya existe (si se proporcionó)
    if client.email:
        existing = get_client_by_email(db, client.email)
        if existing:
            raise ValueError(f"Ya existe un cliente con el email {client.email}")
    
    db_client = model.Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client

def update_client(db: Session, client_id: int, client_update: schemas.ClientUpdate):
    db_client = get_client(db, client_id)
    if not db_client:
        return None
    
    update_data = client_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_client, field, value)
    
    db.commit()
    db.refresh(db_client)
    return db_client

def delete_client(db: Session, client_id: int):
    db_client = get_client(db, client_id)
    if not db_client:
        return False
    
    db.delete(db_client)
    db.commit()
    return True