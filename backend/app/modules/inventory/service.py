from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from datetime import datetime
from typing import Optional, List



from app.modules.inventory import model, schemas
from app.modules.productos.model import Material, Producto
from app.modules.catalogos.model import Ubicacion


def obtener_inventario(
    db: Session,
    material_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None ) -> List[schemas.InventarioResponse]:
    """
    Retorna el stock actual de materiales por ubicación.
    Opcionalmente filtra por material y/o ubicación.
    """
    query = db.query(model.Inventario).options(
        joinedload(model.Inventario.material),
        joinedload(model.Inventario.ubicacion)
    )
    if material_id:
        query = query.filter(model.Inventario.material_id == material_id)
    if ubicacion_id:
        query = query.filter(model.Inventario.ubicacion_id == ubicacion_id)

    resultados = query.all()
    return [
        schemas.InventarioResponse(
            id=inv.id,
            material_id=inv.material_id,
            material_nombre=inv.material.nombre,
            ubicacion_id=inv.ubicacion_id,
            ubicacion_nombre=inv.ubicacion.nombre,
            cantidad=inv.cantidad,
            created_at=inv.created_at,
            updated_at=inv.updated_at
        )
        for inv in resultados
    ]


def obtener_stock_material(db: Session, material_id: int, ubicacion_id: int) -> Decimal:
    """Devuelve la cantidad disponible de un material en una ubicación específica."""
    inv = db.query(model.Inventario).filter(
        model.Inventario.material_id == material_id,
        model.Inventario.ubicacion_id == ubicacion_id
    ).first()
    return inv.cantidad if inv else Decimal(0)



def registrar_movimiento(db: Session, movimiento: schemas.MovimientoCreate) -> model.MovimientoInventario:
    """
    Registra un movimiento de inventario (entrada, salida, ajuste, etc.)
    y actualiza la cantidad en la tabla inventario.
    """
    if movimiento.cantidad <= 0:
        raise ValueError("La cantidad debe ser positiva")

    # Obtener o crear el registro de inventario para ese material y ubicación.
    # FOR UPDATE bloquea la fila para que dos SALIDAS concurrentes no lean el
    # mismo stock y descuenten dos veces (race condition).
    inventario = db.query(model.Inventario).filter(
        model.Inventario.material_id == movimiento.material_id,
        model.Inventario.ubicacion_id == movimiento.ubicacion_id
    ).with_for_update().first()

    if not inventario:
        try:
            # Savepoint: si dos requests crean la fila a la vez, el único
            # constraint (uq_inventario_material_ubicacion) permite capturar el
            # conflicto y re-leer la fila del ganador en vez de lanzar 500.
            with db.begin_nested():
                inventario = model.Inventario(
                    material_id=movimiento.material_id,
                    ubicacion_id=movimiento.ubicacion_id,
                    cantidad=Decimal(0)
                )
                db.add(inventario)
                db.flush()
        except IntegrityError:
            inventario = db.query(model.Inventario).filter(
                model.Inventario.material_id == movimiento.material_id,
                model.Inventario.ubicacion_id == movimiento.ubicacion_id
            ).with_for_update().first()
            if not inventario:
                raise

    # Aplicar cambio según tipo de movimiento
    if movimiento.tipo == "ENTRADA":
        inventario.cantidad += movimiento.cantidad
    elif movimiento.tipo in ("SALIDA", "DAÑO"):
        if inventario.cantidad < movimiento.cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {inventario.cantidad}")
        inventario.cantidad -= movimiento.cantidad
    elif movimiento.tipo == "AJUSTE":
        inventario.cantidad = movimiento.cantidad
    elif movimiento.tipo == "DEVOLUCION":
        inventario.cantidad += movimiento.cantidad
    else:
        raise ValueError(f"Tipo de movimiento inválido: {movimiento.tipo}")

    # Crear el registro de movimiento
    db_mov = model.MovimientoInventario(
        material_id=movimiento.material_id,
        ubicacion_id=movimiento.ubicacion_id,
        tipo=movimiento.tipo,
        cantidad=movimiento.cantidad,
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=datetime.utcnow()
    )
    db.add(db_mov)
    # IMPORTANTE: flush, NO commit. Un commit aquí rompería la transacción del
    # llamador (compra/producción): si algo falla después, la compra, el detalle y
    # el movimiento ya quedarían persistidos a medias. El caller commitea al final.
    db.flush()
    db.refresh(db_mov)
    return db_mov


