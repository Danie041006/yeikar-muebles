from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class SyncCambio(Base):
    """Bitácora de cambios para la réplica offline de los dispositivos.

    La llenan triggers de PostgreSQL (uno por tabla, ver migración
    `sync_offline`) en cada INSERT/UPDATE/DELETE. El `id` es el cursor
    monótono que los clientes guardan y piden con `?desde=`.
    """

    __tablename__ = "sync_cambio"

    id = Column(BigInteger, primary_key=True, index=True)
    tabla = Column(String(80), nullable=False)
    pk = Column(String(64), nullable=False)
    op = Column(String(1), nullable=False)  # I = insert, U = update, D = delete
    ocurrido_en = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_sync_cambio_tabla_pk", "tabla", "pk"),
    )


class SyncOperacion(Base):
    """Operación enviada por un dispositivo offline (motor de push).

    La fila se inserta ANTES de ejecutar el handler (`EN_PROCESO`) para que
    reintentos concurrentes no dupliquen el efecto; al terminar se guarda el
    resultado y el reintento devuelve exactamente lo mismo (idempotencia).
    """

    __tablename__ = "sync_operacion"

    operacion_id = Column(String(36), primary_key=True)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    tipo = Column(String(120), nullable=False)
    estado = Column(String(20), nullable=False, default="EN_PROCESO")  # EN_PROCESO, OK, CONFLICTO, ERROR
    resultado = Column(JSON, nullable=True)
    ocurrida_en = Column(DateTime, nullable=True)  # hora del dispositivo al capturar
    aplicada_en = Column(DateTime, server_default=func.now(), nullable=False, index=True)
