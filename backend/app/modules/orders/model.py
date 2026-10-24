from decimal import Decimal

from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from app.modules.clients.model import Client
from app.modules.quotes.model import Cotizacion
from app.modules.productos.model import Producto, Material

class Pedido(Base):
    __tablename__ = "pedido"

    id = Column(BigInteger, primary_key=True, index=True)
    cotizacion_id = Column(BigInteger, ForeignKey("cotizacion.id"), unique=True, nullable=False)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), nullable=False)
    observaciones = Column(Text, nullable=True)
    fecha_entrega_estimada = Column(Date, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    actualizado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    cliente = relationship("Client")
    cotizacion = relationship("Cotizacion")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    actualizador = relationship("Usuario", foreign_keys=[actualizado_por_id])

    @property
    def creador_nombre(self):
        return (self.creador.nombre or self.creador.nombre_usuario) if self.creador else None
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")
    # Despachos del pedido. Puede haber varios (entregas parciales).
    envios = relationship(
        "Envio",
        back_populates="pedido",
        cascade="all, delete-orphan",
        order_by="Envio.id",
    )

    @property
    def entrega_resumen(self) -> dict:
        """Progreso de entrega en unidades físicas (piezas cuando el juego las declara).

        - `total` / `entregado` / `pendiente`: cantidades.
        - `estado`: PENDIENTE | PARCIAL | COMPLETO.
        - Los envíos históricos sin detalle se consideran entrega total.
        """
        total = Decimal("0")
        for det in self.detalles or []:
            tipo = (det.tipo_item or "FABRICADO")
            ordenes = [
                o for o in (getattr(det, "ordenes", None) or [])
                if o.estado != "CANCELADA"
            ]
            if tipo in ("FABRICADO", "REPARACION") and ordenes:
                for orden in ordenes:
                    cantidad = orden.cantidad if orden.cantidad is not None else det.cantidad
                    total += Decimal(str(cantidad or 0))
            else:
                total += Decimal(str(det.cantidad or 0))

        entregado = Decimal("0")
        envios = list(self.envios or [])
        for envio in envios:
            if envio.estado != "ENTREGADO":
                continue
            if envio.detalles:
                for item in envio.detalles:
                    entregado += Decimal(str(item.cantidad or 0))
            else:
                # Envío previo a la entrega parcial: cubría todo el pedido.
                entregado = total
                break

        pendiente = max(Decimal("0"), total - entregado)
        if total > 0 and pendiente <= 0:
            estado = "COMPLETO"
        elif entregado > 0:
            estado = "PARCIAL"
        else:
            estado = "PENDIENTE"
        fechas = [
            e.fecha_entrega for e in envios
            if e.estado == "ENTREGADO" and e.fecha_entrega is not None
        ]
        return {
            "total": float(total),
            "entregado": float(entregado),
            "pendiente": float(pendiente),
            "estado": estado,
            "envios": len(envios),
            "ultima_entrega": max(fechas) if fechas else None,
        }

class DetallePedido(Base):
    __tablename__ = "detalle_pedido"

    id = Column(BigInteger, primary_key=True, index=True)
    pedido_id = Column(BigInteger, ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id"), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="RESTRICT"), nullable=True)
    tipo_item = Column(String(20), nullable=False, server_default="FABRICADO")  # FABRICADO | REVENTA | INSUMO
    cantidad = Column(Numeric(14, 4), nullable=False)
    precio = Column(Numeric(15, 2), nullable=False)
    # Captura flexible del insumo (se copia de la cotización): cantidad/precio
    # en la unidad vendida y `cantidad_base` en la unidad del inventario.
    unidad_captura = Column(String(4), nullable=True)  # 'M' | 'CM'
    cantidad_base = Column(Numeric(14, 4), nullable=True)
    # Snapshot de costos al convertir cotización → pedido
    costo_unitario = Column(Numeric(15, 2), nullable=True)
    porcentaje_ganancia = Column(Numeric(5, 2), nullable=True)
    alto = Column(Numeric(10, 2), nullable=True)
    ancho = Column(Numeric(10, 2), nullable=True)
    largo = Column(Numeric(10, 2), nullable=True)
    color = Column(String(100), nullable=True)
    acabado = Column(String(100), nullable=True)
    descripcion_especifica = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    # Promo obsequio: línea del plástico de regalo (precio 0, 1 por colchón)
    es_obsequio = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto")
    material = relationship("Material")
    # Órdenes de producción de este renglón: una normal, o N (una por pieza)
    # cuando el juego se abrió en piezas. La entrega parcial se apoya en ellas.
    ordenes = relationship("OrdenProduccion", back_populates="detalle_pedido")
    # Piezas del juego copiadas de la cotización. Cada una genera su propia
    # orden de producción; el renglón conserva el precio global.
    piezas = relationship(
        "DetallePedidoPieza",
        back_populates="detalle",
        cascade="all, delete-orphan",
        order_by="DetallePedidoPieza.orden",
    )


class DetallePedidoPieza(Base):
    """Pieza de un renglón-juego en el pedido (una orden de producción cada una)."""

    __tablename__ = "detalle_pedido_pieza"

    id = Column(BigInteger, primary_key=True, index=True)
    detalle_pedido_id = Column(
        BigInteger,
        ForeignKey("detalle_pedido.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre = Column(String(150), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False, server_default="1", default=1)
    notas = Column(Text, nullable=True)
    orden = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    detalle = relationship("DetallePedido", back_populates="piezas")