def obtener_movimientos_por_material(
    db: Session,
    material_id: int,
    limit: int = 100
) -> List[model.MovimientoInventario]:
    """
    Retorna el historial de movimientos (kardex) de un material.
    """
    return db.query(model.MovimientoInventario).filter(
        model.MovimientoInventario.material_id == material_id
    ).order_by(model.MovimientoInventario.fecha.desc()).limit(limit).all()


def obtener_alertas_stock(
    db: Session,
    umbral: Decimal = Decimal(8)   # umbral por defecto si el material no tiene stock_minimo
) -> List[schemas.AlertaStockResponse]:
    """
    Retorna todos los materiales cuyo stock actual es menor o igual a su
    stock_minimo configurado (columna material.stock_minimo, default 8).
    Los materiales sin fila de inventario con cantidad 0 también alertan.
    """
    # Todos los materiales activos + su stock actual agregado
    resultados = db.query(model.Inventario).options(
        joinedload(model.Inventario.material),
        joinedload(model.Inventario.ubicacion)
    ).all()

    alertas = []
    por_material = {}
    for inv in resultados:
        key = (inv.material_id, inv.ubicacion_id)
        por_material[key] = inv

    # Materiales que SÍ tienen fila de inventario
    for (mat_id, ubi_id), inv in por_material.items():
        minimo = inv.material.stock_minimo if inv.material.stock_minimo is not None else umbral
        if inv.cantidad <= minimo:
            alertas.append(schemas.AlertaStockResponse(
                material_id=inv.material_id,
                material_nombre=inv.material.nombre,
                stock_actual=inv.cantidad,
                stock_minimo=minimo,
                ubicacion_id=inv.ubicacion_id,
                ubicacion_nombre=inv.ubicacion.nombre,
            ))

    # Materiales activos SIN ninguna fila de inventario (stock = 0) también alertan
    mats_con_stock = {mat_id for (mat_id, _) in por_material}
    materiales_sin_fila = db.query(Material).options(
        joinedload(Material.unidad_medida)
    ).filter(Material.activo == True).all()
    for mat in materiales_sin_fila:
        if mat.id in mats_con_stock:
            continue
        minimo = mat.stock_minimo if mat.stock_minimo is not None else umbral
        if Decimal("0") <= minimo:
            alertas.append(schemas.AlertaStockResponse(
                material_id=mat.id,
                material_nombre=mat.nombre,
                stock_actual=Decimal("0"),
                stock_minimo=minimo,
                ubicacion_id=0,
                ubicacion_nombre="Sin ubicación",
            ))

    return alertas


# =========================================================================
# Inventario de PRODUCTOS (terminados / de reventa)
# =========================================================================

def obtener_inventario_productos(
    db: Session,
    producto_id: Optional[int] = None,
    ubicacion_id: Optional[int] = None,
    solo_reventa: bool = False,
) -> List[schemas.ProductoInventarioResponse]:
    """Stock actual de productos (terminados/de reventa) por ubicación.

    Con solo_reventa=True solo devuelve productos marcados es_reventa
    (los que la empresa compra para revender: colchones, neveras, etc.).
    """
    query = db.query(model.ProductoInventario).options(
        joinedload(model.ProductoInventario.producto),
        joinedload(model.ProductoInventario.ubicacion),
    )
    if solo_reventa:
        query = query.join(Producto, model.ProductoInventario.producto_id == Producto.id).filter(Producto.es_reventa == True)
    if producto_id:
        query = query.filter(model.ProductoInventario.producto_id == producto_id)
    if ubicacion_id:
        query = query.filter(model.ProductoInventario.ubicacion_id == ubicacion_id)

    resultados = query.all()
    return [
        schemas.ProductoInventarioResponse(
            id=inv.id,
            producto_id=inv.producto_id,
            producto_nombre=inv.producto.nombre if inv.producto else None,
            producto_codigo=inv.producto.codigo if inv.producto else None,
            es_reventa=inv.producto.es_reventa if inv.producto else None,
            ubicacion_id=inv.ubicacion_id,
            ubicacion_nombre=inv.ubicacion.nombre if inv.ubicacion else None,
            cantidad=inv.cantidad,
            costo_promedio=inv.costo_promedio,
            stock_minimo=inv.producto.stock_minimo if inv.producto else None,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
        )
        for inv in resultados
    ]


