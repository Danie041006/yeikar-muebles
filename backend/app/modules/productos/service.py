from typing import Optional

from decimal import Decimal

from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, or_
from app.modules.productos import model, schemas

# Moneda base del ERP: COP (id=1). Todos los costos internos del motor de
# costos, cotizaciones y ventas se calculan en esta moneda.
MONEDA_BASE_ID = 1


def _tasa_moneda_a_base(db: Session, moneda_id: int) -> Optional[Decimal]:
    """Tasa vigente para convertir 1 unidad de `moneda_id` a COP.

    Acepta la tasa directa (moneda → COP) o la invertida (COP → moneda).
    Devuelve None si no hay ninguna tasa registrada: el caller decide su
    fallback en vez de convertir mal un precio financiero en silencio
    (leería "US$45" como "45 COP").
    """
    from app.modules.tasas_cambio.service import obtener_tasa_moneda_a_cop, obtener_ultima_tasa
    from app.modules.tasas_cambio.model import TasaCambio
    if obtener_ultima_tasa(db, moneda_id, MONEDA_BASE_ID):
        return Decimal(str(obtener_tasa_moneda_a_cop(db, moneda_id)))
    inversa = db.query(TasaCambio).filter(
        TasaCambio.moneda_origen_id == MONEDA_BASE_ID,
        TasaCambio.moneda_destino_id == moneda_id,
    ).order_by(TasaCambio.fecha.desc()).first()
    if not inversa or not inversa.valor or float(inversa.valor) <= 0:
        return None
    return Decimal("1") / Decimal(str(inversa.valor))


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
    if not moneda_id or moneda_id == MONEDA_BASE_ID:
        return float(monto)
    tasa = _tasa_moneda_a_base(db, moneda_id)
    if tasa is None:
        return None
    return float(Decimal(str(monto)) * tasa)


def convertir_desde_moneda_base(
    db: Session,
    moneda_id: Optional[int],
    monto: Optional[float],
) -> Optional[float]:
    """Convierte un monto en moneda base (COP) a la moneda declarada del
    producto (inverso de `convertir_a_moneda_base`). Mismas reglas: tasa
    manual vigente; None si no hay tasa con la cual convertir."""
    if monto is None:
        return None
    if not moneda_id or moneda_id == MONEDA_BASE_ID:
        return float(monto)
    tasa = _tasa_moneda_a_base(db, moneda_id)
    if tasa is None or tasa <= 0:
        return None
    return float(Decimal(str(monto)) / tasa)

# ------------------------------------------------------------
# Producto
# ------------------------------------------------------------
def obtener_producto(db: Session, id_producto: int):
    return db.query(model.Producto).filter(model.Producto.id == id_producto).first()

def obtener_productos(
    db: Session,
    salto: int = 0,
    limite: int = 100,
    buscar: str = None,
    es_reventa: bool = None,
    es_exhibicion: bool = None,
):
    query = db.query(model.Producto).options(
        # Precarga en 2 queries: evita que la serialización de cada producto
        # dispare 2 queries lazy más (N+1 sobre tipo_producto y moneda).
        selectinload(model.Producto.tipo_producto),
        selectinload(model.Producto.moneda),
    )
    if buscar:
        query = query.filter(
            or_(
                model.Producto.nombre.ilike(f"%{buscar}%"),
                model.Producto.codigo.ilike(f"%{buscar}%"),
                model.Producto.descripcion.ilike(f"%{buscar}%")
            )
        )
    if es_reventa is not None:
        query = query.filter(model.Producto.es_reventa == es_reventa)
    if es_exhibicion is not None:
        query = query.filter(model.Producto.es_exhibicion == es_exhibicion)
    # NUEVOS PRIMERO: con el catálogo pasado de 1000 ítems, el orden por id
    # ASC truncaba la página en los más viejos y los recién creados (piezas
    # de exhibición, productos nuevos) nunca aparecían en ningún listado.
    return query.order_by(model.Producto.id.desc()).offset(salto).limit(limite).all()

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
    return db.query(model.Material).options(
        joinedload(model.Material.unidad_medida),
        joinedload(model.Material.categoria_inventario),
    ).filter(model.Material.id == id_material).first()

def obtener_materiales(db: Session, salto: int = 0, limite: int = 100, buscar: str = None):
    # selectinload: sin esto, serializar 1000+ materiales dispara una query por
    # material (N+1) por unidad_medida/categoria_inventario → el inventario de
    # insumos tardaba segundos en cargar.
    query = db.query(model.Material).options(
        joinedload(model.Material.unidad_medida),
        joinedload(model.Material.categoria_inventario),
    )
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


# =========================================================================
# Duplicados del catálogo y fusión de materiales
# =========================================================================

# Tablas hijas con columna material_id que deben re-puntarse al fusionar.
# (elemento_seccion usa material_id_normalizado y se maneja aparte.)
_TABLAS_HIJAS_MATERIAL = [
    "movimiento_inventario",
    "producto_material",
    "consumo_material",
    "produccion_crudo_consumo",
    "detalle_compra",
    "cotizacion_detalle_material",
    "detalle_cotizacion",
    "detalle_pedido",
    "detalle_venta",
    "detalle_factura",
    "sobrante_lamina",
]


def _referencias_material(db: Session, id_material: int) -> dict:
    """Conteo de referencias (para mostrar qué se va a mover en una fusión)."""
    from sqlalchemy import text
    refs = {}
    for tabla in _TABLAS_HIJAS_MATERIAL:
        n = db.execute(
            text(f"SELECT COUNT(*) FROM {tabla} WHERE material_id = :m"), {"m": id_material}
        ).scalar()
        if n:
            refs[tabla] = int(n)
    n_elem = db.execute(
        text("SELECT COUNT(*) FROM elemento_seccion WHERE material_id_normalizado = :m"),
        {"m": id_material},
    ).scalar()
    if n_elem:
        refs["elemento_seccion"] = int(n_elem)
    n_sin = db.execute(
        text("SELECT COUNT(*) FROM material_sinonimo WHERE material_id = :m"), {"m": id_material}
    ).scalar()
    if n_sin:
        refs["material_sinonimo"] = int(n_sin)
    return refs


