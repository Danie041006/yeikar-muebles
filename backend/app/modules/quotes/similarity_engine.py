"""
similarity_engine.py
====================
Motor de Similitud del Intelligent Quotation Engine de YEIKAR.

Generalización (Jul 2026):
  El motor ahora soporta CUALQUIER tipo de mueble que fabrica YEIKAR.
  Estrategia de consulta:
    1. Consulta primero la tabla genérica `mueble_atributos` (todos los tipos).
    2. Para camas, también consulta `cama_historica_atributos` (datos históricos
       de las 63 camas importadas originalmente).
    3. Filtra por `tipo_mueble` para que solo se comparen muebles del mismo tipo.
    4. Ordena por similitud coseno y retorna Top N.

Principio: NO usa IA. Solo Python + matemáticas básicas → milisegundos de respuesta.
"""

import math
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session, joinedload

from app.modules.quotes.vision_provider import FurnitureAttributes
from app.modules.productos.model import Producto, ProductoMaterial, CamaHistoricaAtributos, MuebleAtributos


# Número mínimo de score para considerar un resultado "confiable"
SCORE_MINIMO_CONFIABLE = 0.40


@dataclass
class SimilarityResult:
    """Resultado de una búsqueda de similitud para una estructura histórica."""
    producto_id: int
    nombre: str
    tipo_mueble: str
    score: float                    # 0.00 a 1.00
    score_pct: int                  # 0 a 100 (para UI)
    coincidencias: list[str]        # Atributos que coinciden
    diferencias: list[str]          # Atributos que no coinciden
    ancho_base: Optional[float]
    largo_base: Optional[float]
    tiene_receta: bool              # Si tiene materiales definidos
    es_estructura_nueva: bool       # True si score < SCORE_MINIMO_CONFIABLE


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Similitud de coseno entre dos vectores. 1.0 = idénticos, 0.0 = ortogonales."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a ** 2 for a in vec_a))
    mag_b = math.sqrt(sum(b ** 2 for b in vec_b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _explain_generic(
    attrs: FurnitureAttributes,
    tiene_tapiceria_hist: bool,
    tiene_luces_hist: bool,
    estilo_hist: Optional[str],
    patas_hist: Optional[str],
    atributos_extra_hist: dict,
) -> tuple[list[str], list[str]]:
    """
    Genera listas legibles de coincidencias y diferencias.
    Funciona para cualquier tipo de mueble usando atributos comunes + extra.
    """
    coincidencias, diferencias = [], []

    checks_comunes = [
        ("Tapicería", attrs.tiene_tapiceria, tiene_tapiceria_hist),
        ("Luces LED", attrs.tiene_luces, tiene_luces_hist),
    ]
    for label, a, b in checks_comunes:
        (coincidencias if a == b else diferencias).append(label)

    # Patas
    if attrs.tipo_patas == patas_hist:
        coincidencias.append(f"Patas ({patas_hist or 'sin_patas'})")
    else:
        diferencias.append(f"Patas (foto: {attrs.tipo_patas or 'sin_patas'} | hist: {patas_hist or 'sin_patas'})")

    # Estilo
    if attrs.estilo_general == estilo_hist:
        coincidencias.append(f"Estilo {estilo_hist or 'moderno'}")
    else:
        diferencias.append(f"Estilo (foto: {attrs.estilo_general or '?'} | hist: {estilo_hist or '?'})")

    # Atributos extra: comparar los que estén en ambos
    for key, val_hist in (atributos_extra_hist or {}).items():
        val_new = attrs.atributos_extra.get(key)
        if val_new is None:
            continue
        label = key.replace("tiene_", "").replace("_", " ").capitalize()
        if isinstance(val_hist, bool) and isinstance(val_new, bool):
            (coincidencias if val_new == val_hist else diferencias).append(label)

    return coincidencias, diferencias


def _explain_cama_legacy(
    attrs: FurnitureAttributes,
    hist: CamaHistoricaAtributos,
) -> tuple[list[str], list[str]]:
    """Genera explicaciones para registros de CamaHistoricaAtributos (legacy)."""
    return _explain_generic(
        attrs=attrs,
        tiene_tapiceria_hist=hist.tiene_tapiceria,
        tiene_luces_hist=hist.tiene_luces,
        estilo_hist=hist.estilo_general,
        patas_hist=hist.tipo_patas,
        atributos_extra_hist={
            "tiene_nocheros": hist.tiene_nocheros,
            "tiene_espejo": hist.tiene_espejo,
        },
    )


def _vector_desde_cama_legacy(hist: CamaHistoricaAtributos) -> list[float]:
    """Convierte un registro legacy (6D) al vector de 8 dimensiones actual."""
    attrs = FurnitureAttributes(
        tipo_mueble="cama",
        familia_probable=None,
        estilo_general=hist.estilo_general,
        tipo_patas=hist.tipo_patas,
        tiene_tapiceria=hist.tiene_tapiceria,
        tiene_luces=hist.tiene_luces,
        nivel_confianza=1.0,
        observaciones=None,
        atributos_extra={
            "tiene_nocheros": hist.tiene_nocheros,
            "tiene_espejo": hist.tiene_espejo,
        },
    )
    return attrs.to_vector()


def _inferir_atributos_desde_receta(producto: Producto) -> FurnitureAttributes:
    """
    Infiere atributos visuales a partir de la receta (producto_material).
    Usado como fallback cuando no hay filas en mueble_atributos / cama_historica.
    """
    mats = [pm.material.nombre for pm in (producto.materiales or []) if pm.material]
    mats_upper = [m.upper() for m in mats]
    nombre_upper = (producto.nombre or "").upper()

    tiene_tapiceria = any(
        k in m for m in mats_upper
        for k in ("TELA", "ESPUMA", "ALGODON", "FIBRA", "CAPITONE", "POLIPIEL")
    )
    tiene_nocheros = (
        "NOCHERO" in nombre_upper
        or "CON MESA DE NOCHE" in nombre_upper
        or any("NOCHERO" in m for m in mats_upper)
    )
    tiene_espejo = any("ESPEJO" in m or "BISELADO" in m for m in mats_upper)
    tiene_luces = any(
        k in m for m in mats_upper
        for k in ("CABLE", "APAGADOR", "LUCES", "TOMA", "SWITCH", "LED")
    )

    tipo_patas = "sin_patas"
    for m in mats_upper:
        if "PATA" in m:
            if any(k in m for k in ("PLATEADA", "METAL", "ALUMINIO", " L ")):
                tipo_patas = "metal"
            else:
                tipo_patas = "madera"
            break

    estilo = "moderno"
    if any(k in nombre_upper for k in ("ROMANA", "DINASTIA", "VENECIA", "CLASIC", "IMPERIO")):
        estilo = "clasico"
    elif any(k in nombre_upper for k in ("RUSTIC", "CAMPESTR")):
        estilo = "rustico"

    return FurnitureAttributes(
        tipo_mueble="cama",
        familia_probable="tapizada" if tiene_tapiceria else "melamina",
        estilo_general=estilo,
        tipo_patas=tipo_patas,
        tiene_tapiceria=tiene_tapiceria,
        tiene_luces=tiene_luces,
        nivel_confianza=1.0,
        observaciones=None,
        atributos_extra={"tiene_nocheros": tiene_nocheros, "tiene_espejo": tiene_espejo},
    )


def _filtro_nombre_por_tipo(tipo_mueble: str):
    """Patrones de nombre en catálogo según tipo de mueble."""
    patrones = {
        "cama": "%cama%",
        "nochero": "%nochero%",
        "closet": "%closet%",
        "armario": "%armario%",
        "comedor": "%comedor%",
        "sala": "%sala%",
        "rack_tv": "%tv%",
    }
    from sqlalchemy import or_
    patron = patrones.get(tipo_mueble)
    if patron:
        return Producto.nombre.ilike(patron)
    return or_(Producto.nombre.ilike(f"%{tipo_mueble}%"), Producto.nombre.isnot(None))


def _fallback_catalogo_recetas(
    db: Session,
    attrs: FurnitureAttributes,
    top_n: int,
    producto_ids_vistos: set[int],
) -> list[SimilarityResult]:
    """
    Último recurso: busca productos con receta en el catálogo e infiere
    atributos desde sus materiales cuando las tablas históricas están vacías.
    """
    nuevo_vector = attrs.to_vector()
    resultados: list[SimilarityResult] = []

    candidatos: list[Producto] = (
        db.query(Producto)
        .options(joinedload(Producto.materiales).joinedload(ProductoMaterial.material))
        .filter(Producto.activo == True)
        .filter(_filtro_nombre_por_tipo(attrs.tipo_mueble))
        .all()
    )

    for producto in candidatos:
        if producto.id in producto_ids_vistos:
            continue
        if not producto.materiales:
            continue

        inferidos = _inferir_atributos_desde_receta(producto)
        hist_vector = inferidos.to_vector()
        score = _cosine_similarity(nuevo_vector, hist_vector)

        coincidencias, diferencias = _explain_generic(
            attrs=attrs,
            tiene_tapiceria_hist=inferidos.tiene_tapiceria,
            tiene_luces_hist=inferidos.tiene_luces,
            estilo_hist=inferidos.estilo_general,
            patas_hist=inferidos.tipo_patas,
            atributos_extra_hist=inferidos.atributos_extra,
        )

        resultados.append(SimilarityResult(
            producto_id=producto.id,
            nombre=producto.nombre,
            tipo_mueble=attrs.tipo_mueble,
            score=round(score, 4),
            score_pct=round(score * 100),
            coincidencias=coincidencias,
            diferencias=diferencias,
            ancho_base=float(producto.ancho_base) if producto.ancho_base else None,
            largo_base=float(producto.largo_base) if producto.largo_base else None,
            tiene_receta=True,
            es_estructura_nueva=score < SCORE_MINIMO_CONFIABLE,
        ))

    resultados.sort(key=lambda r: r.score, reverse=True)
    return resultados[:top_n]


def buscar_similares(
    db: Session,
    attrs: FurnitureAttributes,
    top_n: int = 3,
) -> list[SimilarityResult]:
    """
    Busca las estructuras históricas más similares a los atributos dados.
    Funciona para CUALQUIER tipo de mueble.

    Estrategia:
      - Consulta `mueble_atributos` filtrado por tipo_mueble.
      - Si tipo_mueble == "cama", también consulta `cama_historica_atributos`
        para aprovechar los 63 registros históricos originales.
      - Evita duplicados por producto_id.
      - Ordena por similitud de coseno descendente.

    Parámetros
    ----------
    db     : Sesión de SQLAlchemy
    attrs  : Atributos del mueble (validados por el vendedor)
    top_n  : Número de resultados (1-10)

    Retorna
    -------
    Lista de SimilarityResult, de mayor a menor score.
    """
    nuevo_vector = attrs.to_vector()
    resultados: list[SimilarityResult] = []
    producto_ids_vistos: set[int] = set()

    # --- 1. Consulta tabla genérica (todos los tipos) ---
    historicos_genericos: list[MuebleAtributos] = (
        db.query(MuebleAtributos)
        .filter(MuebleAtributos.tipo_mueble == attrs.tipo_mueble)
        .all()
    )

    for hist in historicos_genericos:
        if hist.producto_id in producto_ids_vistos:
            continue
        producto = hist.producto
        if not producto:
            continue
        producto_ids_vistos.add(hist.producto_id)

        hist_vector = hist.vector_similitud or []
        # Padding si el vector almacenado es más corto (compatibilidad)
        while len(hist_vector) < len(nuevo_vector):
            hist_vector.append(0.0)

        score = _cosine_similarity(nuevo_vector, hist_vector)

        coincidencias, diferencias = _explain_generic(
            attrs=attrs,
            tiene_tapiceria_hist=hist.tiene_tapiceria,
            tiene_luces_hist=hist.tiene_luces,
            estilo_hist=hist.estilo_general,
            patas_hist=hist.tipo_patas,
            atributos_extra_hist=hist.atributos_extra or {},
        )

        tiene_receta = len(producto.materiales) > 0 if hasattr(producto, "materiales") else False

        resultados.append(SimilarityResult(
            producto_id=hist.producto_id,
            nombre=producto.nombre,
            tipo_mueble=hist.tipo_mueble,
            score=round(score, 4),
            score_pct=round(score * 100),
            coincidencias=coincidencias,
            diferencias=diferencias,
            ancho_base=float(producto.ancho_base) if producto.ancho_base else None,
            largo_base=float(producto.largo_base) if producto.largo_base else None,
            tiene_receta=tiene_receta,
            es_estructura_nueva=score < SCORE_MINIMO_CONFIABLE,
        ))

    # --- 2. Fallback a cama_historica_atributos para camas (datos legacy) ---
    if attrs.tipo_mueble == "cama":
        historicos_cama: list[CamaHistoricaAtributos] = db.query(CamaHistoricaAtributos).all()

        for hist in historicos_cama:
            if hist.producto_id in producto_ids_vistos:
                continue
            producto = hist.producto
            if not producto:
                continue
            producto_ids_vistos.add(hist.producto_id)

            # Vector legacy (6D almacenado) → normalizar a 8D con la misma lógica del cotizador
            if hist.vector_similitud and isinstance(hist.vector_similitud, list) and len(hist.vector_similitud) >= 8:
                hist_vector = list(hist.vector_similitud)
            else:
                hist_vector = _vector_desde_cama_legacy(hist)

            score = _cosine_similarity(nuevo_vector, hist_vector)
            coincidencias, diferencias = _explain_cama_legacy(attrs, hist)

            tiene_receta = len(producto.materiales) > 0 if hasattr(producto, "materiales") else False

            resultados.append(SimilarityResult(
                producto_id=hist.producto_id,
                nombre=producto.nombre,
                tipo_mueble="cama",
                score=round(score, 4),
                score_pct=round(score * 100),
                coincidencias=coincidencias,
                diferencias=diferencias,
                ancho_base=float(producto.ancho_base) if producto.ancho_base else None,
                largo_base=float(producto.largo_base) if producto.largo_base else None,
                tiene_receta=tiene_receta,
                es_estructura_nueva=score < SCORE_MINIMO_CONFIABLE,
            ))

    # --- 3. Fallback: inferir desde recetas del catálogo si no hay histórico ---
    if not resultados:
        resultados = _fallback_catalogo_recetas(
            db=db,
            attrs=attrs,
            top_n=top_n,
            producto_ids_vistos=producto_ids_vistos,
        )

    # Ordenar por score descendente y limitar
    resultados.sort(key=lambda r: r.score, reverse=True)
    return resultados[:top_n]
