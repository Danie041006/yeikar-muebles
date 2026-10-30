"""Importación del libro de caja EFECTIVO (texto pegado desde Excel).

Formato típico del libro:

    FECHA       TIPO                 CONCEPTO                  INGRESO    EGRESO      SALDO
    10/1/2026   SALDO                MES DE SEPTIEMBRE                                3,683,600
    10/1/2026   DOÑA ROSA  G C       PAGO DE MERCADO           120,000              2,313,600
    10/1/2026   CAMARA ... G F       PAGO DE LUZ                          400,000    1,913,600

Reglas de la importación:

- La fecha viene en formato D/M/AÑO.
- La fila de SALDO inicial es el punto de partida, no un movimiento: sirve
  para validar que la cuenta ya tenía ese saldo antes del período.
- El signo de cada fila sale del cambio de saldo (saldo actual − anterior).
  Así el libro cuadra siempre, aunque la columna de ingreso/egreso venga
  corrida o el monto esté tecleado distinto; esas diferencias se avisan.
- Si el TIPO trae G D / G C / G P / G F / G I, el egreso se crea además como
  Gasto con su clasificación explícita (Gasto Deducible, de Casa, Personal,
  Familiar, Gastos de Fábrica/Camiones o de Inversión). El campo es opcional:
  las filas sin código se
  importan solo como movimiento de caja. La clasificación "Préstamo" existe
  además para las salidas registradas a mano desde Cuentas.
- El libro va en la MONEDA de la cuenta elegida (no solo COP): cada
  movimiento y gasto queda con la tasa del día hacia la moneda base
  (obtener_tasa_moneda_a_cop; 1.0 para COP o cuando nunca se registró tasa).
- Si se pide "cuadrar saldo inicial", el ajuste por la diferencia se fecha el
  ÚLTIMO DÍA DEL MES ANTERIOR: es el saldo que venía del período previo, no un
  ingreso del mes. Así la tarjeta "Saldo inicial (antes del período)" muestra
  el saldo del libro y el saldo final queda igual.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.caja import registrar_movimiento_caja
from app.core.hora_ve import hoy_ve
from app.modules.auditoria.service import record_event
from app.modules.catalogos.model import Moneda, TipoGasto
from app.modules.gastos import schemas as gastos_schemas
from app.modules.gastos import service as gastos_service
from app.modules.gastos.model import Gasto
from app.modules.reports.model import MetodoCaja, MovimientoCaja
from app.modules.tasas_cambio.service import (
    obtener_tasa_moneda_a_cop,
    obtener_ultima_tasa,
)
from app.modules.users.model import Usuario

# Código del libro → clave canónica del gasto. Además de las letras
# (G D, G C, G P, G F, G I), el libro de la dueña puede traer la palabra
# completa: "G CAMIONES" y "G FABRICA" son las clasificaciones nuevas.
CLASIFICACION_POR_CODIGO = {
    "D": "GASTO_DEDUCIBLE",
    "C": "GASTO_CASA",
    "P": "GASTO_PERSONAL",
    "F": "GASTO_FAMILIAR",
    "I": "GASTO_INVERSION",
    "CAMION": "GASTO_CAMIONES",
    "CAMIONES": "GASTO_CAMIONES",
    "FABRICA": "GASTO_FABRICA",
}

_FECHA_RE = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
# Solo tomamos montos con símbolo $: en este libro TODAS las columnas de
# dinero lo llevan, y así no confundimos los números que aparecen dentro del
# concepto (tasas, "500 MIL", teléfonos, etc.).
_TOKEN_RE = re.compile(r"\$\s*\d[\d.,]*")
_CLASIF_RE = re.compile(r"\bG\s*(CAMIONES?|FABRICA|[DCPFI])\b", re.IGNORECASE)
_CERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------
@dataclass
class FilaLibro:
    linea: int
    fecha: date
    tipo: str
    concepto: str
    ingreso: Decimal = _CERO
    egreso: Decimal = _CERO
    saldo: Decimal = _CERO
    saldo_anterior: Optional[Decimal] = None
    clasificacion: Optional[str] = None
    codigo: Optional[str] = None
    es_saldo_inicial: bool = False
    duplicado_de: Optional[str] = None
    advertencias: list[str] = field(default_factory=list)

    @property
    def es_duplicado(self) -> bool:
        return bool(self.duplicado_de)

    @property
    def delta(self) -> Decimal:
        return self.ingreso - self.egreso

    @property
    def descripcion(self) -> str:
        partes = [p for p in (self.tipo.strip(), self.concepto.strip()) if p]
        # Si el pegado colapsó las columnas, tipo == concepto: no duplicar.
        if len(partes) == 2 and partes[0].casefold() == partes[1].casefold():
            partes = partes[:1]
        return " · ".join(partes)[:900]


@dataclass
class LibroParseado:
    filas: list[FilaLibro] = field(default_factory=list)
    omitidas: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    saldo_inicial: Optional[Decimal] = None
    saldo_final: Optional[Decimal] = None
    total_ingresos: Decimal = _CERO
    total_egresos: Decimal = _CERO
    totales_declarados: Optional[tuple[Decimal, Decimal, Decimal]] = None

    @property
    def periodo(self) -> Optional[str]:
        fechas = [f.fecha for f in self.filas if not f.es_saldo_inicial]
        if not fechas:
            return None
        return f"{fechas[0].year:04d}-{fechas[0].month:02d}"

    @property
    def movimientos(self) -> int:
        return sum(1 for f in self.filas if not f.es_saldo_inicial and f.delta != 0)

    @property
    def gastos(self) -> int:
        return sum(
            1 for f in self.filas
            if not f.es_saldo_inicial and f.egreso > 0 and f.clasificacion
        )


def _parse_monto(token: str) -> Optional[Decimal]:
    """Convierte '$ 1.250.000' / '$ 1,250,000' / '$ 1250000.00' a Decimal."""
    s = token.replace("$", "").replace("\u00a0", "").strip()
    if not s:
        return None
    negativo = s.startswith("-")
    s = s.lstrip("+-").strip().rstrip(".,")
    if not re.search(r"\d", s):
        return None
    # Detectar separador decimal: si el último grupo tiene 1-2 dígitos y hay
    # más de un separador (o el entero no es de 3 dígitos exactos).
    if "." in s or "," in s:
        ultimo = max(s.rfind("."), s.rfind(","))
        cola = s[ultimo + 1:]
        if len(cola) in (1, 2):
            entero = re.sub(r"[.,]", "", s[:ultimo])
            s = f"{entero}.{cola}"
        else:
            s = re.sub(r"[.,]", "", s)
    try:
        valor = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return -valor if negativo else valor


def _parse_fecha(
    match: re.Match, anio_base: int, periodo: Optional[tuple[int, int]] = None
) -> Optional[date]:
    dia, mes, anio = (int(g) for g in match.groups())
    if anio < 100:
        anio += 2000
    # Años truncados por el Excel/pegado ("202", "226"): se ancla al año del
    # período. El libro es mensual, así que no hay ambigüedad real.
    if abs(anio - anio_base) > 50:
        anio = anio_base
    # El libro mezcla D/M (1/10/2026) y M/D (10/1/2026). Se generan las dos
    # lecturas válidas y se elige la que cae en el mes del período; si ambas
    # caen en el mes (día == mes), da igual.
    candidatos: list[date] = []
    for d, m in ((dia, mes), (mes, dia)):
        try:
            candidatos.append(date(anio, m, d))
        except ValueError:
            continue
    if not candidatos:
        return None
    if periodo is not None:
        for candidato in candidatos:
            if (candidato.year, candidato.month) == periodo:
                return candidato
    # Sin período conocido: se prefiere D/M (formato habitual en Colombia).
    return candidatos[0]


def _anio_base(texto: str) -> int:
    anios = [int(a) for a in re.findall(r"\b(20\d{2})\b", texto)]
    if not anios:
        return date.today().year
    return Counter(anios).most_common(1)[0][0]


def _periodo_objetivo(texto: str, anio_base: int) -> Optional[tuple[int, int]]:
    """Mes/año dominante del libro, para desambiguar las fechas D/M vs M/D."""
    conteo: Counter = Counter()
    for linea in texto.splitlines():
        match = _FECHA_RE.match(linea)
        if not match:
            continue
        dia, mes, anio = (int(g) for g in match.groups())
        if anio < 100:
            anio += 2000
        if abs(anio - anio_base) > 50:
            anio = anio_base
        for d, m in ((dia, mes), (mes, dia)):
            if 1 <= m <= 12 and 1 <= d <= 31:
                try:
                    fecha = date(anio, m, d)
                except ValueError:
                    continue
                conteo[(fecha.year, fecha.month)] += 1
    if not conteo:
        return None
    return conteo.most_common(1)[0][0]


def _partir_tipo_concepto(medio: str) -> tuple[str, str]:
    """Separa la columna TIPO del CONCEPTO usando los tabuladores del pegado.

    Si el texto viene con espacios (sin celdas), se conserva entero como
    concepto para no inventar una división.
    """
    if "\t" in medio:
        partes = [p.strip() for p in medio.split("\t") if p.strip()]
        if partes:
            return partes[0], " ".join(partes[1:]) if len(partes) > 1 else ""
    limpio = re.sub(r"\s+", " ", medio).strip()
    return "", limpio


def _parse_linea(
    linea: str,
    numero: int,
    anio_base: int,
    periodo: Optional[tuple[int, int]] = None,
) -> Optional[dict]:
    """Devuelve una fila cruda, una omisión o None (encabezado/blanco)."""
    match = _FECHA_RE.match(linea)
    if not match:
        return None
    fecha = _parse_fecha(match, anio_base, periodo)
    if fecha is None:
        return {
            "tipo_resultado": "error",
            "linea": numero,
            "error": f"Fecha inválida en la línea {numero}: {linea.strip()[:80]}",
        }

    tokens = list(_TOKEN_RE.finditer(linea))
    if not tokens:
        return {
            "tipo_resultado": "omitida",
            "linea": numero,
            "texto": re.sub(r"\s+", " ", linea).strip()[:200],
            "motivo": "sin montos en la fila (nota o gasto pagado fuera de caja)",
        }

    ultimo = tokens[-1]
    # El saldo debe cerrar la línea; si después hay texto ("... pesos"), la
    # fila es una nota y no un movimiento con saldo.
    if linea[ultimo.end():].strip():
        return {
            "tipo_resultado": "omitida",
            "linea": numero,
            "texto": re.sub(r"\s+", " ", linea).strip()[:200],
            "motivo": "los montos no están al final de la fila (parece una nota)",
        }

    # Recoger los montos contiguos del final (separados solo por espacios o
    # tabuladores). Normalmente son 2: monto + saldo. Si hay 3, la fila trae
    # ingreso y egreso en columnas separadas.
    corrida = [ultimo]
    for token in reversed(tokens[:-1]):
        if linea[token.end():corrida[0].start()].strip():
            break
        corrida.insert(0, token)
        if len(corrida) == 3:
            break

    saldo = _parse_monto(corrida[-1].group())
    if saldo is None:
        return {
            "tipo_resultado": "error",
            "linea": numero,
            "error": f"No se pudo leer el saldo de la línea {numero}.",
        }

    ingreso_declarado = egreso_declarado = None
    monto_declarado = None
    if len(corrida) >= 3:
        ingreso_declarado = _parse_monto(corrida[-3].group()) or _CERO
        egreso_declarado = _parse_monto(corrida[-2].group()) or _CERO
        monto_declarado = max(ingreso_declarado, egreso_declarado)
    elif len(corrida) == 2:
        monto_declarado = _parse_monto(corrida[-2].group())

    medio = linea[match.end():corrida[0].start()]
    tipo, concepto = _partir_tipo_concepto(medio)
    texto_clasif = f"{tipo} {concepto}"
    clasif_match = _CLASIF_RE.search(texto_clasif)
    codigo = clasif_match.group(1).upper() if clasif_match else None

    return {
        "tipo_resultado": "fila",
        "linea": numero,
        "fecha": fecha,
        "tipo": tipo,
        "concepto": concepto,
        "saldo": saldo,
        "ingreso_declarado": ingreso_declarado,
        "egreso_declarado": egreso_declarado,
        "monto_declarado": monto_declarado,
        "codigo": codigo,
        "clasificacion": CLASIFICACION_POR_CODIGO.get(codigo) if codigo else None,
        "numeros": len(corrida),
    }


def parsear_libro(texto: str) -> LibroParseado:
    """Parsea el texto pegado y calcula ingresos/egresos desde el saldo."""
    resultado = LibroParseado()
    if not texto or not texto.strip():
        resultado.errores.append("Pega el libro de caja antes de continuar.")
        return resultado

    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    anio_base = _anio_base(texto)
    periodo_objetivo = _periodo_objetivo(texto, anio_base)
    saldo_anterior: Optional[Decimal] = None

    for numero, linea in enumerate(lineas, start=1):
        if not linea.strip():
            continue
        crudo = _parse_linea(linea, numero, anio_base, periodo_objetivo)
        if crudo is None:
            # Posible fila de totales (sin fecha y con 3 montos): se usa para
            # contrastar los totales del libro.
            tokens = list(_TOKEN_RE.finditer(linea))
            if len(tokens) >= 3:
                montos = [_parse_monto(t.group()) for t in tokens[-3:]]
                if all(m is not None for m in montos):
                    resultado.totales_declarados = tuple(montos)  # type: ignore[assignment]
            continue
        if crudo["tipo_resultado"] == "error":
            resultado.errores.append(crudo["error"])
            continue
        if crudo["tipo_resultado"] == "omitida":
            resultado.omitidas.append({
                "linea": crudo["linea"],
                "texto": crudo["texto"],
                "motivo": crudo["motivo"],
            })
            continue

        saldo = crudo["saldo"]
        if saldo_anterior is None:
            if crudo["numeros"] == 1 and not crudo["ingreso_declarado"] and not crudo["monto_declarado"]:
                # Primera fila del libro: SALDO con el que arranca el mes.
                fila = FilaLibro(
                    linea=numero,
                    fecha=crudo["fecha"],
                    tipo=crudo["tipo"],
                    concepto=crudo["concepto"],
                    saldo=saldo,
                    es_saldo_inicial=True,
                )
                resultado.saldo_inicial = saldo
                resultado.filas.append(fila)
                saldo_anterior = saldo
                continue
            # Primera fila con movimiento y sin saldo previo: el saldo inicial
            # se deduce del propio movimiento.
            saldo_anterior = _CERO
            resultado.saldo_inicial = _CERO

        delta = saldo - saldo_anterior
        advertencias: list[str] = []
        ingreso = _CERO
        egreso = _CERO

        if crudo["numeros"] >= 3:
            ingreso = crudo["ingreso_declarado"] or _CERO
            egreso = crudo["egreso_declarado"] or _CERO
            if (ingreso - egreso) != delta:
                advertencias.append(
                    f"El saldo cambia {delta:,.2f} pero la fila declara "
                    f"{ingreso - egreso:,.2f}; se usa el cambio de saldo."
                )
                if delta > 0:
                    ingreso, egreso = delta, _CERO
                elif delta < 0:
                    ingreso, egreso = _CERO, -delta
                else:
                    ingreso = egreso = _CERO
        elif delta > 0:
            ingreso = delta
        elif delta < 0:
            egreso = -delta
        else:
            monto = crudo["monto_declarado"] or _CERO
            if monto > 0:
                advertencias.append(
                    "La fila dice un monto pero el saldo no cambia: no se "
                    "puede saber si fue ingreso o egreso."
                )
                resultado.errores.append(
                    f"Línea {numero}: el saldo no cambia pero hay un monto de "
                    f"{monto:,.2f}. Corrige el saldo de esa fila."
                )

        monto_declarado = crudo["monto_declarado"]
        if monto_declarado is not None and abs(abs(delta) - monto_declarado) > Decimal("0.50"):
            advertencias.append(
                f"La fila dice {monto_declarado:,.2f} y el saldo cambia "
                f"{abs(delta):,.2f}; se usa el saldo para que el libro cuadre."
            )

        if crudo["clasificacion"] and ingreso > 0:
            advertencias.append(
                "La fila trae un código de gasto pero es un ingreso: se "
                "importa solo como movimiento de caja."
            )

        fila = FilaLibro(
            linea=numero,
            fecha=crudo["fecha"],
            tipo=crudo["tipo"],
            concepto=crudo["concepto"],
            ingreso=ingreso,
            egreso=egreso,
            saldo=saldo,
            saldo_anterior=saldo_anterior,
            clasificacion=crudo["clasificacion"],
            codigo=crudo["codigo"],
            advertencias=advertencias,
        )
        resultado.filas.append(fila)
        resultado.total_ingresos += ingreso
        resultado.total_egresos += egreso
        saldo_anterior = saldo

    if resultado.filas:
        resultado.saldo_final = resultado.filas[-1].saldo

    if resultado.saldo_inicial is not None and resultado.saldo_final is not None:
        esperado = resultado.saldo_inicial + resultado.total_ingresos - resultado.total_egresos
        if abs(esperado - resultado.saldo_final) > Decimal("0.50"):
            resultado.errores.append(
                f"El libro no cuadra: saldo inicial {resultado.saldo_inicial:,.2f} "
                f"+ ingresos {resultado.total_ingresos:,.2f} − egresos "
                f"{resultado.total_egresos:,.2f} = {esperado:,.2f}, pero el "
                f"último saldo es {resultado.saldo_final:,.2f}."
            )

    if resultado.totales_declarados:
        ti, te, ts = resultado.totales_declarados
        if abs(ti - resultado.total_ingresos) > Decimal("0.50"):
            resultado.advertencias.append(
                f"Los ingresos del libro ({ti:,.2f}) no coinciden con la suma "
                f"de las filas ({resultado.total_ingresos:,.2f})."
            )
        if abs(te - resultado.total_egresos) > Decimal("0.50"):
            resultado.advertencias.append(
                f"Los egresos del libro ({te:,.2f}) no coinciden con la suma "
                f"de las filas ({resultado.total_egresos:,.2f})."
            )
        if abs(ts - (resultado.saldo_final or _CERO)) > Decimal("0.50"):
            resultado.advertencias.append(
                f"El saldo final del libro ({ts:,.2f}) no coincide con el "
                f"último saldo de las filas ({resultado.saldo_final or _CERO:,.2f})."
            )

    if not resultado.filas:
        resultado.errores.append(
            "No se reconoció ninguna fila. Revisa que las fechas estén al "
            "inicio y que los montos tengan el símbolo $."
        )
    return resultado


# ---------------------------------------------------------------------------
# Importación a la base de datos
# ---------------------------------------------------------------------------
def _cuenta(db: Session, metodo_caja_id: int) -> MetodoCaja:
    cuenta = db.query(MetodoCaja).filter(MetodoCaja.id == metodo_caja_id).first()
    if cuenta is None:
        raise ValueError("La cuenta de caja indicada no existe.")
    return cuenta


def _moneda_cop(db: Session) -> Moneda:
    moneda = db.query(Moneda).filter(Moneda.codigo == "COP").first()
    if moneda is None:
        raise ValueError("No existe la moneda COP en el catálogo.")
    return moneda


def _tasa_para(db: Session, moneda: Moneda, fecha: date) -> Decimal:
    """Tasa de la moneda del libro hacia la base (COP), a la fecha de la fila.

    Para COP es 1.0; para otras monedas usa la tasa registrada del día (o la
    más reciente anterior). Si nunca se registró una tasa queda en 1.0 y el
    preview avisa.
    """
    if moneda.codigo == "COP":
        return Decimal("1.0")
    return Decimal(str(obtener_tasa_moneda_a_cop(db, moneda.id, fecha)))


def _aviso_sin_tasa(db: Session, moneda: Optional[Moneda]) -> Optional[str]:
    """Aviso si la cuenta no es COP y nunca se registró una tasa de cambio."""
    if moneda is None or moneda.codigo == "COP":
        return None
    if obtener_ultima_tasa(db, moneda.id, 1) is not None:
        return None
    return (
        f"La cuenta está en {moneda.codigo} y no hay una tasa {moneda.codigo} "
        f"→ COP registrada: los movimientos se guardan con tasa 1.0 hacia la "
        f"moneda base. Registra la tasa del período para que el equivalente "
        f"en la base sea correcto."
    )


def _saldo_cuenta_hasta(
    db: Session, metodo_caja_id: int, hasta: date
) -> Decimal:
    """Saldo de la cuenta hasta una fecha (SALIDA resta; el resto suma)."""
    movimientos = (
        db.query(MovimientoCaja)
        .filter(
            MovimientoCaja.metodo_caja_id == metodo_caja_id,
            MovimientoCaja.fecha <= hasta,
        )
        .all()
    )
    total = _CERO
    for mov in movimientos:
        monto = Decimal(str(mov.monto or 0))
        total += -monto if mov.tipo == "SALIDA" else monto
    return total


def _etiqueta(cuenta: MetodoCaja, periodo: str) -> str:
    return f"Libro {cuenta.codigo} {periodo}"


# Palabras que aparecen en casi todos los movimientos y no identifican a
# nadie: si se usaran para emparejar, cualquier venta sería "duplicado".
_PALABRAS_GENERICAS = {
    "VENTA", "PAGO", "ABONO", "COBRO", "EFECTIVO", "PESOS", "DOLARES",
    "CLIENTE", "GASTO", "COMPRA", "PAGADO", "TRANSFERENCIA", "NEQUI",
    "ZELLE", "BANCO", "CUENTA", "CAJA", "LIBRO", "MES", "DEL", "PARA",
    "POR", "CON", "LOS", "LAS", "UNA", "UNOS", "UNAS", "SENOR", "SENORA",
}


def _tokens_nombre(texto: str) -> set[str]:
    normal = unicodedata.normalize("NFKD", texto or "")
    normal = normal.encode("ascii", "ignore").decode().upper()
    return {
        token for token in re.split(r"[^A-Z]+", normal)
        if len(token) >= 4 and token not in _PALABRAS_GENERICAS
    }


def _marcar_duplicados(
    db: Session, cuenta: MetodoCaja, filas: list[FilaLibro]
) -> None:
    """Marca filas que ya existen en la cuenta (mismo sentido, importe y persona).

    Sirve para no duplicar las ventas/gastos que ya se registraron por la vía
    normal del ERP (cobros, nómina, compras) antes de importar el libro.
    Es una sugerencia: la importación puede omitirlas o incluirlas.
    """
    fechas = [f.fecha for f in filas if not f.es_saldo_inicial]
    if not fechas:
        return
    desde = min(fechas) - timedelta(days=31)
    hasta = max(fechas) + timedelta(days=31)
    existentes = (
        db.query(MovimientoCaja)
        .filter(
            MovimientoCaja.metodo_caja_id == cuenta.id,
            MovimientoCaja.fecha >= desde,
            MovimientoCaja.fecha <= hasta,
        )
        .all()
    )
    for fila in filas:
        if fila.es_saldo_inicial or fila.delta == 0:
            continue
        direccion = "ENTRADA" if fila.delta > 0 else "SALIDA"
        monto = abs(fila.delta)
        tolerancia = max(Decimal("1"), monto * Decimal("0.005"))
        tokens_fila = _tokens_nombre(f"{fila.tipo} {fila.concepto}")
        if not tokens_fila:
            continue
        for mov in existentes:
            if mov.tipo != direccion:
                continue
            if abs((mov.fecha - fila.fecha).days) > 20:
                continue
            monto_existente = Decimal(str(mov.monto or 0))
            if abs(monto_existente - monto) > tolerancia:
                continue
            # Además del importe, debe coincidir al menos un nombre/razón
            # social: dos ventas de 100.000 a personas distintas no son la
            # misma operación.
            tokens_mov = _tokens_nombre(
                f"{mov.concepto or ''} {mov.persona_entidad or ''} {mov.referencia or ''}"
            )
            if not (tokens_fila & tokens_mov):
                continue
            fila.duplicado_de = (
                f"{mov.fecha.isoformat()} · {mov.tipo} · "
                f"{monto_existente:,.0f} · {mov.referencia or 'sin referencia'}"
            )
            break


def _ya_importado(db: Session, etiqueta: str) -> bool:
    if db.query(MovimientoCaja).filter(MovimientoCaja.referencia == etiqueta).first():
        return True
    return (
        db.query(Gasto)
        .filter(Gasto.observaciones.like(f"[{etiqueta}]%"))
        .first()
        is not None
    )


def _tipo_gasto(db: Session, clasificacion: str) -> TipoGasto:
    """TipoGasto del catálogo para la clasificación (compartido con Gastos)."""
    return gastos_service.tipo_gasto_para_clasificacion(db, clasificacion)


def _resumen(
    parsed: LibroParseado,
    cuenta: MetodoCaja,
    saldo_previo: Optional[Decimal],
    ya_importado: bool,
    con_detalle: bool = True,
    advertencias_extra: Optional[list[str]] = None,
) -> dict:
    periodo = parsed.periodo or ""
    diferencia = None
    if saldo_previo is not None and parsed.saldo_inicial is not None:
        # Positivo = el libro arranca con más saldo del que tiene la cuenta.
        diferencia = parsed.saldo_inicial - saldo_previo
    advertencias = list(advertencias_extra or []) + list(parsed.advertencias)
    if diferencia is not None and abs(diferencia) > Decimal("0.50"):
        advertencias.append(
            f"El saldo de la cuenta antes del período es {saldo_previo:,.2f} "
            f"y el libro arranca en {parsed.saldo_inicial:,.2f} "
            f"(diferencia {diferencia:,.2f}). Puedes cuadrar la cuenta con "
            f"ese saldo al importar o autorizar la diferencia."
        )
    duplicados = sum(1 for f in parsed.filas if f.duplicado_de)
    if duplicados:
        advertencias.append(
            f"{duplicados} fila{'s' if duplicados != 1 else ''} coincide con "
            f"movimientos que ya están en la cuenta (posibles duplicados)."
        )
    if ya_importado:
        advertencias.append(
            f"El período {periodo} ya fue importado en esta cuenta. "
            f"Borra esa importación antes de volver a cargarlo."
        )
    filas_detalle = []
    if con_detalle:
        for fila in parsed.filas:
            filas_detalle.append({
                "linea": fila.linea,
                "fecha": fila.fecha.isoformat(),
                "tipo": fila.tipo,
                "concepto": fila.concepto,
                "ingreso": fila.ingreso,
                "egreso": fila.egreso,
                "saldo": fila.saldo,
                "clasificacion": fila.clasificacion,
                "codigo": fila.codigo,
                "es_saldo_inicial": fila.es_saldo_inicial,
                "duplicado_de": fila.duplicado_de,
                "advertencias": fila.advertencias,
            })
    return {
        "periodo": periodo,
        "cuenta_id": cuenta.id,
        "cuenta_nombre": cuenta.nombre,
        "filas": len(parsed.filas),
        "movimientos": parsed.movimientos,
        "gastos": parsed.gastos,
        "duplicados": duplicados,
        "saldo_inicial": parsed.saldo_inicial,
        "saldo_final": parsed.saldo_final,
        "total_ingresos": parsed.total_ingresos,
        "total_egresos": parsed.total_egresos,
        "saldo_previo_cuenta": saldo_previo,
        "diferencia_saldo_inicial": diferencia,
        "ya_importado": ya_importado,
        "advertencias": advertencias,
        "errores": list(parsed.errores),
        "omitidas": parsed.omitidas,
        "filas_detalle": filas_detalle,
    }


def previsualizar_libro(
    db: Session, texto: str, metodo_caja_id: int
) -> dict:
    parsed = parsear_libro(texto)
    cuenta = _cuenta(db, metodo_caja_id)
    aviso = _aviso_sin_tasa(db, cuenta.moneda)
    _marcar_duplicados(db, cuenta, parsed.filas)
    fechas = [f.fecha for f in parsed.filas if not f.es_saldo_inicial]
    saldo_previo = None
    if fechas:
        saldo_previo = _saldo_cuenta_hasta(db, cuenta.id, min(fechas) - timedelta(days=1))
    etiqueta = _etiqueta(cuenta, parsed.periodo or "")
    return _resumen(
        parsed, cuenta, saldo_previo, _ya_importado(db, etiqueta),
        con_detalle=True, advertencias_extra=[aviso] if aviso else [],
    )


def _fecha_ajuste_saldo(periodo: Optional[str], primera: date) -> date:
    """Último día del mes anterior al período importado.

    El ajuste de "cuadrar saldo inicial" representa el saldo que venía del
    período previo. Si se fecha en el primer día del período aparece como un
    INGRESO del mes y la tarjeta "Saldo inicial (antes del período)" muestra
    un saldo menor al del libro (el saldo final sí queda igual).
    """
    if periodo:
        try:
            inicio = date(int(periodo[:4]), int(periodo[5:7]), 1)
        except (ValueError, IndexError):
            inicio = None
        if inicio is not None:
            return inicio - timedelta(days=1)
    return primera - timedelta(days=1)


def importar_libro(
    db: Session,
    *,
    texto: str,
    metodo_caja_id: int,
    usuario: Optional[Usuario] = None,
    cuadrar_saldo_inicial: bool = False,
    permitir_saldo_distinto: bool = False,
    omitir_duplicados: bool = True,
) -> dict:
    parsed = parsear_libro(texto)
    if parsed.errores:
        raise ValueError(" ".join(parsed.errores))
    if not parsed.filas:
        raise ValueError("No se reconoció ninguna fila del libro.")
    if not parsed.periodo:
        raise ValueError("No se pudo determinar el período del libro.")

    cuenta = _cuenta(db, metodo_caja_id)
    moneda = cuenta.moneda or _moneda_cop(db)
    aviso_sin_tasa = _aviso_sin_tasa(db, moneda)
    if aviso_sin_tasa:
        parsed.advertencias.append(aviso_sin_tasa)

    etiqueta = _etiqueta(cuenta, parsed.periodo)
    if _ya_importado(db, etiqueta):
        raise ValueError(
            f"El período {parsed.periodo} ya fue importado en la cuenta "
            f"{cuenta.nombre}. Borra esa importación antes de repetirla."
        )

    fechas = [f.fecha for f in parsed.filas if not f.es_saldo_inicial]
    saldo_previo = (
        _saldo_cuenta_hasta(db, cuenta.id, min(fechas) - timedelta(days=1))
        if fechas
        else _CERO
    )
    _marcar_duplicados(db, cuenta, parsed.filas)
    if (
        parsed.saldo_inicial is not None
        and not cuadrar_saldo_inicial
        and abs(saldo_previo - parsed.saldo_inicial) > Decimal("0.50")
        and not permitir_saldo_distinto
    ):
        raise ValueError(
            f"El saldo de la cuenta antes del período es {saldo_previo:,.2f} "
            f"y el libro arranca en {parsed.saldo_inicial:,.2f}. Si ya "
            f"registraste septiembre, revisa el saldo; si quieres cargarlo "
            f"igual, autoriza la diferencia o marca 'cuadrar saldo inicial'."
        )

    movimientos = 0
    gastos = 0
    omitidos = 0
    duplicados = sum(1 for f in parsed.filas if f.duplicado_de)
    try:
        # Cuadrar la cuenta con el saldo inicial del libro: en vez de crear
        # una apertura por el total (que duplicaría lo que ya había), se
        # registra un ajuste por la DIFERENCIA contra el saldo actual. Va
        # fechado ANTES del período (último día del mes anterior) para que la
        # vista lo muestre como saldo inicial y no como ingreso del mes.
        if cuadrar_saldo_inicial and parsed.saldo_inicial is not None and fechas:
            ajuste = parsed.saldo_inicial - saldo_previo
            if ajuste != 0:
                fecha_ajuste = _fecha_ajuste_saldo(parsed.periodo, min(fechas))
                registrar_movimiento_caja(
                    db,
                    metodo_caja_id=cuenta.id,
                    tipo="APERTURA" if ajuste > 0 else "SALIDA",
                    monto=float(abs(ajuste)),
                    moneda_id=moneda.id,
                    tasa_cambio=float(_tasa_para(db, moneda, fecha_ajuste)),
                    fecha=fecha_ajuste,
                    referencia=etiqueta,
                    concepto=(
                        f"[{etiqueta}] Ajuste para cuadrar con el saldo inicial "
                        f"del libro ({parsed.saldo_inicial:,.2f})"
                    ),
                    usuario_id=usuario.id if usuario else None,
                )
                movimientos += 1

        for fila in parsed.filas:
            if fila.es_saldo_inicial:
                continue

            if fila.delta == 0:
                continue

            if omitir_duplicados and fila.duplicado_de:
                omitidos += 1
                continue

            if fila.egreso > 0 and fila.clasificacion:
                tipo_gasto = _tipo_gasto(db, fila.clasificacion)
                gasto = gastos_schemas.GastoCreate(
                    tipo_gasto_id=tipo_gasto.id,
                    moneda_id=moneda.id,
                    fecha=fila.fecha,
                    descripcion=fila.descripcion or "Gasto importado del libro",
                    monto=fila.egreso,
                    tasa_cambio=None,
                    clasificacion=fila.clasificacion,
                    metodo_caja_id=cuenta.id,
                    observaciones=(
                        f"[{etiqueta}] Código original: {fila.codigo}. "
                        f"TIPO: {fila.tipo or '—'} · CONCEPTO: {fila.concepto or '—'}"
                    )[:2000],
                )
                gasto_creado = gastos_service.crear_gasto(
                    db, gasto, usuario, commit=False
                )
                # El movimiento del gasto conserva la referencia "Gasto #id"
                # (así se sincroniza al editar/eliminar), pero se marca con la
                # etiqueta del libro para poder deshacer la importación.
                movimiento = (
                    db.query(MovimientoCaja)
                    .filter(MovimientoCaja.referencia == f"Gasto #{gasto_creado.id}")
                    .first()
                )
                if movimiento is not None:
                    movimiento.concepto = (
                        f"[{etiqueta}] {fila.tipo or 'Gasto'} · {fila.concepto or ''}"
                    )[:1000]
                    movimiento.persona_entidad = (fila.tipo or "").strip() or None
                gastos += 1
            else:
                registrar_movimiento_caja(
                    db,
                    metodo_caja_id=cuenta.id,
                    tipo="ENTRADA" if fila.ingreso > 0 else "SALIDA",
                    monto=float(abs(fila.delta)),
                    moneda_id=moneda.id,
                    tasa_cambio=float(_tasa_para(db, moneda, fila.fecha)),
                    fecha=fila.fecha,
                    referencia=etiqueta,
                    concepto=(
                        f"[{etiqueta}] {fila.tipo or ''} · {fila.concepto or ''}"
                    )[:1000],
                    persona_entidad=(fila.tipo or "").strip() or None,
                    usuario_id=usuario.id if usuario else None,
                )
                movimientos += 1

        record_event(
            db,
            actor=usuario,
            action="IMPORT",
            entity_type="libro_caja",
            entity_id=etiqueta,
            after={
                "cuenta": cuenta.nombre,
                "periodo": parsed.periodo,
                "movimientos": movimientos,
                "gastos": gastos,
                "duplicados": duplicados,
                "omitidos": omitidos,
                "saldo_inicial": str(parsed.saldo_inicial),
                "saldo_final": str(parsed.saldo_final),
                "total_ingresos": str(parsed.total_ingresos),
                "total_egresos": str(parsed.total_egresos),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "periodo": parsed.periodo,
        "cuenta_id": cuenta.id,
        "cuenta_nombre": cuenta.nombre,
        "filas": len(parsed.filas),
        # Movimientos de caja totales: ajuste de saldo (si se pidió) + filas
        # sin G + los movimientos que genera cada gasto clasificado.
        "movimientos": movimientos + gastos,
        "gastos": gastos,
        "duplicados": duplicados,
        "omitidos": omitidos,
        "saldo_inicial": parsed.saldo_inicial,
        "saldo_final": parsed.saldo_final,
        "total_ingresos": parsed.total_ingresos,
        "total_egresos": parsed.total_egresos,
        "saldo_previo_cuenta": saldo_previo,
        "diferencia_saldo_inicial": (
            parsed.saldo_inicial - saldo_previo
            if parsed.saldo_inicial is not None else None
        ),
        "ya_importado": False,
        "advertencias": parsed.advertencias,
        "errores": [],
        "omitidas": parsed.omitidas,
        "filas_detalle": [],
    }


def deshacer_importacion(
    db: Session,
    *,
    metodo_caja_id: int,
    periodo: str,
    usuario: Optional[Usuario] = None,
) -> dict:
    cuenta = _cuenta(db, metodo_caja_id)
    etiqueta = _etiqueta(cuenta, periodo)
    gastos = (
        db.query(Gasto)
        .filter(Gasto.observaciones.like(f"[{etiqueta}]%"))
        .all()
    )
    gastos_borrados = 0
    for gasto in gastos:
        db.query(MovimientoCaja).filter(
            MovimientoCaja.referencia == f"Gasto #{gasto.id}"
        ).delete(synchronize_session=False)
        db.delete(gasto)
        gastos_borrados += 1
    movimientos_borrados = (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.referencia == etiqueta)
        .delete(synchronize_session=False)
    )
    record_event(
        db,
        actor=usuario,
        action="DELETE",
        entity_type="libro_caja",
        entity_id=etiqueta,
        before={"gastos": gastos_borrados, "movimientos": movimientos_borrados},
    )
    db.commit()
    return {
        "periodo": periodo,
        "cuenta_nombre": cuenta.nombre,
        "gastos_borrados": gastos_borrados,
        "movimientos_borrados": int(movimientos_borrados or 0),
    }


# ---------------------------------------------------------------------------
# Vista del libro (como la hoja de Excel: fecha, tipo, concepto, ingreso,
# egreso y saldo corrido)
# ---------------------------------------------------------------------------
_TAG_LIBRO = re.compile(r"^\[Libro [^\]]+\]\s*(.*)$")


def _tipo_concepto_movimiento(
    mov: MovimientoCaja, gasto: Optional[Gasto]
) -> tuple[str, str]:
    obs = (mov.concepto or "").strip()
    persona = (mov.persona_entidad or "").strip()
    match = _TAG_LIBRO.match(obs)
    if match:
        resto = match.group(1).strip()
        # El separador es " · " pero, si el CONCEPTO está vacío, el strip deja
        # " ·" sin espacio final: hay que aceptar las dos formas.
        if " ·" in resto:
            tipo, concepto = resto.split(" ·", 1)
        else:
            tipo, concepto = "", resto
        tipo = persona or tipo.strip() or ("GASTO" if gasto else mov.tipo)
        return tipo, concepto.strip()
    if persona:
        return persona, (obs or mov.referencia or "")
    if gasto:
        return "GASTO", (gasto.descripcion or obs or mov.referencia or "")
    if mov.pago_id:
        return "VENTA", (obs or mov.referencia or "Cobro de venta")
    if mov.transferencia_id:
        return "TRANSFERENCIA", (obs or "Transferencia entre cuentas")
    if mov.tipo == "APERTURA":
        return "APERTURA", (obs or "Saldo inicial")
    return "MOVIMIENTO", (obs or mov.referencia or "")


def obtener_libro_caja(
    db: Session,
    metodo_caja_id: int,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> dict:
    """Devuelve el libro de una cuenta con saldo corrido, como la hoja."""
    cuenta = _cuenta(db, metodo_caja_id)

    # Rango por defecto: el mes del último movimiento (o el mes actual).
    ultima = (
        db.query(func.max(MovimientoCaja.fecha))
        .filter(MovimientoCaja.metodo_caja_id == cuenta.id)
        .scalar()
    )
    base = fecha_hasta or ultima or hoy_ve()
    if fecha_hasta is None:
        fecha_hasta = date(
            base.year, base.month, calendar.monthrange(base.year, base.month)[1]
        )
    if fecha_desde is None:
        fecha_desde = date(base.year, base.month, 1)
    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    saldo_inicial = _saldo_cuenta_hasta(
        db, cuenta.id, fecha_desde - timedelta(days=1)
    )
    movimientos = (
        db.query(MovimientoCaja)
        .options(
            joinedload(MovimientoCaja.usuario),
            # Para los cobros creados desde Ventas, la hora fiable es la del
            # pago (hora VE); el created_at del movimiento puede venir en UTC.
            joinedload(MovimientoCaja.pago),
        )
        .filter(
            MovimientoCaja.metodo_caja_id == cuenta.id,
            MovimientoCaja.fecha >= fecha_desde,
            MovimientoCaja.fecha <= fecha_hasta,
        )
        .order_by(
            MovimientoCaja.fecha,
            # La hora del movimiento manda cuando existe; las filas sin hora
            # (NULLS LAST) conservan el orden de registro dentro del día.
            MovimientoCaja.hora.asc().nulls_last(),
            MovimientoCaja.id,
        )
        .all()
    )

    gasto_ids: set[int] = set()
    for mov in movimientos:
        if mov.referencia and mov.referencia.startswith("Gasto #"):
            try:
                gasto_ids.add(int(mov.referencia.split("#", 1)[1].split()[0]))
            except (ValueError, IndexError):
                pass
    gastos = {
        gasto.id: gasto
        for gasto in (
            db.query(Gasto).filter(Gasto.id.in_(gasto_ids)).all()
            if gasto_ids else []
        )
    }

    saldo = saldo_inicial
    total_ingresos = _CERO
    total_egresos = _CERO
    filas: list[dict] = []
    por_clasificacion: dict[str, dict] = {}

    for mov in movimientos:
        monto = Decimal(str(mov.monto or 0))
        ingreso = monto if mov.tipo != "SALIDA" else _CERO
        egreso = monto if mov.tipo == "SALIDA" else _CERO
        saldo += ingreso - egreso
        total_ingresos += ingreso
        total_egresos += egreso

        gasto = None
        if mov.referencia and mov.referencia.startswith("Gasto #"):
            try:
                gasto = gastos.get(int(mov.referencia.split("#", 1)[1].split()[0]))
            except (ValueError, IndexError):
                gasto = None
        tipo, concepto = _tipo_concepto_movimiento(mov, gasto)
        clasificacion = gasto.clasificacion if gasto else None
        if clasificacion:
            acumulado = por_clasificacion.setdefault(
                clasificacion, {"count": 0, "total": _CERO}
            )
            acumulado["count"] += 1
            acumulado["total"] += monto

        if _TAG_LIBRO.match((mov.concepto or "").strip()):
            origen = "LIBRO"
        elif gasto:
            origen = "GASTO"
        elif mov.pago_id:
            origen = "VENTA"
        elif mov.transferencia_id:
            origen = "TRANSFERENCIA"
        else:
            origen = "MANUAL"

        usuario = mov.usuario
        usuario_nombre = (
            (usuario.nombre or usuario.nombre_usuario) if usuario else None
        )
        # Los movimientos de cobro creados por Ventas guardan a veces el
        # created_at en UTC; el Pago sí tiene la hora VE. Para los importados
        # o manuales se conserva el created_at del movimiento.
        created_at = mov.created_at
        if (mov.referencia or "").startswith("Pago #") and mov.pago is not None:
            created_at = mov.pago.created_at or mov.created_at

        filas.append({
            "id": mov.id,
            "fecha": mov.fecha,
            "hora": mov.hora,
            "tipo": tipo,
            "tipo_movimiento": mov.tipo,
            "concepto": concepto,
            "ingreso": ingreso,
            "egreso": egreso,
            "saldo": saldo,
            "clasificacion": clasificacion,
            "origen": origen,
            "referencia": mov.referencia,
            "persona_entidad": mov.persona_entidad,
            "usuario_id": mov.usuario_id,
            "usuario_nombre": usuario_nombre,
            "created_at": created_at,
        })

    clasificaciones = []
    for clave, etiqueta in gastos_service.CLASIFICACIONES_GASTO.items():
        datos = por_clasificacion.get(clave)
        if datos:
            clasificaciones.append({
                "clasificacion": clave,
                "label": etiqueta,
                "count": datos["count"],
                "total": datos["total"],
            })

    return {
        "cuenta_id": cuenta.id,
        "cuenta_nombre": cuenta.nombre,
        "moneda_codigo": cuenta.moneda.codigo if cuenta.moneda else "COP",
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "saldo_inicial": saldo_inicial,
        "total_ingresos": total_ingresos,
        "total_egresos": total_egresos,
        "saldo_final": saldo,
        "filas": filas,
        "clasificaciones": clasificaciones,
    }

