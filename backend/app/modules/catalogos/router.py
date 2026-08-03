from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.catalogos import schemas, service

router = APIRouter(dependencies=[Depends(require_module('catalogos', solo_escritura=True))])

# ------------------------------------------------------------
# TipoProducto
# ------------------------------------------------------------
@router.post("/tipo-producto/", response_model=schemas.TipoProductoResponse, status_code=status.HTTP_201_CREATED)
def crear_tipo_producto(
    esquema: schemas.TipoProductoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_tipo_producto(db, esquema)

@router.get("/tipo-producto/", response_model=List[schemas.TipoProductoResponse])
def listar_tipos_productos(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_tipos_productos(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/tipo-producto/{id_tipo}", response_model=schemas.TipoProductoResponse)
def ver_tipo_producto(
    id_tipo: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_tipo_producto(db, id_tipo)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Tipo de producto no encontrado")
    return db_obj

@router.put("/tipo-producto/{id_tipo}", response_model=schemas.TipoProductoResponse)
def actualizar_tipo_producto(
    id_tipo: int,
    esquema: schemas.TipoProductoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_tipo_producto(db, id_tipo, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Tipo de producto no encontrado")
    return db_obj

@router.delete("/tipo-producto/{id_tipo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_tipo_producto(
    id_tipo: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_tipo_producto(db, id_tipo)
    if not exito:
        raise HTTPException(status_code=404, detail="Tipo de producto no encontrado")
    return None

# ------------------------------------------------------------
# UnidadMedida
# ------------------------------------------------------------
@router.post("/unidad-medida/", response_model=schemas.UnidadMedidaResponse, status_code=status.HTTP_201_CREATED)
def crear_unidad_medida(
    esquema: schemas.UnidadMedidaCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_unidad_medida(db, esquema)

@router.get("/unidad-medida/", response_model=List[schemas.UnidadMedidaResponse])
def listar_unidades_medida(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre o abreviatura"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_unidades_medida(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/unidad-medida/{id_unidad}", response_model=schemas.UnidadMedidaResponse)
def ver_unidad_medida(
    id_unidad: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_unidad_medida(db, id_unidad)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Unidad de medida no encontrada")
    return db_obj

@router.put("/unidad-medida/{id_unidad}", response_model=schemas.UnidadMedidaResponse)
def actualizar_unidad_medida(
    id_unidad: int,
    esquema: schemas.UnidadMedidaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_unidad_medida(db, id_unidad, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Unidad de medida no encontrada")
    return db_obj

@router.delete("/unidad-medida/{id_unidad}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_unidad_medida(
    id_unidad: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_unidad_medida(db, id_unidad)
    if not exito:
        raise HTTPException(status_code=404, detail="Unidad de medida no encontrada")
    return None

# ------------------------------------------------------------
# TipoGasto
# ------------------------------------------------------------
@router.post("/tipo-gasto/", response_model=schemas.TipoGastoResponse, status_code=status.HTTP_201_CREATED)
def crear_tipo_gasto(
    esquema: schemas.TipoGastoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_tipo_gasto(db, esquema)

@router.get("/tipo-gasto/", response_model=List[schemas.TipoGastoResponse])
def listar_tipos_gasto(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria: OPERATIVO, PASIVO, PRODUCCION"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_tipos_gasto(db, salto=salto, limite=limite, buscar=buscar, categoria=categoria)

@router.get("/tipo-gasto/{id_gasto}", response_model=schemas.TipoGastoResponse)
def ver_tipo_gasto(
    id_gasto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_tipo_gasto(db, id_gasto)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Tipo de gasto no encontrado")
    return db_obj

@router.put("/tipo-gasto/{id_gasto}", response_model=schemas.TipoGastoResponse)
def actualizar_tipo_gasto(
    id_gasto: int,
    esquema: schemas.TipoGastoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_tipo_gasto(db, id_gasto, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Tipo de gasto no encontrado")
    return db_obj

@router.delete("/tipo-gasto/{id_gasto}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_tipo_gasto(
    id_gasto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_tipo_gasto(db, id_gasto)
    if not exito:
        raise HTTPException(status_code=404, detail="Tipo de gasto no encontrado")
    return None

# ------------------------------------------------------------
# Ubicacion
# ------------------------------------------------------------
@router.post("/ubicacion/", response_model=schemas.UbicacionResponse, status_code=status.HTTP_201_CREATED)
def crear_ubicacion(
    esquema: schemas.UbicacionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_ubicacion(db, esquema)

@router.get("/ubicacion/", response_model=List[schemas.UbicacionResponse])
def listar_ubicaciones(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre, descripcion o tipo"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_ubicaciones(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/ubicacion/{id_ubicacion}", response_model=schemas.UbicacionResponse)
def ver_ubicacion(
    id_ubicacion: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_ubicacion(db, id_ubicacion)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Ubicacion no encontrada")
    return db_obj

@router.put("/ubicacion/{id_ubicacion}", response_model=schemas.UbicacionResponse)
def actualizar_ubicacion(
    id_ubicacion: int,
    esquema: schemas.UbicacionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_ubicacion(db, id_ubicacion, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Ubicacion no encontrada")
    return db_obj

@router.delete("/ubicacion/{id_ubicacion}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_ubicacion(
    id_ubicacion: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_ubicacion(db, id_ubicacion)
    if not exito:
        raise HTTPException(status_code=404, detail="Ubicacion no encontrada")
    return None

# ------------------------------------------------------------
# Area
# ------------------------------------------------------------
@router.post("/area/", response_model=schemas.AreaResponse, status_code=status.HTTP_201_CREATED)
def crear_area(
    esquema: schemas.AreaCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_area(db, esquema)

@router.get("/area/", response_model=List[schemas.AreaResponse])
def listar_areas(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_areas(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/area/{id_area}", response_model=schemas.AreaResponse)
def ver_area(
    id_area: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_area(db, id_area)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Area no encontrada")
    return db_obj

@router.put("/area/{id_area}", response_model=schemas.AreaResponse)
def actualizar_area(
    id_area: int,
    esquema: schemas.AreaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_area(db, id_area, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Area no encontrada")
    return db_obj

@router.delete("/area/{id_area}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_area(
    id_area: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_area(db, id_area)
    if not exito:
        raise HTTPException(status_code=404, detail="Area no encontrada")
    return None

# ------------------------------------------------------------
# Cargo
# ------------------------------------------------------------
@router.post("/cargo/", response_model=schemas.CargoResponse, status_code=status.HTTP_201_CREATED)
def crear_cargo(
    esquema: schemas.CargoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_cargo(db, esquema)

@router.get("/cargo/", response_model=List[schemas.CargoResponse])
def listar_cargos(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_cargos(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/cargo/{id_cargo}", response_model=schemas.CargoResponse)
def ver_cargo(
    id_cargo: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_cargo(db, id_cargo)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    return db_obj

@router.put("/cargo/{id_cargo}", response_model=schemas.CargoResponse)
def actualizar_cargo(
    id_cargo: int,
    esquema: schemas.CargoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_cargo(db, id_cargo, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    return db_obj

@router.delete("/cargo/{id_cargo}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cargo(
    id_cargo: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_cargo(db, id_cargo)
    if not exito:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    return None

# ------------------------------------------------------------
# Moneda
# ------------------------------------------------------------
@router.post("/moneda/", response_model=schemas.MonedaResponse, status_code=status.HTTP_201_CREATED)
def crear_moneda(
    esquema: schemas.MonedaCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_moneda(db, esquema)

@router.get("/moneda/", response_model=List[schemas.MonedaResponse])
def listar_monedas(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por codigo, nombre o simbolo"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_monedas(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/moneda/{id_moneda}", response_model=schemas.MonedaResponse)
def ver_moneda(
    id_moneda: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_moneda(db, id_moneda)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Moneda no encontrada")
    return db_obj

@router.put("/moneda/{id_moneda}", response_model=schemas.MonedaResponse)
def actualizar_moneda(
    id_moneda: int,
    esquema: schemas.MonedaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_moneda(db, id_moneda, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Moneda no encontrada")
    return db_obj

@router.delete("/moneda/{id_moneda}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_moneda(
    id_moneda: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    exito = service.eliminar_moneda(db, id_moneda)
    if not exito:
        raise HTTPException(status_code=404, detail="Moneda no encontrada")
    return None

# ------------------------------------------------------------
# Rol
# ------------------------------------------------------------
@router.post("/rol/", response_model=schemas.RolResponse, status_code=status.HTTP_201_CREATED)
def crear_rol(
    esquema: schemas.RolCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.crear_rol(db, esquema)

@router.get("/rol/", response_model=List[schemas.RolResponse])
def listar_roles(
    salto: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=1000),
    buscar: Optional[str] = Query(None, description="Buscar por nombre o descripcion"),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    return service.obtener_roles(db, salto=salto, limite=limite, buscar=buscar)

@router.get("/rol/{id_rol}", response_model=schemas.RolResponse)
def ver_rol(
    id_rol: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_rol(db, id_rol)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return db_obj

@router.put("/rol/{id_rol}", response_model=schemas.RolResponse)
def actualizar_rol(
    id_rol: int,
    esquema: schemas.RolUpdate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.actualizar_rol(db, id_rol, esquema)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return db_obj

@router.delete("/rol/{id_rol}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_rol(
    id_rol: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user)
):
    db_obj = service.obtener_rol(db, id_rol)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if db_obj.nombre in ("Dueño", "Administrador"):
        raise HTTPException(status_code=400, detail=f"El rol '{db_obj.nombre}' es de acceso total y no se puede eliminar")
    exito = service.eliminar_rol(db, id_rol)
    if not exito:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return None