def detectar_duplicados(db: Session) -> list[dict]:
    """Materiales cuyo nombre (normalizado upper/trim) aparece más de una vez,
    con su stock y referencias, para decidir cuál sobrevive en una fusión."""
    from sqlalchemy import text
    grupos = db.execute(text(
        "SELECT upper(trim(nombre)) AS norma, COUNT(*) AS n "
        "FROM material GROUP BY upper(trim(nombre)) HAVING COUNT(*) > 1 "
        "ORDER BY n DESC, norma"
    )).all()
    stock_por_material = dict(db.execute(text(
        "SELECT material_id, SUM(cantidad) FROM inventario GROUP BY material_id"
    )).all())
    resultado = []
    for norma, n in grupos:
        mats = db.query(model.Material).filter(
            func.upper(func.trim(model.Material.nombre)) == norma
        ).order_by(model.Material.id).all()
        items = []
        for m in mats:
            items.append({
                "id": m.id,
                "nombre": m.nombre,
                "costo_base": float(m.costo_base or 0),
                "activo": bool(m.activo),
                "largo_cm": float(m.largo_cm) if m.largo_cm is not None else None,
                "ancho_cm": float(m.ancho_cm) if m.ancho_cm is not None else None,
                "stock": float(stock_por_material.get(m.id) or 0),
                "referencias": _referencias_material(db, m.id),
            })
        resultado.append({"nombre": norma, "total": n, "items": items})
    return resultado


def fusionar_material(
    db: Session,
    origen_id: int,
    destino_id: int,
    costo_base=None,
    usuario=None,
) -> dict:
    """Fusiona el material origen en el destino: mueve stock (sumando por
    ubicación), re-punta todas las FKs, traslada sinónimos y elimina el origen.
    Todo en UNA transacción: si algo falla, no queda nada a medias."""
    from sqlalchemy import text
    from decimal import Decimal

    origen = db.query(model.Material).filter(model.Material.id == origen_id).with_for_update().first()
    destino = db.query(model.Material).filter(model.Material.id == destino_id).with_for_update().first()
    if not origen or not destino:
        raise ValueError("Alguno de los materiales no existe.")
    if origen.id == destino.id:
        raise ValueError("El origen y el destino son el mismo material.")

    # 1. Completar al destino lo que el origen sabía y él no (dimensiones de
    #    lámina, categoría) y quedarse con el stock mínimo más exigente.
    for campo in ("largo_cm", "ancho_cm", "categoria_inventario_id"):
        if getattr(destino, campo) is None and getattr(origen, campo) is not None:
            setattr(destino, campo, getattr(origen, campo))
    if origen.stock_minimo is not None and (
        destino.stock_minimo is None or origen.stock_minimo > destino.stock_minimo
    ):
        destino.stock_minimo = origen.stock_minimo
    if costo_base is not None:
        destino.costo_base = Decimal(str(costo_base))
    db.flush()

    # 2. Inventario: sumar cantidades por ubicación y eliminar las filas del origen.
    from app.modules.inventory.model import Inventario
    invs = db.query(Inventario).filter(Inventario.material_id == origen.id).all()
    for inv in invs:
        inv_dest = (
            db.query(Inventario)
            .filter(
                Inventario.material_id == destino.id,
                Inventario.ubicacion_id == inv.ubicacion_id,
            )
            .with_for_update()
            .first()
        )
        if inv_dest:
            inv_dest.cantidad = (inv_dest.cantidad or 0) + (inv.cantidad or 0)
            db.delete(inv)
        else:
            inv.material_id = destino.id
    db.flush()

    # 3. Re-puntar el historial y las referencias al destino.
    for tabla in _TABLAS_HIJAS_MATERIAL:
        db.execute(
            text(f"UPDATE {tabla} SET material_id = :d WHERE material_id = :o"),
            {"d": destino.id, "o": origen.id},
        )
    db.execute(
        text("UPDATE elemento_seccion SET material_id_normalizado = :d "
             "WHERE material_id_normalizado = :o"),
        {"d": destino.id, "o": origen.id},
    )

    # 4. Sinónimos: moverlos; si el texto ya existe apuntando a otro material,
    #    se descarta la fila del origen (el sinonimo es unique).
    for sin in db.query(model.MaterialSinonimo).filter(
            model.MaterialSinonimo.material_id == origen.id).all():
        duplicado = db.query(model.MaterialSinonimo).filter(
            model.MaterialSinonimo.sinonimo == sin.sinonimo,
            model.MaterialSinonimo.material_id != origen.id,
        ).first()
        if duplicado:
            db.delete(sin)
        else:
            sin.material_id = destino.id
    db.flush()

    refs = _referencias_material(db, origen.id)
    if refs:
        raise ValueError(
            f"No se pudo fusionar: el material origen aún tiene referencias ({refs}). "
            "Revise las restricciones y reintente."
        )

    nombre_origen = origen.nombre
    db.delete(origen)
    db.commit()

    from app.modules.auditoria.service import record_event
    record_event(
        db, actor=usuario, action="UPDATE", entity_type="material",
        entity_id=destino.id,
        after={"fusion_origen": nombre_origen, "fusion_origen_id": origen_id,
               "destino": destino.nombre},
    )
    return {"origen_eliminado": nombre_origen, "destino": destino.nombre, "destino_id": destino.id}


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
