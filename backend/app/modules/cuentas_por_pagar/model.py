from decimal import Decimal

from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Integer, Numeric, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class CuentaPorPagar(Base):
    """Deuda con un proveedor ("fiar"): compras de inventario sin pagar o
    deudas registradas a mano. Se abona de a poco; cada abono sale de una
    cuenta de caja. El gasto asociado (P&L) se registra al crearse la deuda,
    para no duplicar egresos cuando se abona."""

    __tablename__ = "cuenta_por_pagar"

    id = Column(BigInteger, primary_key=True, index=True)
    proveedor_id = Column(BigInteger, ForeignKey("proveedor.id"), nullable=False)
    # El egreso al que da origen la deuda (P&L). Se crea sin tocar caja.
    gasto_id = Column(BigInteger, ForeignKey("gasto.id", ondelete="SET NULL"), nullable=True, index=True)
    tipo_gasto_id = Column(BigInteger, ForeignKey("tipo_gasto.id", ondelete="RESTRICT"), nullable=False)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    fecha = Column(Date, nullable=False)
    descripcion = Column(Text, nullable=True)
    monto = Column(Numeric(15, 2), nullable=False)
    # Tasa "1 [moneda] = X COP" congelada al crear la deuda.
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False, default=0.0)
    # Total abonado en efectivo, en la moneda de la deuda (sin descuentos).
    monto_pagado = Column(Numeric(15, 2), nullable=False, default=0.0)
    # Total condonado/descontado por el proveedor, en la moneda de la deuda.
    # Cierra deuda sin mover caja y NO altera el gasto original (el costo
    # del ítem sigue siendo el precio de compra).
    monto_descontado = Column(Numeric(15, 2), nullable=False, default=0.0)
    estado = Column(String(20), nullable=False, default="PENDIENTE", index=True)  # PENDIENTE | PAGADA
    # De dónde nació la deuda: MANUAL (registrada a mano) | ENTRADA_INVENTARIO (fiar).
    origen_tipo = Column(String(30), nullable=True)
    origen_id = Column(BigInteger, nullable=True)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    proveedor = relationship("Proveedor")
    gasto = relationship("Gasto")
    tipo_gasto = relationship("TipoGasto")
    moneda = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self) -> str | None:
        return self.creador.display_name if self.creador else None
    detalles = relationship("DetalleCuentaPorPagar", back_populates="cuenta_por_pagar",
                             cascade="all, delete-orphan", order_by="DetalleCuentaPorPagar.orden")
    pagos = relationship("PagoCuentaPorPagar", back_populates="cuenta_por_pagar", cascade="all, delete-orphan")

    @property
    def saldo(self) -> Decimal:
        return (
            Decimal(str(self.monto))
            - Decimal(str(self.monto_pagado))
            - Decimal(str(self.monto_descontado))
        ).quantize(Decimal("0.01"))


class DetalleCuentaPorPagar(Base):
    """Renglón de una deuda: qué se compró, cuánto, a cuánto, y para quién.

    Permite que una cuenta por pagar muestre el detalle de "qué cosas hacen
    que uno deba lo que debe" (la hoja de control del proveedor): cada fila
    es un ítem con cantidad, descripción, precio unitario y cliente/obra
    destino. El `monto` de la cabecera es la suma de los renglones."""
    __tablename__ = "detalle_cuenta_por_pagar"

    id = Column(BigInteger, primary_key=True, index=True)
    cuenta_por_pagar_id = Column(BigInteger, ForeignKey("cuenta_por_pagar.id", ondelete="CASCADE"), nullable=False, index=True)
    # Orden de visualización dentro de la deuda (renglón 1, 2, 3...)
    orden = Column(Integer, nullable=False, default=0)
    # Ítem: descripción libre (p. ej. "SOPOLI 90", "TORNILLOS 1\"X 6") o material del catálogo.
    descripcion = Column(String(250), nullable=True)
    material_id = Column(BigInteger, ForeignKey("material.id", ondelete="SET NULL"), nullable=True)
    cantidad = Column(Numeric(12, 2), nullable=False, default=1)
    precio_unitario = Column(Numeric(15, 2), nullable=False, default=0)
    # Para quién se compró (cliente/obra). Texto libre: en la hoja de control
    # son destinos como "FABRICA", "DEPOSITO", "NOCHEROS", "CAMA COMANDANTE".
    cliente_nombre = Column(String(150), nullable=True)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id", ondelete="SET NULL"), nullable=True)
    # Comprobante/nota adicional de la línea (p. ej. "entró el 20/05")
    observaciones = Column(Text, nullable=True)

    cuenta_por_pagar = relationship("CuentaPorPagar", back_populates="detalles")
    material = relationship("Material")
    cliente = relationship("Client")

    @property
    def total(self) -> Decimal:
        return (Decimal(str(self.cantidad)) * Decimal(str(self.precio_unitario))).quantize(Decimal("0.01"))


class PagoCuentaPorPagar(Base):
    """Abono a una deuda: el dinero sale de una cuenta de caja.

    Puede llevar descuento del proveedor (ej. 5% por mayorista): `monto` es lo
    que salió de caja y `descuento` lo condonado; ambos juntos bajan la deuda.
    """

    __tablename__ = "pago_cuenta_por_pagar"

    id = Column(BigInteger, primary_key=True, index=True)
    cuenta_por_pagar_id = Column(BigInteger, ForeignKey("cuenta_por_pagar.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha = Column(Date, nullable=False)
    metodo_caja_id = Column(BigInteger, ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=False)
    # Dinero que SALE de caja, en la moneda de la deuda (neto de descuento).
    monto = Column(Numeric(15, 2), nullable=False)
    # Parte del abono que el proveedor condonó (moneda de la deuda). Se suma
    # al monto para saber cuánto bajó la deuda: monto + descuento.
    descuento = Column(Numeric(15, 2), nullable=False, default=0.0, server_default="0")
    # Porcentaje con que se calculó el descuento (solo para mostrarlo).
    descuento_porcentaje = Column(Numeric(7, 4), nullable=True)
    # Tasa "1 [moneda de la cuenta] = X COP" usada en la salida de caja.
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False, default=0.0)
    creado_por_id = Column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())

    cuenta_por_pagar = relationship("CuentaPorPagar", back_populates="pagos")
    metodo_caja = relationship("MetodoCaja")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def creador_nombre(self) -> str | None:
        return self.creador.display_name if self.creador else None

    @property
    def metodo_caja_nombre(self) -> str | None:
        return self.metodo_caja.nombre if self.metodo_caja else None

    @property
    def metodo_caja_moneda_codigo(self) -> str | None:
        return self.metodo_caja.moneda_codigo if self.metodo_caja else None

    @property
    def monto_aplicado(self) -> Decimal:
        """Cuánto bajó la deuda con este abono: efectivo + descuento."""
        return (
            Decimal(str(self.monto)) + Decimal(str(self.descuento or 0))
        ).quantize(Decimal("0.01"))
