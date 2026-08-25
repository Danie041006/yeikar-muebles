from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Adjunto(Base):
    """Archivo (imagen) adjunto a una entidad del sistema.

    `entidad_tipo` indica el dueño: PRODUCTO (foto de referencia del mueble),
    PAGO (comprobante de ingreso), GASTO/COMPRA (comprobante de egreso).

    Las imágenes se guardan ya optimizadas (redimensionadas/comprimidas) como
    BLOB en la BD, de modo que el respaldo pg_dump cubre todo y el VPS no se
    llena de archivos sueltos.
    """

    __tablename__ = "adjunto"
    __table_args__ = (Index("ix_adjunto_entidad", "entidad_tipo", "entidad_id"),)

    id = Column(BigInteger, primary_key=True, index=True)
    entidad_tipo = Column(String(30), nullable=False)  # PRODUCTO | PAGO | GASTO | COMPRA
    entidad_id = Column(BigInteger, nullable=False)
    # Identificador aleatorio para la URL pública (no-adivinable). Solo los
    # adjuntos de tipo PRODUCTO se sirven públicamente.
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    nombre_original = Column(String(255), nullable=True)
    mime = Column(String(100), nullable=False, default="image/jpeg")
    tamano = Column(BigInteger, nullable=False, default=0)
    archivo = Column(LargeBinary, nullable=False)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())

    creador = relationship("Usuario", foreign_keys=[creado_por_id])
