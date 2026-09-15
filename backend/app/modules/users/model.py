from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.catalogos.model import Rol

# Tabla de asociación para la relación Muchos a Muchos entre Usuario y Rol
usuario_rol = Table(
    "usuario_rol",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("usuario_id", BigInteger, ForeignKey("usuario.id", ondelete="CASCADE")),
    Column("rol_id", BigInteger, ForeignKey("rol.id", ondelete="RESTRICT")),
    extend_existing=True
)

class Usuario(Base):
    __tablename__ = "usuario"   # Debe coincidir exactamente con el nombre de la tabla

    id = Column(BigInteger, primary_key=True, index=True)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True, index=True)
    nombre_usuario = Column(String(100), unique=True, nullable=False, index=True)
    # Nombre visible (p. ej. "Carolina"): la UI saluda con esto, no con el
    # nombre de usuario (que ahora puede ser una clave tipo Mistreshijos123).
    nombre = Column(String(100), nullable=True)
    email = Column(String(150), unique=True, nullable=True)
    password_hash = Column(String, nullable=False)
    activo = Column(Boolean, default=True)
    ultimo_acceso = Column(DateTime, nullable=True)
    # 2FA con app (TOTP RFC 6238): el secreto se genera al pedir el QR y solo
    # se "habilita" tras confirmar un código válido. Los códigos de respaldo
    # se guardan como hashes sha256 en JSON (un solo uso cada uno).
    totp_secret = Column(String(64), nullable=True)
    totp_habilitado = Column(Boolean, default=False, server_default="false")
    totp_respaldo_hash = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relación Muchos a Muchos
    roles = relationship("Rol", secondary=usuario_rol, backref="usuarios")
    empleado = relationship("Empleado", foreign_keys=[empleado_id])

    @property
    def display_name(self) -> str:
        """Nombre real para auditoría/UI, con fallback al login.

        Fuente única de verdad: todo "quién registró" debe usar esto,
        nunca `nombre_usuario` directo.
        """
        return self.nombre or self.nombre_usuario

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

class Sesion(Base):
    """Sesión de acceso visible: un login = una fila (equipo, IP, último uso).

    La revocación apaga su refresh token: el access token vence solo en
    minutos, así que el logout real ocurre al siguiente refresh.
    """
    __tablename__ = "sesion"

    id = Column(BigInteger, primary_key=True, index=True)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    refresh_token_id = Column(BigInteger, ForeignKey("refresh_token.id", ondelete="CASCADE"), nullable=True, index=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(300), nullable=True)
    revocada = Column(Boolean, default=False, index=True)
    creado_en = Column(DateTime, server_default=func.now())
    ultimo_uso = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario")

class CredencialWebauthn(Base):
    """Llave biométrica de un equipo (huella/Face ID/PIN) vía WebAuthn.

    `credential_id` es el ID opaco de la credencial; `llave_publica` guarda
    la clave pública en base64. `contador` detecta claves clonadas: si el
    navegador reporta un contador menor o igual sin firma previa, la credencial
    es sospechosa.
    """
    __tablename__ = "credencial_webauthn"

    id = Column(BigInteger, primary_key=True, index=True)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    credential_id = Column(String(300), unique=True, index=True)
    llave_publica = Column(Text, nullable=False)
    contador = Column(BigInteger, default=0)
    dispositivo = Column(String(100), nullable=True)
    activa = Column(Boolean, default=True, index=True)
    creado_en = Column(DateTime, server_default=func.now())
    ultimo_uso = Column(DateTime, nullable=True)

    usuario = relationship("Usuario")
