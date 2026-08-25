import io

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.adjuntos import model
from app.modules.adjuntos.schemas import AdjuntoInfo
from app.modules.productos.model import Producto
from app.modules.sales.model import Pago
from app.modules.gastos.model import Gasto
from app.modules.purchases.model import Compra

try:  # Soporte opcional para HEIC (fotos de iPhone). Si no está instalado, se
    # rechaza el formato con un mensaje claro.
    import pillow_heif  # noqa: F401

    pillow_heif.register_heif_opener()
    _HEIF_DISPONIBLE = True
except Exception:  # pragma: no cover
    _HEIF_DISPONIBLE = False

from PIL import Image, ImageOps

MAX_RAW_BYTES = 15 * 1024 * 1024  # 15 MB crudos por subida

# Configuración de optimización por tipo de entidad: el formato, el lado máximo
# y la calidad se eligen según el uso.
#  - PRODUCTO (fotos de muebles): WebP a 1024 px → ligeras, bastan para tarjeta
#    y para el PDF de la cotización.
#  - PAGO/GASTO/COMPRA (comprobantes con letras y números): JPEG a 2000 px para
#    que el texto se lea nítido sin que el archivo pese.
_CONFIG_IMAGEN = {
    "PRODUCTO": {"formato": "WEBP", "mime": "image/webp", "max_lado": 1024, "calidad": 80},
    "PAGO": {"formato": "JPEG", "mime": "image/jpeg", "max_lado": 2000, "calidad": 85},
    "GASTO": {"formato": "JPEG", "mime": "image/jpeg", "max_lado": 2000, "calidad": 85},
    "COMPRA": {"formato": "JPEG", "mime": "image/jpeg", "max_lado": 2000, "calidad": 85},
}

# Entidades que aceptan adjuntos (para validar entidad_tipo).
ENTIDADES_VALIDAS = ("PRODUCTO", "PAGO", "GASTO", "COMPRA")

# Tipos que pueden servirse públicamente (fotos de catálogo que salen en el PDF
# de la cotización). Los comprobantes NUNCA se exponen sin autenticación.
TIPOS_PUBLICOS = ("PRODUCTO",)


def procesar_imagen(contenido: bytes, entidad_tipo: str):
    """Redimensiona y comprime la imagen según el tipo de entidad.

    Devuelve (bytes_optimizados, mime, tamaño). Jamás guarda el original crudo,
    de modo que el almacenamiento en la BD se reduce ~20-30x.
    """
    cfg = _CONFIG_IMAGEN.get(entidad_tipo) or _CONFIG_IMAGEN["GASTO"]
    try:
        img = Image.open(io.BytesIO(contenido))
        img = ImageOps.exif_transpose(img)  # auto-orienta según EXIF
        img = img.convert("RGB")            # quita alpha/CMYK → base RGB
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es una imagen válida (usa JPG, PNG, WebP o HEIC).",
        )
    img.thumbnail((cfg["max_lado"], cfg["max_lado"]), Image.LANCZOS)
    buf = io.BytesIO()
    if cfg["formato"] == "WEBP":
        img.save(buf, "WEBP", quality=cfg["calidad"], method=6)
    else:
        img.save(buf, "JPEG", quality=cfg["calidad"], optimize=True, progressive=True)
    data = buf.getvalue()
    return data, cfg["mime"], len(data)


def validar_entidad(db: Session, entidad_tipo: str, entidad_id: int) -> None:
    """Verifica que la entidad destino exista (para no crear adjuntos huérfanos)."""
    if entidad_tipo not in ENTIDADES_VALIDAS:
        raise HTTPException(status_code=400, detail=f"Tipo de entidad inválido: {entidad_tipo}")
    if entidad_tipo == "PRODUCTO":
        existe = db.query(Producto).filter_by(id=entidad_id).first()
    elif entidad_tipo == "PAGO":
        existe = db.query(Pago).filter_by(id=entidad_id).first()
    elif entidad_tipo == "GASTO":
        existe = db.query(Gasto).filter_by(id=entidad_id).first()
    else:
        existe = db.query(Compra).filter_by(id=entidad_id).first()
    if not existe:
        raise HTTPException(status_code=404, detail=f"La entidad {entidad_tipo} {entidad_id} no existe")


def guardar_adjunto(
    db: Session,
    entidad_tipo: str,
    entidad_id: int,
    nombre_original: str | None,
    contenido: bytes,
    usuario_id: int | None = None,
) -> model.Adjunto:
    datos, mime, tamano = procesar_imagen(contenido, entidad_tipo)
    adj = model.Adjunto(
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        nombre_original=(nombre_original or "imagen")[:255],
        mime=mime,
        tamano=tamano,
        archivo=datos,
        creado_por_id=usuario_id,
    )
    db.add(adj)
    db.commit()
    db.refresh(adj)
    return adj


def listar_adjuntos(db: Session, entidad_tipo: str, entidad_id: int):
    return (
        db.query(model.Adjunto)
        .filter(model.Adjunto.entidad_tipo == entidad_tipo, model.Adjunto.entidad_id == entidad_id)
        .order_by(model.Adjunto.id.desc())
        .all()
    )


def _info(adj: model.Adjunto, publico: bool) -> dict:
    return {
        "id": adj.id,
        "nombre": adj.nombre_original,
        "mime": adj.mime,
        "tamano": adj.tamano,
        "url": f"/api/v1/adjunto/publico/{adj.uuid}/contenido" if publico else None,
    }


def adjuntos_info(db: Session, entidad_tipo: str, entidad_id: int) -> list[AdjuntoInfo]:
    """Información de los adjuntos de una entidad (sin los bytes)."""
    publico = entidad_tipo in TIPOS_PUBLICOS
    return [_info(a, publico) for a in listar_adjuntos(db, entidad_tipo, entidad_id)]


def obtener_adjunto(db: Session, id_adjunto: int) -> model.Adjunto | None:
    return db.query(model.Adjunto).filter(model.Adjunto.id == id_adjunto).first()


def obtener_adjunto_por_uuid(db: Session, uuid_adjunto: str) -> model.Adjunto | None:
    return db.query(model.Adjunto).filter(model.Adjunto.uuid == uuid_adjunto).first()


def eliminar_adjunto(db: Session, id_adjunto: int) -> bool:
    adj = obtener_adjunto(db, id_adjunto)
    if not adj:
        return False
    db.delete(adj)
    db.commit()
    return True
