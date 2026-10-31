"""Préstamos por cobrar: dinero que la empresa prestó y la persona debe.

Reglas de oro (decisión del dueño, 31/10/2026):
  * Solo se crean desde una SALIDA de caja clasificada como PRESTAMO. No hay
    pantalla aparte: Cuentas es el único lugar donde nace y se cobra.
  * Se cobran desde una ENTRADA de caja ("Cobro de préstamo"). El abono queda
    atado al movimiento de caja, así que borrar la entrada revierte el saldo.
  * No se revaloriza: el valor en COP del préstamo es el que se congeló al
    prestar. Así la deuda cierra exacta y no aparecen diferencias fantasma.
"""
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.modules.catalogos.model import Moneda
from app.modules.prestamos import model, schemas

CENTAVO = Decimal("0.01")
TOLERANCIA = Decimal("0.005")


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def normalizar_persona(nombre: Optional[str]) -> str:
    """Clave de agrupación: sin acentos, sin espacios de más, en mayúsculas.

    "Antonio  Ebanista" y "ANTONIO EBANISTA" son la misma persona para el
    selector, aunque el nombre que se muestra sea el que se escribió al prestar.
    """
    texto = " ".join((nombre or "").split())
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.upper()


# ---------------------------------------------------------------------------
# Alta (la llama reports.service al registrar una salida PRESTAMO)
# ---------------------------------------------------------------------------
def crear_prestamo(
    db: Session,
    *,
    persona_nombre: str,
    fecha: date,
    moneda_id: int,
    monto: Decimal,
    tasa_cambio: Decimal,
    metodo_caja_id: Optional[int],
    movimiento_caja_id: Optional[int],
    observaciones: Optional[str] = None,
    usuario_id: Optional[int] = None,
) -> model.Prestamo:
    """Crea el préstamo por cobrar. No hace commit (lo hace el llamador)."""
    nombre = " ".join((persona_nombre or "").split())
    if not nombre:
        raise ValueError("Indica la persona a la que le prestaste el dinero.")
    monto = _redondear(_d(monto))
    if monto <= 0:
        raise ValueError("El monto del préstamo debe ser mayor que cero.")
    tasa = _d(tasa_cambio) or Decimal("1.0")

    prestamo = model.Prestamo(
        persona_nombre=nombre[:150],
        fecha=fecha,
        moneda_id=moneda_id,
        monto=monto,
        tasa_cambio=tasa,
        monto_en_moneda_base=_redondear(monto * tasa),
        monto_abonado=Decimal("0"),
        estado="PENDIENTE",
        metodo_caja_id=metodo_caja_id,
        movimiento_caja_id=movimiento_caja_id,
        observaciones=observaciones,
        creado_por_id=usuario_id,
    )
    db.add(prestamo)
    db.flush()
    return prestamo


# ---------------------------------------------------------------------------
# Cobro (lo llama reports.service al registrar una ENTRADA "Cobro de préstamo")
# ---------------------------------------------------------------------------
@dataclass
class PlanCobro:
    persona_nombre: str
    moneda_id: int
    monto: Decimal
    aplicaciones: List[Tuple[model.Prestamo, Decimal]] = field(default_factory=list)

    @property
    def monto_base(self) -> Decimal:
        """Valor en COP a la tasa congelada de cada préstamo."""
        return _redondear(
            sum((monto * _d(p.tasa_cambio) for p, monto in self.aplicaciones), Decimal("0"))
        )


def planificar_cobro(
    db: Session,
    *,
    persona_nombre: str,
    moneda_id: int,
    monto: Decimal,
) -> PlanCobro:
    """Valida y reparte el cobro entre los préstamos pendientes de la persona.

    Aplica del más antiguo al más nuevo (FIFO). No escribe nada: el llamador
    crea primero el movimiento de caja y después registra los abonos, para que
    todo quede en una sola transacción.
    """
    nombre = " ".join((persona_nombre or "").split())
    if not nombre:
        raise ValueError("Indica a quién se le cobra el préstamo.")
    monto = _redondear(_d(monto))
    if monto <= 0:
        raise ValueError("El monto a cobrar debe ser mayor que cero.")

    clave = normalizar_persona(nombre)
    pendientes = (
        db.query(model.Prestamo)
        .filter(
            model.Prestamo.estado == "PENDIENTE",
            model.Prestamo.moneda_id == moneda_id,
        )
        .order_by(model.Prestamo.fecha.asc(), model.Prestamo.id.asc())
        .all()
    )
    propios = [p for p in pendientes if normalizar_persona(p.persona_nombre) == clave]
    saldo = _redondear(sum((p.saldo for p in propios), Decimal("0")))
    if not propios or saldo <= 0:
        raise ValueError(f"{nombre} no tiene préstamos pendientes en esa moneda.")
    if monto > saldo + TOLERANCIA:
        raise ValueError(
            f"El cobro excede lo que debe {nombre}: saldo pendiente {saldo}."
        )

    plan = PlanCobro(
        persona_nombre=propios[0].persona_nombre if propios else nombre,
        moneda_id=moneda_id,
        monto=monto,
    )
    restante = monto
    for prestamo in propios:
        if restante <= 0:
            break
        aplicar = min(restante, prestamo.saldo)
        if aplicar <= 0:
            continue
        plan.aplicaciones.append((prestamo, aplicar))
        restante -= aplicar
    if not plan.aplicaciones:
        raise ValueError(f"{nombre} no tiene saldo pendiente que cobrar.")
    return plan


