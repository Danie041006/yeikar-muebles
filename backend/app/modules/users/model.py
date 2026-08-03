from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Table, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.catalogos.model import Rol

# Tabla de asociación para la relación Muchos a Muchos entre Usuario y Rol
usuario_rol = Table(
    "usuario_rol",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("usuario_id", Integer, ForeignKey("usuario.id", ondelete="CASCADE")),
    Column("rol_id", Integer, ForeignKey("rol.id", ondelete="RESTRICT")),
    extend_existing=True
)

class Usuario(Base):
    __tablename__ = "usuario"   # Debe coincidir exactamente con el nombre de la tabla

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, nullable=True)  # Puede ser NULL
    nombre_usuario = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=True)
    password_hash = Column(String, nullable=False)
    activo = Column(Boolean, default=True)
    ultimo_acceso = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relación Muchos a Muchos
    roles = relationship("Rol", secondary=usuario_rol, backref="usuarios")

class LoginIntento(Base):
    __tablename__ = "login_intento"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(100), index=True)
    ip = Column(String(45), index=True)
    exito = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_login_intento_username_created_at", "username", "created_at"),
    )

class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id = Column(BigInteger, primary_key=True, index=True)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    token_hash = Column(String(64), unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    revocado = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", backref="refresh_tokens")
