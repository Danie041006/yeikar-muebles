from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class TipoProducto(Base):
    __tablename__ = "tipo_producto"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class UnidadMedida(Base):
    __tablename__ = "unidad_medida"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    abreviatura = Column(String(10), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class CategoriaInventario(Base):
    """Categoría para desglosar el inventario en la UI.

    tipo = MATERIAL → agrupa insumos (LÁMINAS MDF, ESPUMA, PINTURA, ...)
    tipo = PRODUCTO → agrupa productos de reventa (COLCHONES, ELECTRODOMÉSTICOS, ...)
    """
    __tablename__ = "categoria_inventario"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False, default="MATERIAL")  # MATERIAL | PRODUCTO
    orden = Column(Integer, nullable=False, default=0)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class TipoGasto(Base):
    __tablename__ = "tipo_gasto"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    categoria = Column(String(50), nullable=False, default="OPERATIVO")  # OPERATIVO, PASIVO, PRODUCCION
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Ubicacion(Base):
    __tablename__ = "ubicacion"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)
    tipo = Column(String(50), nullable=False)  # DEPOSITO, TALLER, PUNTO_VENTA
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Area(Base):
    __tablename__ = "area"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Cargo(Base):
    __tablename__ = "cargo"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Moneda(Base):
    __tablename__ = "moneda"

    id = Column(BigInteger, primary_key=True, index=True)
    codigo = Column(String(3), nullable=False)  # COP, USD, VES
    nombre = Column(String(50), nullable=False)
    simbolo = Column(String(5), nullable=False)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Rol(Base):
    __tablename__ = "rol"

    id = Column(BigInteger, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class RolModulo(Base):
    """Acceso de un rol a un módulo del ERP.

    `gestionar = False`  → solo lectura (GET).
    `gestionar = True`   → lectura + escritura (POST/PUT/DELETE).
    Dueño y Administrador tienen acceso total sin filas en esta tabla.
    """

    __tablename__ = "rol_modulo"
    __table_args__ = (UniqueConstraint("rol_id", "modulo", name="uq_rol_modulo"),)

    id = Column(BigInteger, primary_key=True, index=True)
    rol_id = Column(BigInteger, ForeignKey("rol.id", ondelete="CASCADE"), nullable=False, index=True)
    modulo = Column(String(50), nullable=False, index=True)
    gestionar = Column(Boolean, default=False, nullable=False)

    rol = relationship("Rol", backref="modulos")
