"""
vision_provider.py
==================
Interfaz abstracta para los proveedores de visión artificial del
Motor de Cotización Inteligente (Intelligent Quotation Engine).

Principio de diseño: El ERP NUNCA conoce a OpenAI, Gemini ni ningún
proveedor específico de IA. Solo conoce esta interfaz.

Generalización (Jul 2026):
  El MVP inicial solo analizaba camas. Ahora el sistema soporta CUALQUIER
  mueble que fabrica YEIKAR: camas, closets, comedores, salas, etc.

  La estrategia: atributos compartidos (tipo_mueble, familia_probable,
  estilo_general, etc.) + un dict 'atributos_extra' para campos específicos
  de cada tipo. Esto evita tener que cambiar el schema de BD cada vez que
  se agrega un nuevo tipo de mueble.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# Tipos de mueble soportados por el sistema IQE de YEIKAR
TIPOS_MUEBLE_VALIDOS = {
    "cama", "nochero", "closet", "tocador", "armario",
    "sala", "comedor", "escritorio", "rack_tv", "libreria",
    "mueble_bano", "otro",
}

# Familias de material soportadas
FAMILIAS_VALIDAS = {
    "tapizada", "melamina", "madera_solida", "mdf_laqueado", "metalica", "mixta",
}

# Estilos soportados
ESTILOS_VALIDOS = {"moderno", "clasico", "rustico", "minimalista", "industrial"}

# Tipos de patas soportados
PATAS_VALIDAS = {"metal", "madera", "sin_patas", "ruedas"}


@dataclass
class FurnitureAttributes:
    """
    Atributos visuales del mueble extraídos por la IA.

    El ERP usa este objeto para buscar estructuras históricas similares.
    La IA NUNCA calcula precios ni cantidades; solo devuelve atributos.

    Diseño:
      - Atributos comunes: aplican a CUALQUIER mueble (tipo_mueble, familia_probable, etc.)
      - Atributos específicos: guardados en 'atributos_extra' como dict libre.
        Ej: {"tiene_nocheros": True, "tiene_espejo": False} para camas,
            {"cantidad_puertas_aproximada": 4, "tipo_apertura": "corredizas"} para closets.

    Este diseño evita cambiar el schema de BD o el código cada vez que
    YEIKAR empiece a fabricar un nuevo tipo de mueble.
    """
    tipo_mueble: str                    # Ver TIPOS_MUEBLE_VALIDOS
    familia_probable: Optional[str]     # Ver FAMILIAS_VALIDAS o None
    estilo_general: Optional[str]       # Ver ESTILOS_VALIDOS o None
    tipo_patas: Optional[str]           # Ver PATAS_VALIDAS o None
    tiene_tapiceria: bool               # True si alguna parte está tapizada
    tiene_luces: bool                   # True si tiene iluminación integrada
    nivel_confianza: float              # 0.00 - 1.00
    observaciones: Optional[str]        # Descripción visual resumida (max 200 chars)

    # Atributos específicos del tipo de mueble (sin cambiar schema de BD)
    atributos_extra: dict = field(default_factory=dict)
    estructura_propuesta: list[dict] = field(default_factory=list)

    # --- Helpers para acceder a atributos extra ---

    def get_extra(self, key: str, default=None):
        """Obtiene un atributo extra de forma segura."""
        return self.atributos_extra.get(key, default)

    def tiene_nocheros(self) -> bool:
        """Camas: ¿incluye nocheros integrados?"""
        return bool(self.atributos_extra.get("tiene_nocheros", False))

    def tiene_espejo(self) -> bool:
        """Camas, closets: ¿incluye espejo?"""
        return bool(self.atributos_extra.get("tiene_espejo", False))

    def tiene_cajones(self) -> bool:
        """Closets, rack TV, comedores: ¿incluye cajones o gavetas?"""
        return bool(self.atributos_extra.get("tiene_cajones", False))

    def cantidad_puertas(self) -> Optional[int]:
        """Closets, armarios: número aproximado de puertas."""
        val = self.atributos_extra.get("cantidad_puertas_aproximada")
        return int(val) if val is not None else None

    def cantidad_puestos(self) -> Optional[int]:
        """Comedores: número aproximado de puestos/sillas."""
        val = self.atributos_extra.get("cantidad_puestos_aproximada")
        return int(val) if val is not None else None

    def to_vector(self) -> list[float]:
        """
        Convierte los atributos a un vector numérico normalizado para la
        similitud de coseno. Funciona para CUALQUIER tipo de mueble.

        Dimensiones del vector (8 posiciones):
          [0] tapiceria      1.0 / 0.0
          [1] luces          1.0 / 0.0
          [2] espejo         1.0 / 0.0  (espejo o tiene_espejo en extra)
          [3] cajones        1.0 / 0.0  (nocheros o cajones en extra)
          [4] tipo_patas     0.0=sin_patas/None, 0.5=madera, 1.0=metal
          [5] estilo         0.0=moderno/None, 0.5=rustico, 1.0=clasico
          [6] familia        0.0=melamina/None, 0.5=mdf, 0.75=tapizada, 1.0=madera
          [7] complejidad    promedio de atributos extra activos (0.0 - 1.0)
        """
        v_tap = 1.0 if self.tiene_tapiceria else 0.0
        v_luz = 1.0 if self.tiene_luces else 0.0
        v_esp = 1.0 if self.tiene_espejo() else 0.0
        v_caj = 1.0 if (self.tiene_nocheros() or self.tiene_cajones()) else 0.0

        v_pat = 0.0
        if self.tipo_patas == "metal":
            v_pat = 1.0
        elif self.tipo_patas == "madera":
            v_pat = 0.5
        elif self.tipo_patas == "ruedas":
            v_pat = 0.3

        v_est = 0.0
        if self.estilo_general == "clasico":
            v_est = 1.0
        elif self.estilo_general == "rustico":
            v_est = 0.5
        elif self.estilo_general == "industrial":
            v_est = 0.4
        elif self.estilo_general == "minimalista":
            v_est = 0.2

        v_fam = 0.0
        if self.familia_probable == "madera_solida":
            v_fam = 1.0
        elif self.familia_probable == "tapizada":
            v_fam = 0.75
        elif self.familia_probable == "mdf_laqueado":
            v_fam = 0.5
        elif self.familia_probable == "mixta":
            v_fam = 0.4

        # Complejidad: ratio de atributos extra activos sobre total extras
        extra_bool_vals = [v for v in self.atributos_extra.values() if isinstance(v, bool)]
        v_comp = (sum(extra_bool_vals) / len(extra_bool_vals)) if extra_bool_vals else 0.0

        return [v_tap, v_luz, v_esp, v_caj, v_pat, v_est, v_fam, v_comp]


class VisionProvider(ABC):
    """
    Interfaz abstracta para el proveedor de análisis de imágenes.

    Implementaciones concretas:
      - GPTVisionProvider  (OpenAI GPT-4o)
      - GeminiVisionProvider (Google Gemini 2.5 Pro) — pendiente
    """

    @abstractmethod
    async def analyze(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        contexto_adicional: Optional[str] = None,
    ) -> FurnitureAttributes:
        """
        Analiza la imagen y devuelve los atributos visuales del mueble.

        El proveedor DEBE:
          - Identificar correctamente el tipo de mueble antes de cualquier otra cosa.
          - Devolver null para atributos que no puede deducir con certeza.
          - No inventar materiales, cantidades ni costos.
          - Devolver un nivel_confianza honesto.
          - Funcionar para CUALQUIER mueble que YEIKAR fabrica.
        """
        ...
