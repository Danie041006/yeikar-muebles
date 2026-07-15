from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.productos import model, schemas

# ------------------------------------------------------------
# Producto
# ------------------------------------------------------------
def obtener_producto(db: Session, id_producto: int):
    return db.query(model.Producto).filter(model.Producto.id == id_producto).first()

def obtener_productos(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Producto)
    if buscar:
        query = query.filter(
            or_(
                model.Producto.nombre.ilike(f"%{buscar}%"),
                model.Producto.codigo.ilike(f"%{buscar}%"),
                model.Producto.descripcion.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_producto(db: Session, esquema: schemas.ProductoCreate):
    db_obj = model.Producto(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_producto(db: Session, id_producto: int, esquema: schemas.ProductoUpdate):
    db_obj = obtener_producto(db, id_producto)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_producto(db: Session, id_producto: int):
    db_obj = obtener_producto(db, id_producto)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Material
# ------------------------------------------------------------
def obtener_material(db: Session, id_material: int):
    return db.query(model.Material).filter(model.Material.id == id_material).first()

def obtener_materiales(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Material)
    if buscar:
        query = query.filter(model.Material.nombre.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()

def crear_material(db: Session, esquema: schemas.MaterialCreate):
    db_obj = model.Material(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_material(db: Session, id_material: int, esquema: schemas.MaterialUpdate):
    db_obj = obtener_material(db, id_material)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_material(db: Session, id_material: int):
    db_obj = obtener_material(db, id_material)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True
