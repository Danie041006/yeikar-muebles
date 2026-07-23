from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.productos import schemas, service
from app.modules.productos import cost_service
from app.modules.productos.model import ProductoMaterial

router = APIRouter()

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
@router.post("/material/", response_model=schemas.MaterialResponse, status_code=status.HTTP_201_CREATED)
def crear_material(
    esquema: schemas.MaterialCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_material(db, esquema)

@router.get("/material/", response_model=List[schemas.MaterialResponse])
def listar_materiales(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_materiales(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/material/{id_material}", response_model=schemas.MaterialResponse)
def ver_material(
    id_material: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_material(db, id_material)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    return db_obj

@router.put("/material/{id_material}", response_model=schemas.MaterialResponse)
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

@router.delete("/material/{id_material}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_material(
    id_material: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_material(db, id_material)
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

