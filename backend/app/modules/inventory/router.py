from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from decimal import Decimal

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.inventory import service, schemas

router = APIRouter(prefix="/inventario", tags=["Inventario"], dependencies=[Depends(require_module('inventario'))])


@router.get("/", response_model=List[schemas.InventarioResponse])
def listar_inventario(
    material_id: Optional[int] = Query(None),
    ubicacion_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Lista el stock actual de materiales (opcionalmente filtrado)."""
    return service.obtener_inventario(db, material_id, ubicacion_id)


@router.get("/alertas", response_model=List[schemas.AlertaStockResponse])
def alertas_stock(
    umbral: float = Query(5.0, description="Stock mínimo para considerar alerta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Devuelve materiales con stock <= umbral."""
    return service.obtener_alertas_stock(db, umbral=Decimal(str(umbral)))


@router.post("/movimiento", response_model=schemas.MovimientoResponse, status_code=201)
def crear_movimiento(
    movimiento: schemas.MovimientoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Registra un movimiento de inventario (entrada, salida, ajuste, daño, devolución)
    y actualiza el stock automáticamente.
    """
    try:
        mov = service.registrar_movimiento(db, movimiento, usuario=current_user)
        db.commit()
        db.refresh(mov)
        return mov
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="El movimiento de inventario entró en conflicto con otra operación simultánea")


@router.get("/movimientos/material/{material_id}", response_model=List[schemas.MovimientoResponse])
def movimientos_por_material(
    material_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Obtiene el historial de movimientos (kardex) de un material específico."""
    movimientos = service.obtener_movimientos_por_material(db, material_id, limit)
    return movimientos


@router.get("/material/{material_id}/costo-unitario-real")
def costo_unitario_real_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Costo real por unidad de un material: compra + "la pasada" (llevada/flete)
    prorrateada sobre las unidades de la última entrada. Útil para vender
    insumos sueltos sabiendo cuánto costó realmente cada unidad.
    """
    try:
        return service.costo_unitario_real_material(db, material_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================================================================
# Inventario de PRODUCTOS (terminados / de reventa)
# =========================================================================

@router.get("/productos", response_model=List[schemas.ProductoInventarioResponse])
def listar_inventario_productos(
    producto_id: Optional[int] = Query(None),
    ubicacion_id: Optional[int] = Query(None),
    solo_reventa: bool = Query(False, description="Solo productos de reventa (colchones, neveras, etc.)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Lista el stock actual de productos (terminados / de reventa)."""
    return service.obtener_inventario_productos(db, producto_id, ubicacion_id, solo_reventa=solo_reventa)


@router.get("/productos/alertas", response_model=List[schemas.AlertaStockProductoResponse])
def alertas_stock_productos(
    umbral: float = Query(8.0, description="Stock mínimo de respaldo si el producto no tiene configurado"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Devuelve productos con stock <= su stock_minimo."""
    return service.obtener_alertas_stock_productos(db, umbral=Decimal(str(umbral)))


@router.post("/producto/movimiento", response_model=schemas.MovimientoProductoResponse, status_code=201)
def crear_movimiento_producto(
    movimiento: schemas.MovimientoProductoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Registra un movimiento de inventario de producto (entrada con costo unitario
    opcional, salida, ajuste, daño, devolución) y actualiza stock + costo promedio.
    """
    try:
        mov = service.registrar_movimiento_producto(db, movimiento, usuario=current_user)
        db.commit()
        db.refresh(mov)
        return mov
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="El movimiento de inventario entró en conflicto con otra operación simultánea")


@router.get("/movimientos/producto/{producto_id}", response_model=List[schemas.MovimientoProductoResponse])
def movimientos_producto(
    producto_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Historial (kardex) de movimientos de un producto."""
    return service.obtener_movimientos_producto(db, producto_id, limit)


# =========================================================================
# Sobrantes de láminas (retazos de materiales laminares)
# =========================================================================

@router.get("/sobrantes", response_model=List[schemas.SobranteLaminaResponse])
def listar_sobrantes(
    material_id: Optional[int] = Query(None),
    estado: Optional[str] = Query(None, description="DISPONIBLE | CONSUMIDO | DESECHADO"),
    ubicacion_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Lista los retazos (sobrantes) de materiales laminares."""
    return service.obtener_sobrantes(db, material_id, estado, ubicacion_id)


@router.post("/sobrantes", response_model=schemas.SobranteLaminaResponse, status_code=201)
def crear_sobrante(
    datos: schemas.SobranteLaminaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Registra a mano un retazo (ej. pedazos que ya existen en el taller)."""
    try:
        return service.crear_sobrante(db, datos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sobrantes/{sobrante_id}", response_model=schemas.SobranteLaminaResponse)
def actualizar_sobrante(
    sobrante_id: int,
    datos: schemas.SobranteLaminaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Edita medidas/estado de un sobrante (ej. marcarlo DESECHADO)."""
    try:
        s = service.actualizar_sobrante(db, sobrante_id, datos)
        if not s:
            raise HTTPException(status_code=404, detail="El sobrante no existe.")
        return s
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sobrantes/{sobrante_id}", status_code=204)
def eliminar_sobrante(
    sobrante_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    ok = service.eliminar_sobrante(db, sobrante_id)
    if not ok:
        raise HTTPException(status_code=404, detail="El sobrante no existe.")
    return None


# =========================================================================
# Categorías de inventario (desglose en la UI)
# =========================================================================

@router.get("/categorias", response_model=List[dict])
def listar_categorias(
    tipo: Optional[str] = Query(None, description="MATERIAL | PRODUCTO"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from app.modules.catalogos.model import CategoriaInventario
    query = db.query(CategoriaInventario).filter(CategoriaInventario.activo == True)
    if tipo:
        query = query.filter(CategoriaInventario.tipo == tipo.upper())
    cats = query.order_by(CategoriaInventario.orden, CategoriaInventario.nombre).all()
    return [
        {"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "orden": c.orden}
        for c in cats
    ]


@router.post("/categorias", status_code=201)
def crear_categoria(
    datos: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from app.modules.catalogos.model import CategoriaInventario
    nombre = (datos.get("nombre") or "").strip()
    tipo = (datos.get("tipo") or "MATERIAL").upper()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio.")
    if tipo not in ("MATERIAL", "PRODUCTO"):
        raise HTTPException(status_code=400, detail="El tipo debe ser MATERIAL o PRODUCTO.")
    existe = db.query(CategoriaInventario).filter(
        CategoriaInventario.nombre == nombre, CategoriaInventario.tipo == tipo
    ).first()
    if existe:
        raise HTTPException(status_code=409, detail="Ya existe esa categoría.")
    cat = CategoriaInventario(
        nombre=nombre,
        tipo=tipo,
        orden=int(datos.get("orden") or 0),
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "nombre": cat.nombre, "tipo": cat.tipo, "orden": cat.orden}