def registrar_movimiento_producto(
    db: Session,
    movimiento: schemas.MovimientoProductoCreate,
) -> model.MovimientoProductoInventario:
    """
    Registra un movimiento de inventario de producto (entrada, salida, ajuste...)
    y actualiza la cantidad + costo en producto_inventario.

    Si el movimiento es ENTRADA y trae costo_unitario, el costo_promedio del
    producto se actualiza AL INSTANTE con el último precio (no promedio).
    """
    if movimiento.cantidad <= 0:
        raise ValueError("La cantidad debe ser positiva")

    producto = db.query(Producto).filter(Producto.id == movimiento.producto_id).first()
    if not producto:
        raise ValueError(f"El producto con id {movimiento.producto_id} no existe.")

    inv = db.query(model.ProductoInventario).filter(
        model.ProductoInventario.producto_id == movimiento.producto_id,
        model.ProductoInventario.ubicacion_id == movimiento.ubicacion_id,
    ).with_for_update().first()

    if not inv:
        try:
            with db.begin_nested():
                inv = model.ProductoInventario(
                    producto_id=movimiento.producto_id,
                    ubicacion_id=movimiento.ubicacion_id,
                    cantidad=Decimal(0),
                    costo_promedio=None,
                )
                db.add(inv)
                db.flush()
        except IntegrityError:
            inv = db.query(model.ProductoInventario).filter(
                model.ProductoInventario.producto_id == movimiento.producto_id,
                model.ProductoInventario.ubicacion_id == movimiento.ubicacion_id,
            ).with_for_update().first()
            if not inv:
                raise

    # Aplicar cambio según tipo de movimiento
    if movimiento.tipo == "ENTRADA":
        inv.cantidad += movimiento.cantidad
        # El costo se actualiza AL INSTANTE con el último precio de entrada.
        # No se usa promedio ponderado: si el insumo sube, el nuevo precio
        # rige desde ya para nuevas cotizaciones/pedidos.
        if movimiento.costo_unitario is not None:
            inv.costo_promedio = Decimal(str(movimiento.costo_unitario))
    elif movimiento.tipo in ("SALIDA", "DAÑO"):
        if inv.cantidad < movimiento.cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {inv.cantidad}")
        inv.cantidad -= movimiento.cantidad
    elif movimiento.tipo == "AJUSTE":
        inv.cantidad = movimiento.cantidad
    elif movimiento.tipo == "DEVOLUCION":
        inv.cantidad += movimiento.cantidad
    else:
        raise ValueError(f"Tipo de movimiento inválido: {movimiento.tipo}")

    db_mov = model.MovimientoProductoInventario(
        producto_id=movimiento.producto_id,
        ubicacion_id=movimiento.ubicacion_id,
        tipo=movimiento.tipo,
        cantidad=movimiento.cantidad,
        costo_unitario=movimiento.costo_unitario,
        referencia_tipo=movimiento.referencia_tipo,
        referencia_id=movimiento.referencia_id,
        observaciones=movimiento.observaciones,
        fecha=datetime.utcnow(),
    )
    db.add(db_mov)
    db.flush()
    db.refresh(db_mov)
    return db_mov


def obtener_movimientos_producto(
    db: Session,
    producto_id: int,
    limit: int = 100,
) -> List[model.MovimientoProductoInventario]:
    """Historial (kardex) de movimientos de un producto."""
    return db.query(model.MovimientoProductoInventario).filter(
        model.MovimientoProductoInventario.producto_id == producto_id
    ).order_by(model.MovimientoProductoInventario.fecha.desc()).limit(limit).all()


def obtener_alertas_stock_productos(
    db: Session,
    umbral: Decimal = Decimal(8),
) -> List[schemas.AlertaStockProductoResponse]:
    """Productos de REVENTA cuyo stock actual es menor o igual a su stock_minimo."""
    resultados = db.query(model.ProductoInventario).join(
        Producto, model.ProductoInventario.producto_id == Producto.id
    ).options(
        joinedload(model.ProductoInventario.producto),
        joinedload(model.ProductoInventario.ubicacion),
    ).filter(Producto.es_reventa == True).all()

    alertas = []
    por_producto = {}
    for inv in resultados:
        por_producto[(inv.producto_id, inv.ubicacion_id)] = inv

    for (prod_id, ubi_id), inv in por_producto.items():
        minimo = inv.producto.stock_minimo if inv.producto and inv.producto.stock_minimo is not None else umbral
        if inv.cantidad <= minimo:
            alertas.append(schemas.AlertaStockProductoResponse(
                producto_id=inv.producto_id,
                producto_nombre=inv.producto.nombre if inv.producto else str(prod_id),
                stock_actual=inv.cantidad,
                stock_minimo=minimo,
                ubicacion_id=inv.ubicacion_id,
                ubicacion_nombre=inv.ubicacion.nombre if inv.ubicacion else "",
            ))

    return alertas