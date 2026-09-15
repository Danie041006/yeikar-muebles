from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.users.model import Usuario
from app.modules.users.router import get_current_user
from app.modules.adjuntos import schemas, service

router = APIRouter(prefix="/api/v1/adjunto", tags=["adjuntos"])


@router.post("/upload", response_model=schemas.AdjuntoResponse, status_code=status.HTTP_201_CREATED)
def subir_adjunto(
    entidad_tipo: str = Form(...),
    entidad_id: int = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    """Sube una imagen (foto de mueble o comprobante) asociada a una entidad.

    La imagen se redimensiona/comprime en el servidor según el tipo
    (PRODUCTO → WebP 1024px; PAGO/GASTO/COMPRA → JPEG 2000px) y se guarda
    optimizada en la BD.
    """
    service.validar_entidad(db, entidad_tipo, entidad_id)
    contenido = archivo.file.read()
    if len(contenido) > service.MAX_RAW_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La imagen supera el tamaño máximo permitido (15 MB).",
        )
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    adj = service.guardar_adjunto(
        db, entidad_tipo, entidad_id, archivo.filename, contenido, usuario_actual.id
    )
    publico = entidad_tipo in service.TIPOS_PUBLICOS
    return schemas.AdjuntoResponse(
        id=adj.id,
        entidad_tipo=adj.entidad_tipo,
        entidad_id=adj.entidad_id,
        uuid=adj.uuid,
        nombre=adj.nombre_original,
        mime=adj.mime,
        tamano=adj.tamano,
        url=f"/api/v1/adjunto/publico/{adj.uuid}/contenido" if publico else None,
        creado_por_id=adj.creado_por_id,
        creador_nombre=usuario_actual.display_name,
        created_at=adj.created_at,
    )


@router.get("", response_model=List[schemas.AdjuntoResponse])
def listar_adjuntos(
    entidad_tipo: str = Query(...),
    entidad_id: int = Query(...),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    publico = entidad_tipo in service.TIPOS_PUBLICOS
    resultado = []
    for adj in service.listar_adjuntos(db, entidad_tipo, entidad_id):
        resultado.append(
            schemas.AdjuntoResponse(
                id=adj.id,
                entidad_tipo=adj.entidad_tipo,
                entidad_id=adj.entidad_id,
                uuid=adj.uuid,
                nombre=adj.nombre_original,
                mime=adj.mime,
                tamano=adj.tamano,
                url=f"/api/v1/adjunto/publico/{adj.uuid}/contenido" if publico else None,
                creado_por_id=adj.creado_por_id,
                creador_nombre=adj.creador_nombre,
                created_at=adj.created_at,
            )
        )
    return resultado


@router.get("/{id_adjunto}/contenido")
def contenido_autenticado(
    id_adjunto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    """Devuelve los bytes de un adjunto. Requiere autenticación (recibos,
    comprobantes y fotos). El frontend los descarga con su token y los muestra
    como blob, de modo que los comprobantes nunca se exponen públicamente."""
    adj = service.obtener_adjunto(db, id_adjunto)
    if not adj:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return Response(content=adj.archivo, media_type=adj.mime)


@router.get("/publico/{uuid_adjunto}/contenido")
def contenido_publico(uuid_adjunto: str, db: Session = Depends(get_db)):
    """URL pública SIN autenticación, solo para adjuntos de tipo PRODUCTO
    (fotos de catálogo que se incrustan en el PDF de la cotización).

    El UUID aleatorio hace la URL no-adivinable. Los comprobantes devuelven
    404 para que jamás se expongan públicamente.
    """
    adj = service.obtener_adjunto_por_uuid(db, uuid_adjunto)
    if not adj or adj.entidad_tipo not in service.TIPOS_PUBLICOS:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return Response(content=adj.archivo, media_type=adj.mime)


@router.delete("/{id_adjunto}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_adjunto(
    id_adjunto: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_current_user),
):
    if not service.eliminar_adjunto(db, id_adjunto):
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return None
