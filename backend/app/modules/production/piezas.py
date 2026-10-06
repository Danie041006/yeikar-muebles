"""Detección de piezas de un mueble a partir de su descripción.

Un "juego" (sofá + poltronas) se cotiza como UN renglón con un precio global;
el taller solo necesita ver las piezas para armarlo/entregarlo. Este motor las
detecta del texto para que nadie tenga que teclearlas: si no está seguro, NO
inventa (devuelve lista vacía). Reglas conservadoras:

- Solo propone checklist si detecta un conjunto: 2+ piezas o una palabra de
  conjunto (JUEGO/COMBO/CONJUNTO/SET). Un mueble suelto no genera nada.
- Cuenta piezas concretas (sofá, poltrona, silla, mesa, cama…); ignora
  accesorios como cojines o almohadas (no se fabrican por separado).
- Entiende "N POLTRONAS", "DOS SOFAS", "SOFA DE 3 PUESTOS", "MUEBLES DE 3
  PUESTOS", "MESAS DE NOCHE", y el conteo en palabras o números.
"""
import re
import unicodedata

# Números escritos en palabras que aparecen en las notas reales.
_NUMEROS = {
    "UN": 1, "UNA": 1, "UNO": 1,
    "DOS": 2, "TRES": 3, "CUATRO": 4, "CINCO": 5,
    "SEIS": 6, "SIETE": 7, "OCHO": 8, "NUEVE": 9, "DIEZ": 10,
}

# Singular canónico por sustantivo de mueble (plural y singular caen aquí).
_MUEBLES = {
    "SOFA": "Sofá", "SOFAS": "Sofá",
    "POLTRONA": "Poltrona", "POLTRONAS": "Poltrona",
    "SILLON": "Sillón", "SILLONES": "Sillón",
    "SILLA": "Silla", "SILLAS": "Silla",
    "BANCO": "Banco", "BANCOS": "Banco",
    "COMODA": "Cómoda", "COMODAS": "Cómoda",
    "ESPEJO": "Espejo", "ESPEJOS": "Espejo",
    "PUFF": "Puff", "PUFFS": "Puff",
    "CAMA": "Cama", "CAMAS": "Cama",
    "MUEBLE": "Mueble", "MUEBLES": "Mueble",
}

_RE_CONJUNTO = re.compile(r"\b(JUEGO|JUEGOS|COMBO|CONJUNTO|SET|SALA)\b")
_RE_NOCHE = re.compile(r"\b(\d{1,2}|[A-Z]+)\s+MESAS?\s+DE\s+NOCHE\b")
_RE_PUESTOS = re.compile(
    r"\b(SOFA|SOFAS|MUEBLE|MUEBLES|SALA)\s+DE\s+(\d{1,2}|[A-Z]+)\s+PUESTOS?\b"
)
_RE_SOFA_P = re.compile(r"\bSOFA\s*(\d{1,2})\s*P\b")
_RE_CONTEO = re.compile(
    r"\b(\d{1,2}|[A-Z]+)\s+"
    r"(SOFAS?|POLTRONAS?|SILLONES?|SILLAS?|BANCOS?|COMODAS?|ESPEJOS?|PUFFS?|CAMAS?|MUEBLES?)\b"
)


def _sin_acentos(texto: str) -> str:
    plano = unicodedata.normalize("NFD", texto)
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def _normalizar(descripcion: str | None) -> str:
    if not descripcion:
        return ""
    # Los separadores de las notas (guiones, /, ., comas) no separan piezas:
    # se vuelven espacio para que el regex vea frases limpias.
    texto = _sin_acentos(descripcion.upper())
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _cantidad(token: str) -> int | None:
    if token.isdigit():
        valor = int(token)
        return valor if 1 <= valor <= 50 else None
    return _NUMEROS.get(token)


def detectar_piezas(descripcion: str | None) -> list[dict]:
    """Devuelve [{nombre, cantidad}] o [] si no es un conjunto claro."""
    texto = _normalizar(descripcion)
    if not texto:
        return []

    encontradas: list[tuple[str, int]] = []

    def _agregar(nombre: str, cantidad: int) -> None:
        if cantidad <= 0:
            return
        for i, (existente, acumulada) in enumerate(encontradas):
            if existente == nombre:
                encontradas[i] = (nombre, acumulada + cantidad)
                return
        encontradas.append((nombre, cantidad))

    # 1) "MESAS DE NOCHE" (compuesto): antes que el conteo genérico de mesas.
    for match in _RE_NOCHE.finditer(texto):
        cantidad = _cantidad(match.group(1))
        if cantidad:
            _agregar("Mesa de noche", cantidad)
    texto = _RE_NOCHE.sub(" ", texto)

    # 2) "SOFA/MUEBLE DE N PUESTOS" (el sofá con su tamaño).
    for match in _RE_PUESTOS.finditer(texto):
        cantidad = _cantidad(match.group(2))
        if not cantidad:
            continue
        prefijo = match.group(1)
        nombre = f"Sofá de {cantidad} puestos" if "SOFA" in prefijo or "SALA" in prefijo else f"Mueble de {cantidad} puestos"
        _agregar(nombre, 1)
    texto = _RE_PUESTOS.sub(" ", texto)

    # 3) "SOFA 3P" (abreviatura de taller).
    for match in _RE_SOFA_P.finditer(texto):
        cantidad = _cantidad(match.group(1))
        if cantidad:
            _agregar(f"Sofá de {cantidad} puestos", 1)
    texto = _RE_SOFA_P.sub(" ", texto)

    # 4) Conteo genérico: "2 POLTRONAS", "TRES SILLAS", "1 CAMA"…
    for match in _RE_CONTEO.finditer(texto):
        cantidad = _cantidad(match.group(1))
        if not cantidad:
            continue
        nombre = _MUEBLES.get(match.group(2))
        if nombre:
            _agregar(nombre, cantidad)

    # Sin conjunto claro no se propone checklist (un mueble suelto no la lleva).
    tiene_conjunto = bool(_RE_CONJUNTO.search(texto)) or len(encontradas) >= 2
    if not tiene_conjunto or not encontradas:
        return []

    # Defensa: una descripción rara no debe llenar la tarjeta de ruido.
    return [{"nombre": nombre, "cantidad": cantidad} for nombre, cantidad in encontradas[:12]]


def sembrar_piezas_orden(db, orden, detalle=None) -> list:
    """Crea el checklist de piezas de una orden recién creada (idempotente).

    No toca nada si la orden ya tiene piezas ni si no se detecta un conjunto.
    La fuente del texto es: descripción de la línea → nombre del producto.
    """
    from app.modules.production.model import PiezaOrden

    if orden.piezas:
        return []
    if detalle is None:
        detalle = orden.detalle_pedido
    texto = None
    if detalle is not None:
        producto = getattr(detalle, "producto", None)
        texto = detalle.descripcion_especifica or (producto.nombre if producto else None)
    if not texto and orden.producto_id:
        producto = getattr(orden, "producto", None)
        texto = producto.nombre if producto else None

    piezas = detectar_piezas(texto)
    creadas = []
    for posicion, pieza in enumerate(piezas):
        fila = PiezaOrden(
            orden_produccion_id=orden.id,
            posicion=posicion,
            nombre=pieza["nombre"],
            cantidad=pieza["cantidad"],
        )
        db.add(fila)
        creadas.append(fila)
    return creadas
