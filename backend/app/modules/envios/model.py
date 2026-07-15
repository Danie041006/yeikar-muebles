from sqlalchemy import Column, DateTime, Text, BigInteger, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
class Envio(Base):
    __tablename__ = "envio"
    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="CASCADE"), unique=True, nullable=False)
    empleado_id = Column(BigInteger, ForeignKey("empleado.id", ondelete="SET NULL"), nullable=True)
    fecha_salida = Column(DateTime, nullable=True)
    fecha_entrega = Column(DateTime, nullable=True)
    estado = Column(String(50), nullable=False)  # 'PREPARADO', 'EN_TRANSITO', 'ENTREGADO', 'FALLIDO'
    direccion_entrega = Column(Text, nullable=True)
    guia_despacho = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    pedido = relationship("Pedido")
    empleado = relationship("Empleado")
