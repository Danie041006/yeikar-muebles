"""
medidas_colchon.py
==================
Catálogo de medidas estándar de colchones (referencia venezolana) y
utilidades para derivar las dimensiones REALES de una cama a partir
del nombre del producto.

Motivación: las camas importadas del Excel llegaron todas con
ancho_base=1.60 x largo_base=1.90 (medidas FICTICIAS, el default del
importador). Las cantidades de las recetas SÍ son reales (las calculó
YEIKAR para la medida real de cada cama), así que escalarlas contra una
base falsa corrompe el resultado. El nombre codifica la medida real
("CAMA ... DE 2X2", "1.60", "1.40"...), y este catálogo la valida:
nunca se inventan pares que no existen (no hay colchón 1.35 x 2.00).
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Catálogo de medidas estándar (ancho, largo) en metros — referencia VE
# ---------------------------------------------------------------------------
MEDIDAS_COLCHON: list[tuple[float, float]] = [
    (0.80, 1.90),   # individual
    (0.90, 1.90),   # individual estrecha
    (1.00, 1.90),   # individual amplia
    (1.20, 1.90),   # twin / 1 plaza
    (1.35, 1.90),   # plaza y media / full
    (1.40, 1.90),   # matrimonial
    (1.50, 1.90),   # matrimonial amplia
    (1.60, 1.90),   # queen
    (1.80, 2.00),   # king
    (2.00, 2.00),   # king extra ("2x2")
]

_LARGO_POR_ANCHO: dict[float, float] = dict(MEDIDAS_COLCHON)

_PAR_EXPLICITO = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX*]\s*(\d+(?:[.,]\d+)?)")
_ANCHO_SUELTO = re.compile(r"(\d[.,]\d{2})")


def largo_estandar(ancho: float) -> Optional[float]:
    """Largo de colchón estándar para un ancho dado, o None si no es válido."""
    return _LARGO_POR_ANCHO.get(round(float(ancho), 2))


def es_medida_estandar(ancho: float, largo: float) -> bool:
    """True si (ancho, largo) es un par de colchón estándar conocido."""
    return largo_estandar(ancho) == round(float(largo), 2)


def _norm_numero(valor: str) -> Optional[float]:
    """'1,60' / '1.60' / '2' → 1.6 / 2.0. None si no es número."""
    try:
        return float(valor.strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _buscar_ancho_suelto(nombre: str) -> Optional[float]:
    """Busca un ancho válido del catálogo como decimal suelto ('1.60', '1,40')."""
    for match in _ANCHO_SUELTO.finditer(nombre):
        ancho = _norm_numero(match.group(1))
        if ancho is not None and ancho in _LARGO_POR_ANCHO:
            return ancho
    return None


def medidas_desde_nombre(nombre: Optional[str]) -> Optional[dict]:
    """
    Deriva las medidas reales (ancho x largo en metros) de una cama a
    partir del nombre del producto, validándolas contra el catálogo de
    colchones estándar.

    Retorna None si no se puede determinar con confianza.

    Resultado:
        {"ancho": 2.0, "largo": 2.0, "fuente": "par_explicito"|"ancho_catalogo",
         "corregido": False}   # corregido=True si el par del nombre no era
                               # estándar y se ajustó al catálogo
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return None

    # 1) Par explícito en el nombre: "2X2", "2*2", "1,60 X 1,90"
    m = _PAR_EXPLICITO.search(nombre)
    if m:
        ancho = _norm_numero(m.group(1))
        largo = _norm_numero(m.group(2))
        if ancho is not None and largo is not None:
            ancho = round(ancho, 2)
            largo = round(largo, 2)
            # Par estándar tal cual (2x2, 1.60x1.90...)
            if es_medida_estandar(ancho, largo):
                return {"ancho": ancho, "largo": largo, "fuente": "par_explicito", "corregido": False}
            # Par raro: corregir el largo al estándar del ancho
            largo_std = largo_estandar(ancho)
            if largo_std is not None:
                return {"ancho": ancho, "largo": largo_std, "fuente": "par_explicito", "corregido": True}
            # Ancho tampoco es estándar: descartar el par (ej. "2,10X22X18")
            return None

    # 2) Ancho suelto del catálogo en el nombre: "CAMA ... 1.60 ..."
    ancho = _buscar_ancho_suelto(nombre)
    if ancho is not None:
        return {
            "ancho": ancho,
            "largo": _LARGO_POR_ANCHO[ancho],
            "fuente": "ancho_catalogo",
            "corregido": False,
        }

    return None