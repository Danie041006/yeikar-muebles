from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.inventory import service, schemas

router = APIRouter(prefix="/inventario", tags=["Inventario"])


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
        mov = service.registrar_movimiento(db, movimiento)
        return mov
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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