def registrar_cobro(
    db: Session,
    plan: PlanCobro,
    *,
    movimiento,
    moneda_cuenta_id: int,
    tasa_conversion: Decimal,
    usuario_id: Optional[int] = None,
) -> List[model.PagoPrestamo]:
    """Crea los abonos y actualiza el saldo de cada préstamo. Sin commit."""
    tasa = _d(tasa_conversion) or Decimal("1.0")
    pagos: List[model.PagoPrestamo] = []
    for prestamo, monto in plan.aplicaciones:
        monto = _redondear(monto)
        pago = model.PagoPrestamo(
            prestamo_id=prestamo.id,
            fecha=movimiento.fecha,
            monto=monto,
            metodo_caja_id=movimiento.metodo_caja_id,
            moneda_cuenta_id=moneda_cuenta_id,
            tasa_conversion=tasa,
            monto_en_moneda_cuenta=_redondear(monto * tasa),
            monto_en_moneda_base=_redondear(monto * _d(prestamo.tasa_cambio)),
            movimiento_caja_id=movimiento.id,
            creado_por_id=usuario_id,
        )
        db.add(pago)
        prestamo.monto_abonado = _redondear(_d(prestamo.monto_abonado) + monto)
        if prestamo.saldo <= TOLERANCIA:
            prestamo.estado = "PAGADO"
        pagos.append(pago)
    db.flush()
    return pagos


# ---------------------------------------------------------------------------
# Reversas (las llama reports.service al editar/eliminar el movimiento)
# ---------------------------------------------------------------------------
def pagos_de_movimiento(db: Session, movimiento_caja_id: int) -> List[model.PagoPrestamo]:
    return (
        db.query(model.PagoPrestamo)
        .filter(model.PagoPrestamo.movimiento_caja_id == movimiento_caja_id)
        .all()
    )


def pagos_de_prestamo(db: Session, prestamo_id: int) -> int:
    return int(
        db.query(func.count(model.PagoPrestamo.id))
        .filter(model.PagoPrestamo.prestamo_id == prestamo_id)
        .scalar()
        or 0
    )


def revertir_cobros_de_movimiento(db: Session, movimiento_caja_id: int) -> int:
    """Devuelve el saldo al préstamo y borra los abonos de esa entrada.

    Devuelve cuántos abonos se revirtieron. Sin commit.
    """
    pagos = pagos_de_movimiento(db, movimiento_caja_id)
    for pago in pagos:
        prestamo = (
            db.query(model.Prestamo)
            .filter(model.Prestamo.id == pago.prestamo_id)
            .with_for_update()
            .first()
        )
        if prestamo is not None:
            prestamo.monto_abonado = _redondear(
                _d(prestamo.monto_abonado) - _d(pago.monto)
            )
            if prestamo.monto_abonado < 0:
                prestamo.monto_abonado = Decimal("0")
            prestamo.estado = "PAGADO" if prestamo.saldo <= TOLERANCIA else "PENDIENTE"
        db.delete(pago)
    if pagos:
        db.flush()
    return len(pagos)


def prestamo_de_movimiento(db: Session, movimiento_caja_id: int) -> Optional[model.Prestamo]:
    """Préstamo que nació de esa salida de caja (si la hay)."""
    return (
        db.query(model.Prestamo)
        .filter(model.Prestamo.movimiento_caja_id == movimiento_caja_id)
        .first()
    )


