from decimal import Decimal

from sqlalchemy import Column, DateTime, Date, Text, BigInteger, Numeric, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Prestamo(Base):
    """Dinero que la empresa prestó a una persona y queda por cobrar.

    Nace SOLO desde una salida de caja clasificada como PRESTAMO (el movimiento
    de caja es la otra cara del asiento). Se cobra desde Cuentas → Entrada →
    "Cobro de préstamo", que crea un `PagoPrestamo` atado a su movimiento de
    caja: si el movimiento se elimina, el saldo se revierte solo.

    No es un gasto nuevo: el egreso (y su Gasto) ya existe desde que se prestó.
    """

    __tablename__ = "prestamo"

    id = Column(BigInteger, primary_key=True, index=True)
    # Quién recibió el dinero (texto libre: familiar, empleado, cliente...).
    persona_nombre = Column(String(150), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    moneda_id = Column(BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False)
    # Monto prestado en la moneda del préstamo.
    monto = Column(Numeric(15, 2), nullable=False)
    # Tasa "1 [moneda] = X COP" congelada al prestar (la misma del movimiento).
    tasa_cambio = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False, default=0.0)
    # Total cobrado, en la moneda del préstamo.
    monto_abonado = Column(Numeric(15, 2), nullable=False, default=0.0)
    estado = Column(String(20), nullable=False, default="PENDIENTE", index=True)  # PENDIENTE | PAGADO

    metodo_caja_id = Column(
        BigInteger, ForeignKey("metodo_caja.id", ondelete="SET NULL"), nullable=True
    )
    # Salida de caja que originó el préstamo (asiento espejo).
    movimiento_caja_id = Column(
        BigInteger, ForeignKey("movimiento_caja.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    observaciones = Column(Text, nullable=True)
    creado_por_id = Column(
        BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    moneda = relationship("Moneda")
    metodo_caja = relationship("MetodoCaja")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])
    pagos = relationship(
        "PagoPrestamo",
        back_populates="prestamo",
        cascade="all, delete-orphan",
        order_by="PagoPrestamo.fecha, PagoPrestamo.id",
    )

    @property
    def saldo(self) -> Decimal:
        return (
            Decimal(str(self.monto)) - Decimal(str(self.monto_abonado))
        ).quantize(Decimal("0.01"))

    @property
    def creador_nombre(self):
        return (self.creador.display_name or self.creador.nombre_usuario) if self.creador else None


class PagoPrestamo(Base):
    """Cobro (total o parcial) de un préstamo. Entra a una cuenta de caja.

    `monto` vive en la moneda del préstamo; `monto_en_moneda_cuenta` es lo que
    realmente entró a la cuenta cuando las monedas difieren.
    """

    __tablename__ = "pago_prestamo"

    id = Column(BigInteger, primary_key=True, index=True)
    prestamo_id = Column(
        BigInteger, ForeignKey("prestamo.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    fecha = Column(Date, nullable=False)
    # Monto cobrado EN LA MONEDA DEL PRÉSTAMO.
    monto = Column(Numeric(15, 2), nullable=False)
    metodo_caja_id = Column(
        BigInteger, ForeignKey("metodo_caja.id", ondelete="RESTRICT"), nullable=False
    )
    # Moneda de la cuenta donde entró el dinero.
    moneda_cuenta_id = Column(
        BigInteger, ForeignKey("moneda.id", ondelete="RESTRICT"), nullable=False
    )
    # "1 [moneda del préstamo] = X [moneda de la cuenta]".
    tasa_conversion = Column(Numeric(15, 6), nullable=False, default=1.0)
    monto_en_moneda_cuenta = Column(Numeric(15, 2), nullable=False, default=0.0)
    # Valor en COP (a la tasa congelada del préstamo) para los reportes.
    monto_en_moneda_base = Column(Numeric(15, 2), nullable=False, default=0.0)
    # Entrada de caja que materializó el cobro (se revierte con ella).
    movimiento_caja_id = Column(
        BigInteger, ForeignKey("movimiento_caja.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    creado_por_id = Column(
        BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, server_default=func.now())

    prestamo = relationship("Prestamo", back_populates="pagos")
    metodo_caja = relationship("MetodoCaja")
    moneda_cuenta = relationship("Moneda")
    creador = relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def metodo_caja_nombre(self):
        return self.metodo_caja.nombre if self.metodo_caja else None

    @property
    def moneda_cuenta_codigo(self):
        return self.moneda_cuenta.codigo if self.moneda_cuenta else None

    @property
    def creador_nombre(self):
        return (self.creador.display_name or self.creador.nombre_usuario) if self.creador else None
