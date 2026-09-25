from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.empleados import model, schemas

def obtener_empleado(db: Session, id_empleado: int):
    return db.query(model.Empleado).filter(model.Empleado.id == id_empleado).first()

def obtener_empleados(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Empleado)
    if buscar:
        query = query.filter(
            or_(
                model.Empleado.nombre.ilike(f"%{buscar}%"),
                model.Empleado.telefono.ilike(f"%{buscar}%")
            )
        )
    total = query.count()
    items = query.order_by(model.Empleado.nombre.asc()).offset(salto).limit(limite).all()
    return items, total

def crear_empleado(db: Session, esquema: schemas.EmpleadoCreate):
    db_obj = model.Empleado(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_empleado(db: Session, id_empleado: int, esquema: schemas.EmpleadoUpdate):
    db_obj = obtener_empleado(db, id_empleado)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_empleado(db: Session, id_empleado: int):
    db_obj = obtener_empleado(db, id_empleado)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True
