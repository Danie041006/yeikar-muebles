"""
atributos.py
============
Modelo de atributos del mueble y vocabulario de preguntas del costeador.

Era parte del antigo vision_provider.py (proveedores de visión OpenAI/Gemini).
Al eliminar el modo API, quedó solo el contrato de datos que usan
structure_builder.py y similarity_engine.py.
"""

from dataclasses import dataclass, field
from typing import Optional

# Tipos de mueble soportados por el sistema IQE de YEIKAR
TIPOS_MUEBLE_VALIDOS = {
    "cama", "nochero", "closet", "tocador", "armario",
    "sala", "comedor", "escritorio", "rack_tv", "libreria",
    "mueble_bano", "otro",
}

# Piezas (sub-partes) por tipo de mueble: cuando un mueble tiene varias piezas
# (cama + nocheros, mesa + sillas), la sección lleva la pieza entre paréntesis,
# igual que en el Excel: EBANISTERÍA (CAMA), PINTURA (NOCHEROS), etc.
SUB_PARTES_POR_TIPO: dict[str, dict[str, list[str]]] = {
    "cama": {
        "CAMA": ["EBANISTERÍA (CAMA)", "TENDIDO", "PINTURA (CAMA)", "TAPICERÍA", "TERMINACIÓN"],
        "NOCHEROS": ["EBANISTERÍA (NOCHEROS)", "PINTURA (NOCHEROS)", "TERMINACIÓN (NOCHEROS)"],
        "PATAS": ["PINTURA (PATAS)", "TENDIDO (PATAS)"],
    },
    "comedor": {
        "MESA": ["EBANISTERÍA (MESA)", "PINTURA (MESA)", "TERMINACIÓN"],
        "SILLAS": ["EBANISTERÍA (SILLAS)", "PINTURA (SILLAS)", "TAPICERÍA (SILLAS)", "TERMINACIÓN (SILLAS)"],
    },
    "sala": {
        "SOFÁ / PRINCIPAL": ["EBANISTERÍA (SOFÁ)", "PINTURA (SOFÁ)", "TAPICERÍA (SOFÁ)", "TERMINACIÓN"],
        "ACOMPAÑANTES": ["EBANISTERÍA (ACOMPAÑANTES)", "PINTURA (ACOMPAÑANTES)", "TAPICERÍA (ACOMPAÑANTES)"],
        "CENTRO": ["EBANISTERÍA (CENTRO)", "PINTURA (CENTRO)", "TERMINACIÓN"],
    },
}

