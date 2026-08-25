from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import date

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario
from app.modules.users.deps import es_admin, require_module
from app.modules.reports import service, schemas

router = APIRouter(
    prefix="/reports",
    tags=["Reportes"],
    dependencies=[Depends(require_module('reportes')), Depends(es_admin)],
)

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

@router.get("/diario", response_model=schemas.ResumenDiarioResponse)
def get_resumen_diario(
    fecha: Optional[date] = Query(None, description="Fecha del día (YYYY-MM-DD). Por defecto, hoy"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Estado del día: saldo inicial, ingresos, egresos, quién los hizo y saldo final."""
    return service.resumen_diario(db, fecha or date.today())

@router.get("/informe-mensual", response_model=schemas.InformeMensualResponse)
def get_informe_mensual(
    mes: str = Query(..., description="Mes a consultar en formato YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Obtiene el Informe Mensual completo: Control Interno de Ingresos, Resumen del mes y Estado de Resultados."""
    try:
        return service.obtener_informe_mensual(db, mes)
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


# ------------------------------------------------------------
# Conceptos de reporte (catálogo flexible)
# ------------------------------------------------------------
@router.get("/conceptos", response_model=List[schemas.ConceptoReporteResponse])
def get_conceptos(
    seccion: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_conceptos(db, seccion)

@router.post("/conceptos", response_model=schemas.ConceptoReporteResponse, status_code=201)
def post_concepto(
    esquema: schemas.ConceptoReporteCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.crear_concepto(db, esquema)

@router.put("/conceptos/{concepto_id}", response_model=schemas.ConceptoReporteResponse)
def put_concepto(
    concepto_id: int,
    esquema: schemas.ConceptoReporteUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    obj = service.actualizar_concepto(db, concepto_id, esquema)
    if not obj:
        raise HTTPException(status_code=404, detail="Concepto no encontrado")
    return obj

@router.delete("/conceptos/{concepto_id}", status_code=204)
def delete_concepto(
    concepto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_concepto(db, concepto_id):
        raise HTTPException(status_code=404, detail="Concepto no encontrado")
    return None


# ------------------------------------------------------------
# Valores mensuales de conceptos (corte de inventario)
# ------------------------------------------------------------
@router.get("/valores-mensuales", response_model=List[schemas.ValorConceptoMensualResponse])
def get_valores_mensuales(
    mes: str = Query(..., description="Mes en formato YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.obtener_valores_mensuales(db, mes)

@router.put("/valores-mensuales/{mes}", response_model=List[schemas.ValorConceptoMensualResponse])
def put_valores_mensuales(
    mes: str,
    valores: List[schemas.ValorConceptoMensualCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.guardar_valores_mensuales(db, mes, valores)


# ------------------------------------------------------------
# Métodos de caja
# ------------------------------------------------------------
@router.get("/metodos-caja", response_model=List[schemas.MetodoCajaResponse])
def get_metodos_caja(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_metodos_caja(db)

@router.post("/metodos-caja", response_model=schemas.MetodoCajaResponse, status_code=201)
def post_metodo_caja(
    esquema: schemas.MetodoCajaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.crear_metodo_caja(db, esquema)

@router.put("/metodos-caja/{metodo_id}", response_model=schemas.MetodoCajaResponse)
def put_metodo_caja(
    metodo_id: int,
    esquema: schemas.MetodoCajaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    obj = service.actualizar_metodo_caja(db, metodo_id, esquema)
    if not obj:
        raise HTTPException(status_code=404, detail="Método de caja no encontrado")
    return obj

@router.delete("/metodos-caja/{metodo_id}", status_code=204)
def delete_metodo_caja(
    metodo_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_metodo_caja(db, metodo_id):
        raise HTTPException(status_code=404, detail="Método de caja no encontrado")
    return None


# ------------------------------------------------------------
# Movimientos de caja
# ------------------------------------------------------------
@router.get("/movimientos-caja", response_model=List[schemas.MovimientoCajaResponse])
def get_movimientos_caja(
    metodo_caja_id: Optional[int] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_movimientos_caja(db, metodo_caja_id, fecha_desde, fecha_hasta)

@router.post("/movimientos-caja", response_model=schemas.MovimientoCajaResponse, status_code=201)
def post_movimiento_caja(
    esquema: schemas.MovimientoCajaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.crear_movimiento_caja(db, esquema)

@router.put("/movimientos-caja/{movimiento_id}", response_model=schemas.MovimientoCajaResponse)
def put_movimiento_caja(
    movimiento_id: int,
    esquema: schemas.MovimientoCajaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    obj = service.actualizar_movimiento_caja(db, movimiento_id, esquema)
    if not obj:
        raise HTTPException(status_code=404, detail="Movimiento de caja no encontrado")
    return obj

@router.delete("/movimientos-caja/{movimiento_id}", status_code=204)
def delete_movimiento_caja(
    movimiento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_movimiento_caja(db, movimiento_id):
        raise HTTPException(status_code=404, detail="Movimiento de caja no encontrado")
    return None


# ------------------------------------------------------------
# Devoluciones de venta
# ------------------------------------------------------------
@router.get("/devoluciones", response_model=List[schemas.DevolucionVentaResponse])
def get_devoluciones(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return service.listar_devoluciones(db, fecha_desde, fecha_hasta)

@router.post("/devoluciones", response_model=schemas.DevolucionVentaResponse, status_code=201)
def post_devolucion(
    esquema: schemas.DevolucionVentaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    try:
        return service.crear_devolucion(db, esquema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/devoluciones/{devolucion_id}", status_code=204)
def delete_devolucion(
    devolucion_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if not service.eliminar_devolucion(db, devolucion_id):
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    return None
