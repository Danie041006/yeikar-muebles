from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.modules.productos import model, schemas

# Moneda base del ERP: COP (id=1). Todos los costos internos del motor de
# costos, cotizaciones y ventas se calculan en esta moneda.
MONEDA_BASE_ID = 1


def convertir_a_moneda_base(
    db: Session,
    moneda_id: Optional[int],
    monto: Optional[float],
) -> Optional[float]:
    """Convierte un precio de referencia a la moneda base (COP) con la tasa vigente.

    Los precios de referencia (precio_costo_base / precio_venta_base) se guardan
    en la moneda declarada del producto (`moneda_id`); si no hay moneda explícita
    o ya es la base, el monto pasa tal cual. `monto=None` devuelve None para que
    el caller aplique su propio fallback.

    Filosofía de tasas: se ingresan MANUALMENTE en cada operación (cotización,
    pago, facturación) porque cambian a diario; NO se guardan en una tabla.
    Si no existe una tasa registrada para la moneda, devuelve None (sin
    conversión): el caller decide su fallback en vez de convertir mal un
    precio financiero en silencio (leería "US$45" como "45 COP").
    """
    if monto is None:
        return None
    from decimal import Decimal
    monto_dec = Decimal(str(monto))
    if not moneda_id or moneda_id == MONEDA_BASE_ID:
        return float(monto_dec)
    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop, obtener_ultima_tasa
    from app.modules.tasas_cambio.model import TasaCambio
    if not obtener_ultima_tasa(db, moneda_id, MONEDA_BASE_ID):
        # ¿Tasa invertida (1 COP = X moneda)? Se acepta y se invierte.
        inversa = db.query(TasaCambio).filter(
            TasaCambio.moneda_origen_id == MONEDA_BASE_ID,
            TasaCambio.moneda_destino_id == moneda_id,
        ).order_by(TasaCambio.fecha.desc()).first()
        if not inversa or not inversa.valor or float(inversa.valor) <= 0:
            return None
        tasa = Decimal("1") / Decimal(str(inversa.valor))
    else:
        tasa = obtener_tasa_moneda_a_cop(db, moneda_id)
    return float(monto_dec * tasa)

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