# Anatomía típica por tipo de mueble: secciones BASE requeridas y opcionales
# (se usan para la validación de "secciones faltantes" a nivel base; las
# piezas concretas viven en SUB_PARTES_POR_TIPO).
# Las secciones usan los nombres canónicos de SECCIONES_VALIDAS (alineados
# al Excel: herrajes, iluminación y cola de pato viven dentro de TERMINACIÓN).
ANATOMIA_POR_TIPO: dict[str, dict] = {
    "cama": {
        "etiqueta": "cama",
        "secciones": ["EBANISTERÍA", "TENDIDO", "PINTURA", "TERMINACIÓN", "TAPICERÍA"],
        "opcionales": ["NOCHEROS"],
    },
    "nochero": {
        "etiqueta": "mesa de noche / velador",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "closet": {
        "etiqueta": "closet / armario",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "armario": {
        "etiqueta": "armario / ropero",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "tocador": {
        "etiqueta": "tocador / peinador",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "sala": {
        "etiqueta": "mueble de sala",
        "secciones": ["EBANISTERÍA", "PINTURA", "TAPICERÍA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "comedor": {
        "etiqueta": "mueble de comedor",
        "secciones": ["EBANISTERÍA", "PINTURA", "TAPICERÍA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "escritorio": {
        "etiqueta": "escritorio / pupitre",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "rack_tv": {
        "etiqueta": "rack / mueble de TV",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "libreria": {
        "etiqueta": "librería / estantería",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
    "mueble_bano": {
        "etiqueta": "mueble de baño",
        "secciones": ["EBANISTERÍA", "PINTURA", "TERMINACIÓN"],
        "opcionales": [],
    },
}

# Mano de obra típica por sección (líneas dentro de la sección, estilo Excel)
LABOR_POR_SECCION: dict[str, str] = {
    "EBANISTERÍA": "HECHURA / PREPARADO de ebanistería",
    "TENDIDO": "HECHURA de tendido / somier",
    "PINTURA": "PREPARADO + PINTURA / ACABADO (pistolada)",
    "TAPICERÍA": "TAPIZADO / HECHURA de tapicería",
    "TERMINACIÓN": "MONTAJE / EMBALAJE / COLA DE PATO (incluye herrajes e iluminación)",
    "NOCHEROS": "HECHURA / PREPARADO de nocheros",
}

# Vocabulario de preguntas que el motor de costos SABE consumir.
VOCABULARIO_PREGUNTAS: dict[str, str] = {
    "dimensiones": "Medidas del mueble (ancho, largo, alto, fondo) en metros",
    "material_principal": "Material principal del cuerpo: pino, mdf, melamina, triplex, madera_maciza",
    "espesor_tablero": "Espesor del tablero en mm: 15, 18, 25",
    "acabado": "Tipo de acabado: pintura, laca, poliuretano, melamina, enchapado, natural",
    "herrajes": "Herrajes: bisagras, correderas, minifix, tornillos, tarugos, pistones, ruedas, jaladeras",
    "tiene_tapizado": "¿Tiene partes tapizadas?",
    "tiene_espuma": "¿Lleva espuma o relleno?",
    "tiene_vidrio": "¿Incluye vidrio o espejos?",
    "tiene_metal": "¿Incluye piezas metálicas (tubos, platinas, estructura interna)?",
    "tiene_led": "¿Lleva iluminación LED?",
    "tiene_espejos": "¿Incluye espejos?",
    "estructura_reforzada": "Refuerzo de estructura: liviana, normal, reforzada",
    "piezas_cnc": "¿Hay piezas que requieren CNC?",
    "piezas_torno": "¿Hay piezas que requieren torno?",
    "piezas_doblado": "¿Hay piezas que requieren doblado de metal?",
    "piezas_curvas": "¿Hay piezas curvas?",
    "partes_ocultas": "Materiales, herrajes o procesos ocultos que el vendedor conoce",
    "medidas_conocidas": "¿Conoce las medidas finales?",
}


@dataclass
class FurnitureAttributes:
    """
    Atributos del mueble usados para buscar estructuras históricas similares.

    En el Modo Manual los construye el propio ERP a partir del JSON pegado
    (tipo_mueble) o de la receta de un producto similar.
    """
    tipo_mueble: str                    # Ver TIPOS_MUEBLE_VALIDOS
    familia_probable: Optional[str] = None
    estilo_general: Optional[str] = None
    tipo_patas: Optional[str] = None
    tiene_tapiceria: bool = False
    tiene_luces: bool = False
    nivel_confianza: float = 1.0
    observaciones: Optional[str] = None
    atributos_extra: dict = field(default_factory=dict)
    estructura_propuesta: list[dict] = field(default_factory=list)
    percepcion: Optional[str] = None
    dimensiones_referencia: dict = field(default_factory=dict)
    preguntas_faltantes: list = field(default_factory=list)

    def get_extra(self, key: str, default=None):
        return self.atributos_extra.get(key, default)

    def tiene_nocheros(self) -> bool:
        return bool(self.atributos_extra.get("tiene_nocheros", False))

    def tiene_espejo(self) -> bool:
        return bool(self.atributos_extra.get("tiene_espejo", False))

    def tiene_cajones(self) -> bool:
        return bool(self.atributos_extra.get("tiene_cajones", False))

    def cantidad_puertas(self) -> Optional[int]:
        val = self.atributos_extra.get("cantidad_puertas_aproximada")
        return int(val) if val is not None else None

    def cantidad_puestos(self) -> Optional[int]:
        val = self.atributos_extra.get("cantidad_puestos_aproximada")
        return int(val) if val is not None else None

    def to_vector(self) -> list[float]:
        """Vector numérico normalizado para la similitud de coseno (8 posiciones)."""
        estilo = (self.estilo_general or "").lower()
        familia = (self.familia_probable or "").lower()
        patas = (self.tipo_patas or "").lower()

        extras_activos = sum(
            1 for k in ("tiene_nocheros", "tiene_espejo", "tiene_cajones",
                        "cantidad_puertas_aproximada", "cantidad_puestos_aproximada")
            if self.atributos_extra.get(k)
        )

        return [
            1.0 if self.tiene_tapiceria else 0.0,
            1.0 if self.tiene_luces else 0.0,
            1.0 if (self.tiene_espejo() or self.tiene_espejo()) else 0.0,
            1.0 if (self.tiene_nocheros() or self.tiene_cajones()) else 0.0,
            0.0 if patas in ("", "sin_patas") else (0.5 if patas == "madera" else 1.0),
            0.0 if estilo in ("", "moderno") else (0.5 if estilo == "rustico" else 1.0),
            0.0 if familia in ("", "melamina") else (0.5 if familia in ("mdf", "mdf_laqueado") else (0.75 if familia == "tapizada" else 1.0)),
            min(1.0, extras_activos / 4.0),
        ]
