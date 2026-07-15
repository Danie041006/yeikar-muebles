from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.catalogos import model, schemas

# ------------------------------------------------------------
# TipoProducto
# ------------------------------------------------------------
def obtener_tipo_producto(db: Session, id_tipo: int):
    return db.query(model.TipoProducto).filter(model.TipoProducto.id == id_tipo).first()

def obtener_tipos_productos(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.TipoProducto)
    if buscar:
        query = query.filter(model.TipoProducto.nombre.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()

def crear_tipo_producto(db: Session, esquema: schemas.TipoProductoCreate):
    db_obj = model.TipoProducto(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_tipo_producto(db: Session, id_tipo: int, esquema: schemas.TipoProductoUpdate):
    db_obj = obtener_tipo_producto(db, id_tipo)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_tipo_producto(db: Session, id_tipo: int):
    db_obj = obtener_tipo_producto(db, id_tipo)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# UnidadMedida
# ------------------------------------------------------------
def obtener_unidad_medida(db: Session, id_unidad: int):
    return db.query(model.UnidadMedida).filter(model.UnidadMedida.id == id_unidad).first()

def obtener_unidades_medida(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.UnidadMedida)
    if buscar:
        query = query.filter(
            or_(
                model.UnidadMedida.nombre.ilike(f"%{buscar}%"),
                model.UnidadMedida.abreviatura.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_unidad_medida(db: Session, esquema: schemas.UnidadMedidaCreate):
    db_obj = model.UnidadMedida(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_unidad_medida(db: Session, id_unidad: int, esquema: schemas.UnidadMedidaUpdate):
    db_obj = obtener_unidad_medida(db, id_unidad)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_unidad_medida(db: Session, id_unidad: int):
    db_obj = obtener_unidad_medida(db, id_unidad)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# TipoGasto
# ------------------------------------------------------------
def obtener_tipo_gasto(db: Session, id_gasto: int):
    return db.query(model.TipoGasto).filter(model.TipoGasto.id == id_gasto).first()

def obtener_tipos_gasto(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.TipoGasto)
    if buscar:
        query = query.filter(model.TipoGasto.nombre.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()

def crear_tipo_gasto(db: Session, esquema: schemas.TipoGastoCreate):
    db_obj = model.TipoGasto(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_tipo_gasto(db: Session, id_gasto: int, esquema: schemas.TipoGastoUpdate):
    db_obj = obtener_tipo_gasto(db, id_gasto)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_tipo_gasto(db: Session, id_gasto: int):
    db_obj = obtener_tipo_gasto(db, id_gasto)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Ubicacion
# ------------------------------------------------------------
def obtener_ubicacion(db: Session, id_ubicacion: int):
    return db.query(model.Ubicacion).filter(model.Ubicacion.id == id_ubicacion).first()

def obtener_ubicaciones(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Ubicacion)
    if buscar:
        query = query.filter(
            or_(
                model.Ubicacion.nombre.ilike(f"%{buscar}%"),
                model.Ubicacion.descripcion.ilike(f"%{buscar}%"),
                model.Ubicacion.tipo.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_ubicacion(db: Session, esquema: schemas.UbicacionCreate):
    db_obj = model.Ubicacion(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_ubicacion(db: Session, id_ubicacion: int, esquema: schemas.UbicacionUpdate):
    db_obj = obtener_ubicacion(db, id_ubicacion)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_ubicacion(db: Session, id_ubicacion: int):
    db_obj = obtener_ubicacion(db, id_ubicacion)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Area
# ------------------------------------------------------------
def obtener_area(db: Session, id_area: int):
    return db.query(model.Area).filter(model.Area.id == id_area).first()

def obtener_areas(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Area)
    if buscar:
        query = query.filter(model.Area.nombre.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()

def crear_area(db: Session, esquema: schemas.AreaCreate):
    db_obj = model.Area(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_area(db: Session, id_area: int, esquema: schemas.AreaUpdate):
    db_obj = obtener_area(db, id_area)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_area(db: Session, id_area: int):
    db_obj = obtener_area(db, id_area)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Cargo
# ------------------------------------------------------------
def obtener_cargo(db: Session, id_cargo: int):
    return db.query(model.Cargo).filter(model.Cargo.id == id_cargo).first()

def obtener_cargos(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Cargo)
    if buscar:
        query = query.filter(model.Cargo.nombre.ilike(f"%{buscar}%"))
    return query.offset(salto).limit(limite).all()

def crear_cargo(db: Session, esquema: schemas.CargoCreate):
    db_obj = model.Cargo(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_cargo(db: Session, id_cargo: int, esquema: schemas.CargoUpdate):
    db_obj = obtener_cargo(db, id_cargo)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_cargo(db: Session, id_cargo: int):
    db_obj = obtener_cargo(db, id_cargo)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Moneda
# ------------------------------------------------------------
def obtener_moneda(db: Session, id_moneda: int):
    return db.query(model.Moneda).filter(model.Moneda.id == id_moneda).first()

def obtener_monedas(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Moneda)
    if buscar:
        query = query.filter(
            or_(
                model.Moneda.codigo.ilike(f"%{buscar}%"),
                model.Moneda.nombre.ilike(f"%{buscar}%"),
                model.Moneda.simbolo.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_moneda(db: Session, esquema: schemas.MonedaCreate):
    db_obj = model.Moneda(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_moneda(db: Session, id_moneda: int, esquema: schemas.MonedaUpdate):
    db_obj = obtener_moneda(db, id_moneda)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_moneda(db: Session, id_moneda: int):
    db_obj = obtener_moneda(db, id_moneda)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True

# ------------------------------------------------------------
# Rol
# ------------------------------------------------------------
def obtener_rol(db: Session, id_rol: int):
    return db.query(model.Rol).filter(model.Rol.id == id_rol).first()

def obtener_roles(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    query = db.query(model.Rol)
    if buscar:
        query = query.filter(
            or_(
                model.Rol.nombre.ilike(f"%{buscar}%"),
                model.Rol.descripcion.ilike(f"%{buscar}%")
            )
        )
    return query.offset(salto).limit(limite).all()

def crear_rol(db: Session, esquema: schemas.RolCreate):
    db_obj = model.Rol(**esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def actualizar_rol(db: Session, id_rol: int, esquema: schemas.RolUpdate):
    db_obj = obtener_rol(db, id_rol)
    if not db_obj:
        return None
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def eliminar_rol(db: Session, id_rol: int):
    db_obj = obtener_rol(db, id_rol)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True
