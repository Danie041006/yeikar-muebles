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
    from decimal import Decimal
    costo_viejo = Decimal(str(db_obj.costo_base)) if db_obj.costo_base is not None else None
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    # Recalcular (con cuidado) los productos que usan este insumo: si sube el
    # precio del material, sube el precio del mueble automáticamente, sin inflar.
    if "costo_base" in datos:
        costo_nuevo = Decimal(str(db_obj.costo_base)) if db_obj.costo_base is not None else None
        if costo_viejo is not None and costo_nuevo is not None and costo_viejo != costo_nuevo:
            try:
                from app.modules.productos.cost_service import recalcular_tras_cambio_material
                recalcular_tras_cambio_material(db, id_material, costo_viejo, costo_nuevo)
            except Exception:
                # El recálculo jamás debe romper la actualización del material.
                db.rollback()
    return db_obj

def eliminar_material(db: Session, id_material: int):
    db_obj = obtener_material(db, id_material)
    if not db_obj:
        return False
    db.delete(db_obj)
    db.commit()
    return True


# ------------------------------------------------------------
# Secciones de Producto (Receta Estructurada)
# ------------------------------------------------------------
def crear_seccion_producto(db: Session, esquema: schemas.SeccionProductoCreate):
    from app.modules.productos import model
    seccion = model.SeccionProducto(
        producto_id=esquema.producto_id,
        nombre=esquema.nombre.upper().strip(),
        orden=esquema.orden
    )
    db.add(seccion)
    db.commit()
    db.refresh(seccion)

    politica = model.PoliticaSeccion(
        seccion_id=seccion.id,
        mano_obra_base=esquema.mano_obra_base if esquema.mano_obra_base is not None else 0.0,
        pct_liquidacion_mo=esquema.pct_liquidacion_mo if esquema.pct_liquidacion_mo is not None else 5.0,
        pct_gastos_seccion=esquema.pct_gastos_seccion if esquema.pct_gastos_seccion is not None else 10.0,
        costo_fabricacion=esquema.costo_fabricacion,
        pct_trabajadores=esquema.pct_trabajadores,
        pct_negocio=esquema.pct_negocio,
    )
    db.add(politica)
    db.commit()
    db.refresh(seccion)
    return seccion


def eliminar_seccion_producto(db: Session, seccion_id: int):
    from app.modules.productos import model
    seccion = db.query(model.SeccionProducto).filter(model.SeccionProducto.id == seccion_id).first()
    if not seccion:
        return False
    db.delete(seccion)
    db.commit()
    return True