def eliminar_prestamo_de_movimiento(db: Session, movimiento_caja_id: int) -> bool:
    """Borra el préstamo creado por esa salida. Falla si ya tiene cobros.

    Sin commit. Devuelve True si borró algo.
    """
    prestamo = prestamo_de_movimiento(db, movimiento_caja_id)
    if prestamo is None:
        return False
    if _d(prestamo.monto_abonado) > 0:
        raise ValueError(
            f"Este préstamo ya tiene cobros registrados ({prestamo.persona_nombre}). "
            "Elimina primero las entradas de cobro."
        )
    db.delete(prestamo)
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Consultas (API)
# ---------------------------------------------------------------------------
def listar_prestamos(
    db: Session,
    *,
    estado: Optional[str] = None,
    persona: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> List[model.Prestamo]:
    query = db.query(model.Prestamo).options(
        joinedload(model.Prestamo.moneda),
        joinedload(model.Prestamo.pagos).joinedload(model.PagoPrestamo.metodo_caja),
        joinedload(model.Prestamo.pagos).joinedload(model.PagoPrestamo.moneda_cuenta),
    )
    if estado:
        query = query.filter(model.Prestamo.estado == estado.upper())
    if fecha_desde:
        query = query.filter(model.Prestamo.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(model.Prestamo.fecha <= fecha_hasta)
    # Pendientes primero; dentro de cada grupo, los más recientes arriba.
    orden_estado = case((model.Prestamo.estado == "PENDIENTE", 0), else_=1)
    prestamos = query.order_by(
        orden_estado, model.Prestamo.fecha.desc(), model.Prestamo.id.desc()
    ).all()
    if persona:
        clave = normalizar_persona(persona)
        prestamos = [p for p in prestamos if clave in normalizar_persona(p.persona_nombre)]
    return prestamos


def pendientes(db: Session) -> List[schemas.PendientePrestamo]:
    """Deudores con saldo, agrupados por persona + moneda (para el selector)."""
    filas = (
        db.query(model.Prestamo)
        .options(joinedload(model.Prestamo.moneda))
        .filter(model.Prestamo.estado == "PENDIENTE")
        .order_by(model.Prestamo.fecha.asc(), model.Prestamo.id.asc())
        .all()
    )
    agrupado: dict[tuple[str, int], schemas.PendientePrestamo] = {}
    for prestamo in filas:
        clave = (normalizar_persona(prestamo.persona_nombre), prestamo.moneda_id)
        actual = agrupado.get(clave)
        if actual is None:
            actual = schemas.PendientePrestamo(
                persona_nombre=prestamo.persona_nombre,
                moneda_id=prestamo.moneda_id,
                moneda_codigo=prestamo.moneda.codigo if prestamo.moneda else "COP",
                moneda_simbolo=prestamo.moneda.simbolo if prestamo.moneda else None,
                saldo=Decimal("0"),
                prestamos=0,
                ultima_fecha=prestamo.fecha,
            )
            agrupado[clave] = actual
        actual.saldo = _redondear(actual.saldo + prestamo.saldo)
        actual.prestamos += 1
        if prestamo.fecha and (actual.ultima_fecha is None or prestamo.fecha > actual.ultima_fecha):
            actual.ultima_fecha = prestamo.fecha
    # Los que más deben primero: es lo que ella busca al abrir el selector.
    return sorted(agrupado.values(), key=lambda p: p.saldo, reverse=True)


def resumen(db: Session) -> schemas.ResumenPrestamos:
    pendientes_por_persona = pendientes(db)
    filas = (
        db.query(
            model.Prestamo.moneda_id,
            func.coalesce(func.sum(model.Prestamo.monto), 0),
            func.coalesce(func.sum(model.Prestamo.monto_abonado), 0),
        )
        .group_by(model.Prestamo.moneda_id)
        .all()
    )
    monedas = {
        m.id: m
        for m in db.query(Moneda)
        .filter(Moneda.id.in_([f[0] for f in filas] or [0]))
        .all()
    }
    por_moneda = []
    for moneda_id, prestado, cobrado in filas:
        moneda = monedas.get(moneda_id)
        por_moneda.append(
            schemas.TotalPrestamosMoneda(
                moneda_id=moneda_id,
                moneda_codigo=moneda.codigo if moneda else "COP",
                moneda_simbolo=moneda.simbolo if moneda else None,
                total_prestado=_redondear(_d(prestado)),
                total_cobrado=_redondear(_d(cobrado)),
                saldo=_redondear(_d(prestado) - _d(cobrado)),
            )
        )
    return schemas.ResumenPrestamos(
        personas_con_saldo=len(pendientes_por_persona),
        por_moneda=por_moneda,
        por_persona=pendientes_por_persona,
    )
