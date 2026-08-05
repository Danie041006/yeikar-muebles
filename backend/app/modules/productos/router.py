from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.productos import schemas, service
from app.modules.productos import cost_service
from app.modules.productos.model import ProductoMaterial

router = APIRouter(dependencies=[Depends(require_module("productos"))])
material_router = APIRouter(dependencies=[Depends(require_module("materiales"))])

# ------------------------------------------------------------
# Producto
# ------------------------------------------------------------
@router.post("/producto/", response_model=schemas.ProductoResponse, status_code=status.HTTP_201_CREATED)
def crear_producto(
    esquema: schemas.ProductoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_producto(db, esquema)

@router.get("/producto/", response_model=List[schemas.ProductoResponse])
def listar_productos(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre, codigo o descripcion"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_productos(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/producto/{id_producto}", response_model=schemas.ProductoResponse)
def ver_producto(
    id_producto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_producto(db, id_producto)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db_obj

@router.put("/producto/{id_producto}", response_model=schemas.ProductoResponse)
def actualizar_producto(
    id_producto: int,
    esquema: schemas.ProductoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_producto(db, id_producto, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db_obj

@router.delete("/producto/{id_producto}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_producto(
    id_producto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_producto(db, id_producto)
    if not exito:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return None

# ------------------------------------------------------------
# Material
# ------------------------------------------------------------
@material_router.post("/", response_model=schemas.MaterialResponse, status_code=status.HTTP_201_CREATED)
def crear_material(
    esquema: schemas.MaterialCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_material(db, esquema)

@material_router.get("/", response_model=List[schemas.MaterialResponse])
def listar_materiales(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_materiales(db, salto=salto, limite=limite, buscar=buscar)

@material_router.get("/{id_material}", response_model=schemas.MaterialResponse)
def ver_material(
    id_material: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_material(db, id_material)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    return db_obj

@material_router.put("/{id_material}", response_model=schemas.MaterialResponse)
def actualizar_material(
    id_material: int,
    esquema: schemas.MaterialUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_material(db, id_material, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    return db_obj

@material_router.delete("/{id_material}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_material(
    id_material: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    try:
        exito = service.eliminar_material(db, id_material)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar el material: tiene recetas, inventario, movimientos o compras asociados.",
        )
    if not exito:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    return None


# ------------------------------------------------------------
# Costeo paramétrico
# ------------------------------------------------------------

@router.get("/producto/{producto_id}/calcular-precio", response_model=dict, tags=["costeo"])
@router.post("/producto/{producto_id}/calcular-precio", response_model=dict, tags=["costeo"])
def calcular_precio_personalizado(
    producto_id: int,
    ancho: float = Query(..., gt=0, description="Ancho nuevo en metros"),
    largo: float = Query(..., gt=0, description="Largo nuevo en metros"),
    ganancia: float = Query(40.0, ge=0, description="Porcentaje de ganancia (ej. 40 = 40%)"),
    iva: float = Query(0.0, ge=0, description="Porcentaje de IVA (ej. 19 = 19%)"),
    pct_mano_obra: float = Query(15.0, ge=0, description="Porcentaje de mano de obra sobre materiales"),
    pct_gastos: float = Query(10.0, ge=0, description="Porcentaje de gastos indirectos sobre materiales"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Calcula automáticamente el costo y precio de venta de un producto
    con dimensiones personalizadas. Usa las reglas de escala definidas
    en la tabla `producto_material`.
    """
    try:
        resultado = cost_service.calcular_costo_producto(
            db=db,
            producto_id=producto_id,
            nuevo_ancho=Decimal(str(ancho)),
            nuevo_largo=Decimal(str(largo)),
            ganancia_porcentaje=Decimal(str(ganancia)),
            iva_porcentaje=Decimal(str(iva)),
            pct_mano_obra=Decimal(str(pct_mano_obra)),
            pct_gastos=Decimal(str(pct_gastos)),
        )
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------
# CRUD de receta (producto_material)
# ------------------------------------------------------------

@router.get("/producto/{producto_id}/receta", response_model=List[schemas.ProductoMaterialResponse], tags=["costeo"])
def ver_receta_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Lista todos los materiales y reglas de escala de un producto."""
    producto = service.obtener_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db.query(ProductoMaterial).filter(ProductoMaterial.producto_id == producto_id).all()


@router.post("/producto/{producto_id}/receta", response_model=schemas.ProductoMaterialResponse, status_code=status.HTTP_201_CREATED, tags=["costeo"])
def agregar_material_receta(
    producto_id: int,
    esquema: schemas.ProductoMaterialCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Agrega un material con su regla de escala a la receta del producto."""
    producto = service.obtener_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    db_obj = ProductoMaterial(producto_id=producto_id, **esquema.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/receta/{receta_id}", response_model=schemas.ProductoMaterialResponse, tags=["costeo"])
def actualizar_material_receta(
    receta_id: int,
    esquema: schemas.ProductoMaterialUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Actualiza una fila de la receta (permite cambiar tipo_escala, cantidades, condiciones, etc.)."""
    db_obj = db.query(ProductoMaterial).filter(ProductoMaterial.id == receta_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Entrada de receta no encontrada")
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_obj, campo, valor)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/receta/{receta_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["costeo"])
def eliminar_material_receta(
    receta_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Elimina un material de la receta del producto."""
    db_obj = db.query(ProductoMaterial).filter(ProductoMaterial.id == receta_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Entrada de receta no encontrada")
    db.delete(db_obj)
    db.commit()
    return None


# ------------------------------------------------------------
# Recetas Jerárquicas por Secciones
# ------------------------------------------------------------
from app.modules.productos import model

@router.get("/producto/{producto_id}/receta-estructurada", response_model=List[schemas.SeccionProductoResponse], tags=["receta-secciones"])
def ver_receta_estructurada(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Retorna el árbol de receta del producto organizado por Secciones (EBANISTERÍA, PINTURA, etc.),
    con sus insumos físicos aislados y sus políticas de mano de obra y porcentajes por área.
    """
    producto = service.obtener_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    secciones = (
        db.query(model.SeccionProducto)
        .filter(model.SeccionProducto.producto_id == producto_id)
        .order_by(model.SeccionProducto.orden)
        .all()
    )
    return secciones


@router.put("/seccion/{seccion_id}/politica", response_model=schemas.PoliticaSeccionResponse, tags=["receta-secciones"])
def actualizar_politica_seccion(
    seccion_id: int,
    esquema: schemas.PoliticaSeccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Actualiza la tarifa de mano de obra base o los porcentajes de recargo (liquidación, gastos)
    de una sección específica.
    """
    politica = db.query(model.PoliticaSeccion).filter(model.PoliticaSeccion.seccion_id == seccion_id).first()
    if not politica:
        raise HTTPException(status_code=404, detail="Política de sección no encontrada")

    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(politica, campo, valor)
    db.commit()
    db.refresh(politica)
    return politica


@router.post("/seccion/", response_model=schemas.SeccionProductoResponse, status_code=status.HTTP_201_CREATED, tags=["receta-secciones"])
def crear_seccion_producto(
    esquema: schemas.SeccionProductoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Crea una nueva sección para un producto e inicializa su política por defecto."""
    seccion = model.SeccionProducto(
        producto_id=esquema.producto_id,
        nombre=esquema.nombre.upper().strip(),
        orden=esquema.orden
    )
    db.add(seccion)
    db.commit()
    db.refresh(seccion)

    # Crear política de sección por defecto
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


@router.delete("/seccion/{seccion_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["receta-secciones"])
def eliminar_seccion_producto(
    seccion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Elimina una sección de producto y todo lo asociado (cascada)."""
    seccion = db.query(model.SeccionProducto).filter(model.SeccionProducto.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    db.delete(seccion)
    db.commit()
    return None


# ------------------------------------------------------------
# Elementos / Insumos de una Sección
# ------------------------------------------------------------

@router.post("/seccion/{seccion_id}/elemento", response_model=schemas.ElementoSeccionResponse, status_code=status.HTTP_201_CREATED, tags=["receta-secciones"])
def crear_elemento_seccion(
    seccion_id: int,
    esquema: schemas.ElementoSeccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Agrega un insumo físico a una sección específica del producto."""
    seccion = db.query(model.SeccionProducto).filter(model.SeccionProducto.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    elemento = model.ElementoSeccion(seccion_id=seccion_id, **esquema.model_dump(exclude={"seccion_id"}))
    db.add(elemento)
    db.commit()
    db.refresh(elemento)
    return elemento


@router.delete("/elemento/{elemento_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["receta-secciones"])
def eliminar_elemento_seccion(
    elemento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Elimina un insumo de una sección."""
    elemento = db.query(model.ElementoSeccion).filter(model.ElementoSeccion.id == elemento_id).first()
    if not elemento:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")
    db.delete(elemento)
    db.commit()
    return None



# ------------------------------------------------------------
# Costos de Producción por Sección (múltiples items)
# ------------------------------------------------------------

@router.post("/seccion/{seccion_id}/costo-produccion", response_model=schemas.CostoProduccionSeccionResponse, status_code=status.HTTP_201_CREATED, tags=["receta-secciones"])
def crear_costo_produccion_seccion(
    seccion_id: int,
    esquema: schemas.CostoProduccionSeccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Agrega un costo de producción a una sección (ej: PREPARADO CAMA, PINTURA CAMA)."""
    seccion = db.query(model.SeccionProducto).filter(model.SeccionProducto.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    item = model.CostoProduccionSeccion(seccion_id=seccion_id, **esquema.model_dump(exclude={"seccion_id"}))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/costo-produccion/{item_id}", response_model=schemas.CostoProduccionSeccionResponse, tags=["receta-secciones"])
def actualizar_costo_produccion_seccion(
    item_id: int,
    esquema: schemas.CostoProduccionSeccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Actualiza un costo de producción de una sección."""
    item = db.query(model.CostoProduccionSeccion).filter(model.CostoProduccionSeccion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Costo de producción no encontrado")
    datos = esquema.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(item, campo, valor)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/costo-produccion/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["receta-secciones"])
def eliminar_costo_produccion_seccion(
    item_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    """Elimina un costo de producción de una sección."""
    item = db.query(model.CostoProduccionSeccion).filter(model.CostoProduccionSeccion.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Costo de producción no encontrado")
    db.delete(item)
    db.commit()
    return None


@router.post("/recalculate-custom-recipe", tags=["receta-secciones"])
def recalcular_receta_personalizada(
    esquema: schemas.RecalculateCustomRecipeRequest,
    usuario_actual: Usuario = Depends(get_current_user)
):
    """
    Recibe la estructura modificada de secciones e insumos y calcula el desglose de costos
    y precio de venta sugerido sin guardar nada en base de datos.
    """
    from decimal import Decimal, ROUND_HALF_UP

    def _redondear(val: Decimal, decs: int = 2) -> Decimal:
        cuantificador = Decimal("0." + "0" * decs) if decs > 0 else Decimal("1")
        return val.quantize(cuantificador, rounding=ROUND_HALF_UP)

    ganancia_porcentaje = Decimal(str(esquema.ganancia))
    costo_total_elementos = Decimal("0")
    desglose_por_seccion = {}
    detalle_elementos = []

    for sec in esquema.secciones:
        # Sumar insumos de la sección
        costo_insumos = Decimal("0")
        for el in sec.elementos:
            subtotal = Decimal(str(el.cantidad)) * Decimal(str(el.precio_unitario or 0.0))
            costo_insumos += subtotal
            detalle_elementos.append({
                "seccion": sec.nombre,
                "nombre": el.nombre_insumo_original,
                "cantidad": float(el.cantidad),
                "unidad": el.unidad_medida or "",
                "costo_unitario": float(el.precio_unitario or 0.0),
                "costo_subtotal": float(subtotal),
            })

        # Sumar costos de producción individuales
        total_costos_produccion = Decimal("0")
        costos_produccion_detalle = []
        for cp in sec.costos_produccion or []:
            cp_base = Decimal(str(cp.costo_base)) if cp.costo_base else Decimal("0")
            cp_pct = Decimal(str(cp.porcentaje)) if cp.porcentaje else Decimal("0")
            cp_aporte = cp_base + (_redondear(cp_base * cp_pct / Decimal("100"), 2) if cp_pct > 0 else Decimal("0"))
            total_costos_produccion += cp_aporte
            costos_produccion_detalle.append({
                "nombre": cp.nombre,
                "costo_base": float(cp_base),
                "porcentaje": float(cp_pct),
                "aporte": float(cp_aporte),
            })

        # Subtotal seccion = insumos + costos de produccion
        subtotal_seccion = costo_insumos + total_costos_produccion

        # Porcentaje de gastos sección
        pct_gastos_sec = Decimal(str(sec.politica.pct_gastos_seccion)) if sec.politica else Decimal("0")
        gasto_seccion = _redondear(subtotal_seccion * pct_gastos_sec / Decimal("100"), 2) if pct_gastos_sec > 0 else Decimal("0")

        # Total sección
        total_seccion = subtotal_seccion + gasto_seccion
        costo_total_elementos += total_seccion

        desglose_por_seccion[sec.nombre] = {
            "costo_insumos": float(costo_insumos),
            "costos_produccion": costos_produccion_detalle,
            "total_costos_produccion": float(total_costos_produccion),
            "subtotal": float(subtotal_seccion),
            "pct_gastos_seccion": float(pct_gastos_sec),
            "gasto_seccion": float(gasto_seccion),
            "total_seccion": float(total_seccion),
        }

    costo_produccion = costo_total_elementos
    precio_sin_iva = _redondear(costo_produccion * (Decimal("1") + ganancia_porcentaje / Decimal("100")), 2)

    return {
        "costo_materiales": float(costo_total_elementos),
        "costo_mano_obra": 0.0,
        "costo_gastos": 0.0,
        "costo_gastos_indirectos": 0.0,
        "costo_produccion": float(costo_produccion),
        "costo_total": float(costo_produccion),
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(precio_sin_iva),
        "iva_porcentaje": 0.0,
        "precio_con_iva": float(precio_sin_iva),
        "precio_sugerido": float(precio_sin_iva),
        "precio_venta": float(precio_sin_iva),
        "ganancia_monto": float(precio_sin_iva - costo_produccion),
        "materiales": detalle_elementos,
        "desglose_por_seccion": desglose_por_seccion,
    }


