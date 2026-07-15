from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.modules.users.router import get_current_user
from app.modules.users.model import Usuario

from app.modules.purchases import service, schemas

router = APIRouter(prefix="/compras", tags=["Compras"])

@router.post("/", response_model=schemas.CompraResponse, status_code=201)
def crear_compra(compra: schemas.CompraCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Registra una compra y actualiza el inventario mediante registrar_movimiento (tipo ENTRADA)."""
    try:
        nueva_compra = service.crear_compra(db, compra)
        return nueva_compra
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[schemas.CompraResponse])
def listar_compras(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtiene una lista paginada de compras."""
    return service.obtener_compras(db, skip=skip, limit=limit)

@router.get("/{compra_id}", response_model=schemas.CompraResponse)
def obtener_compra(compra_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Obtiene los detalles de una compra por su ID."""
    compra = service.obtener_compra(db, compra_id)
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    return compra

@router.put("/{compra_id}/estado", response_model=schemas.CompraResponse)
def actualizar_estado_compra(
    compra_id: int,
    estado: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Actualiza el estado de una compra (transición a RECIBIDA dispara entrada de stock)."""
    compra = service.obtener_compra(db, compra_id)
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    
    if estado not in ["BORRADOR", "EMITIDA", "RECIBIDA", "CANCELADA"]:
        raise HTTPException(status_code=400, detail="Estado de compra inválido")
        
    compra_update = schemas.CompraBase(
        proveedor_id=compra.proveedor_id,
        moneda_id=compra.moneda_id,
        fecha=compra.fecha,
        estado=estado,
        observaciones=compra.observaciones
    )
    return service.actualizar_compra(db, compra_id, compra_update)
