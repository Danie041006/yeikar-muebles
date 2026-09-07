from sqlalchemy import Column, Integer, BigInteger, Numeric, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class Gasto(Base):
    __tablename__ = "gasto"

    id = Column(Integer, primary_key=True, index=True)
    tipo_gasto_id = Column(BigInteger, ForeignKey("tipo_gasto.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    # Área/departamento al que se imputa el gasto (opcional, se limpia si el área se elimina).
    area_id = Column(BigInteger, ForeignKey("area.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha = Column(Date, nullable=False)
    descripcion = Column(Text, nullable=True)
    monto = Column(Numeric(15,2), nullable=False)
    tasa_cambio = Column(Numeric(15,6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15,2), nullable=False, default=0.0)
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    tipo_gasto = relationship("TipoGasto")
    moneda = relationship("Moneda")
    area = relationship("Area")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def comprobantes(self):
        """Comprobantes digitales del egreso (adjuntos tipo GASTO)."""
        from sqlalchemy.orm import object_session
        from app.modules.adjuntos.service import adjuntos_info
        s = object_session(self)
        if s is None:
            return []
        return adjuntos_info(s, "GASTO", self.id)

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None
