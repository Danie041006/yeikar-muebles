from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.proveedores import model, schemas

def obtener_proveedor(db: Session, id_proveedor: int):
    return db.query(model.Proveedor).filter(model.Proveedor.id == id_proveedor).first()

def obtener_proveedores(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Proveedor)
    if buscar:
        query = query.filter(
            or_(
                model.Proveedor.nombre.ilike(f"%{buscar}%"),
                model.Proveedor.email.ilike(f"%{buscar}%"),
                model.Proveedor.telefono.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_proveedor(db: Session, esquema: schemas.ProveedorCreate):
    db_obj = model.Proveedor(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_proveedor(db: Session, id_proveedor: int, esquema: schemas.ProveedorUpdate):
    db_obj = obtener_proveedor(db, id_proveedor)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_proveedor(db: Session, id_proveedor: int):
    db_obj = obtener_proveedor(db, id_proveedor)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True
