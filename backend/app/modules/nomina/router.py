from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from decimal import Decimal

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import require_module
from app.modules.nomina import service, schemas

router = APIRouter(
    prefix="/nomina",
    tags=["Nómina"],
    dependencies=[Depends(require_module('nomina'))],
)


# ------------------------------------------------------------
# Config de áreas (aguinaldo %)
# ------------------------------------------------------------
@router.get("/area-config", response_model=List[schemas.NominaAreaConfigResponse])
def listar_config_areas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return service.listar_config_areas(db)

@router.put("/area-config/{area_id}", response_model=schemas.NominaAreaConfigResponse)
def actualizar_config_area(
    area_id: int,
    esquema: schemas.NominaAreaConfigCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return service.actualizar_config_area(db, area_id, esquema.porcentaje_aguinaldo)


# ------------------------------------------------------------
# Generación (draft) y CRUD
# ------------------------------------------------------------
@router.post("/generar", response_model=schemas.NominaDraftResponse)
def generar_nomina(
    esquema: schemas.NominaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        return service.generar_nomina(db, esquema.periodo_desde, esquema.periodo_hasta)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/", response_model=schemas.NominaResponse, status_code=201)
def crear_nomina(
    esquema: schemas.NominaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        return service.crear_nomina(db, esquema, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.NominaResponse])
def listar_nominas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return service.listar_nominas(db, skip=skip, limit=limit)

@router.get("/saldos-aguinaldo", response_model=List[schemas.SaldoAguinaldoResponse])
def saldos_aguinaldo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return service.saldos_aguinaldo(db)

# Antes de las rutas dinámicas /{nomina_id} para que FastAPI resuelva el
# prefijo literal /aguinaldo/pagar (no compite con /{nomina_id}, pero se
# mantiene el orden correcto como buena práctica).
@router.post("/aguinaldo/pagar", response_model=schemas.PagoAguinaldoResponse, status_code=201)
def pagar_aguinaldo(
    esquema: schemas.PagoAguinaldoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        return service.pagar_aguinaldo(db, esquema, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{nomina_id}", response_model=schemas.NominaResponse)
def obtener_nomina(
    nomina_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    nomina = service.obtener_nomina(db, nomina_id)
    if not nomina:
        raise HTTPException(status_code=404, detail="Nómina no encontrada")
    return nomina


# ------------------------------------------------------------
# Edición del borrador
# ------------------------------------------------------------
@router.put("/detalle/{detalle_id}", response_model=schemas.NominaDetalleResponse)
def actualizar_detalle(
    detalle_id: int,
    esquema: schemas.NominaDetalleUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        detalle = service.actualizar_detalle(db, detalle_id, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not detalle:
        raise HTTPException(status_code=404, detail="Detalle no encontrado")
    return detalle

@router.post("/detalle/{detalle_id}/linea", response_model=schemas.NominaLineaResponse, status_code=201)
def agregar_linea_manual(
    detalle_id: int,
    esquema: schemas.NominaLineaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        linea = service.agregar_linea_manual(db, detalle_id, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not linea:
        raise HTTPException(status_code=404, detail="Detalle no encontrado")
    return linea

@router.delete("/linea/{linea_id}", status_code=204)
def eliminar_linea(
    linea_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        exito = service.eliminar_linea(db, linea_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Línea no encontrada")
    return None

@router.post("/{nomina_id}/concepto-vario", response_model=schemas.ConceptoVarioResponse, status_code=201)
def agregar_concepto_vario(
    nomina_id: int,
    esquema: schemas.ConceptoVarioCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        concepto = service.agregar_concepto_vario(db, nomina_id, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not concepto:
        raise HTTPException(status_code=404, detail="Nómina no encontrada")
    return concepto

@router.delete("/concepto-vario/{concepto_id}", status_code=204)
def eliminar_concepto_vario(
    concepto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        exito = service.eliminar_concepto_vario(db, concepto_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not exito:
        raise HTTPException(status_code=404, detail="Concepto no encontrado")
    return None


# ------------------------------------------------------------
# Pago y anulación
# ------------------------------------------------------------
@router.post("/{nomina_id}/pagar", response_model=schemas.NominaResponse)
def pagar_nomina(
    nomina_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        nomina = service.pagar_nomina(db, nomina_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not nomina:
        raise HTTPException(status_code=404, detail="Nómina no encontrada")
    return nomina

@router.post("/{nomina_id}/anular", response_model=schemas.NominaResponse)
def anular_nomina(
    nomina_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        nomina = service.anular_nomina(db, nomina_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not nomina:
        raise HTTPException(status_code=404, detail="Nómina no encontrada")
    return nomina
