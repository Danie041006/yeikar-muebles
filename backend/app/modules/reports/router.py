from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.reports import service, schemas

router = APIRouter(prefix="/reports", tags=["Reportes"])

@router.get("/pnl", response_model=schemas.PnLResponse)
def get_pnl(
    mes: str = Query(..., description="Mes a consultar en formato YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Obtiene el reporte de pérdidas y ganancias (PnL) agrupado por moneda para un mes específico."""
    try:
        return service.obtener_pnl(db, mes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/rentabilidad-producto", response_model=List[schemas.RentabilidadProductoResponse])
def get_rentabilidad_productos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Calcula la rentabilidad y el margen promedio estimado por producto basándose en costos de producción y ventas."""
    return service.obtener_rentabilidad_productos(db)

@router.get("/alertas-stock", response_model=List[schemas.ReportAlertaStockResponse])
def get_alertas_stock(
    umbral: float = Query(5.0, description="Umbral de stock bajo"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Devuelve una lista de materiales en inventario con stock inferior o igual al umbral especificado."""
    return service.obtener_alertas_stock(db, Decimal(str(umbral)))
