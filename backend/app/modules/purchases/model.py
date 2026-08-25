from sqlalchemy import Column, DateTime, Date, ForeignKey, Numeric, BigInteger, Text, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.proveedores.model import Proveedor  # noqa: F401 — necesario para resolver la relación SQLAlchemy
from app.modules.catalogos.model import Moneda  # noqa: F401 — necesario para resolver la relación SQLAlchemy

class Compra(Base):
    __tablename__ = "compra"

    id = Column(BigInteger, primary_key=True, index=True)
    proveedor_id = Column(BigInteger, ForeignKey("proveedor.id"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), default="BORRADOR", nullable=False)
    tipo_pago = Column(String(50), default="CREDITO", nullable=False)  # CONTADO | CREDITO
    # Cuenta de caja de la que sale el dinero al recibir una compra CONTADO.
    metodo_caja_id = Column(BigInteger, ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=True)
    # Tasa de cambio al momento de la compra (COP por 1 unidad de moneda de la compra).
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    # Total convertido a moneda base (COP) con la tasa del día de la compra.
    total_en_moneda_base = Column(Numeric(15, 2), nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    proveedor = relationship("Proveedor")
    moneda = relationship("Moneda")
    detalles = relationship("DetalleCompra", back_populates="compra", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(d.cantidad * d.costo_unitario for d in self.detalles) if self.detalles else 0.0

    @property
    def comprobantes(self):
        """Comprobantes digitales de la compra (adjuntos tipo COMPRA)."""
        from sqlalchemy.orm import object_session
        from app.modules.adjuntos.service import adjuntos_info
        s = object_session(self)
        if s is None:
            return []
        return adjuntos_info(s, "COMPRA", self.id)

class DetalleCompra(Base):
    __tablename__ = "detalle_compra"

    id = Column(BigInteger, primary_key=True, index=True)
    compra_id = Column(BigInteger, ForeignKey("compra.id", ondelete="CASCADE"), nullable=False)
    material_id = Column(BigInteger, ForeignKey("material.id"), nullable=False)
    cantidad = Column(Numeric(12, 2), nullable=False)
    costo_unitario = Column("costo_unitario", Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    compra = relationship("Compra", back_populates="detalles")
    material = relationship("Material")
