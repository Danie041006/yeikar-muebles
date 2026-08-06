"""
gemini_vision_provider.py
==========================
Implementación concreta del VisionProvider usando la API de Google Gemini.
Soporta CUALQUIER tipo de mueble que fabrica YEIKAR.

Reutiliza la lógica de parsing y los prompts de gpt_vision_provider para
garantizar salida idéntica (mismo JSON, mismos campos, mismos tipos).

Configuración requerida en .env:
  GOOGLE_GENAI_API_KEY=...   (o GOOGLE_API_KEY / GEMINI_API_KEY)
  GEMINI_VISION_MODEL=gemini-2.5-flash
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from app.modules.quotes.vision_provider import (
    VisionProvider,
    FurnitureAttributes,
    PreguntaFaltante,
    TIPOS_MUEBLE_VALIDOS,
    FAMILIAS_VALIDAS,
    ESTILOS_VALIDOS,
    PATAS_VALIDAS,
)

# Reutilizamos las funciones de parsing y prompts de GPT
from app.modules.quotes.gpt_vision_provider import (
    _load_prompt,
    _load_preguntas_prompt,
    _parse_attributes,
    _parse_preguntas,
    _fallback_attrs,
    _formatear_datos_proyecto,
    _CAMPOS_COMUNES,
)

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class GeminiVisionProvider(VisionProvider):
    """Proveedor de visión usando Google Gemini (gemini-2.5-flash / pro)."""

    def __init__(self):
        if not _GENAI_AVAILABLE:
            raise ImportError("google-genai no está instalado. Ejecuta: pip install google-genai")

        api_key = os.getenv("GOOGLE_GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_GENAI_API_KEY (o GOOGLE_API_KEY / GEMINI_API_KEY) no está configurada en el entorno."
            )

        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
        self._system_prompt = _load_prompt()
        self._preguntas_prompt = _load_preguntas_prompt()

    async def analyze(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        contexto_adicional: Optional[str] = None,
        datos_proyecto: Optional[dict] = None,
    ) -> FurnitureAttributes:
        """
        Analiza la imagen de CUALQUIER mueble y retorna atributos estructurados.

        Pasos:
          1. Crea una Part con los bytes de la imagen.
          2. Envía al modelo con response_mime_type="application/json" para JSON puro.
          3. Incluye el contexto textual del vendedor si se suministra.
          4. Incluye las medidas/opciones estructuradas del proyecto (datos_proyecto)
             para que las cantidades de la estructura se calculen para ESAS medidas,
             no para un estándar genérico.
          5. Parsea el JSON con _parse_attributes.
        """
        # Parte de imagen para Gemini
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        texto_usuario = "Analiza este mueble y devuelve el JSON de atributos según las instrucciones."
        if contexto_adicional:
            texto_usuario += f"\nContexto adicional del vendedor para guiar el análisis: {contexto_adicional}"
        if datos_proyecto:
            texto_usuario += _formatear_datos_proyecto(datos_proyecto)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    types.Content(role="user", parts=[image_part, types.Part.from_text(text=texto_usuario)]),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=self._system_prompt,
                    response_mime_type="application/json",
                    max_output_tokens=6000,
                ),
            )

            raw_text = response.text or ""
            logger.debug("RAW RESPONSE DEL MODELO GEMINI:\n%s\n%s", raw_text, "=" * 50)
            logger.debug("USAGE: %s", response.usage_metadata if hasattr(response, 'usage_metadata') else 'N/A')
            raw_json = json.loads(raw_text)
            return _parse_attributes(raw_json)

        except json.JSONDecodeError:
            return _fallback_attrs("El modelo no devolvió JSON válido. Requiere revisión humana.")
        except Exception as exc:
            raise RuntimeError(f"Error al llamar a Gemini Vision API: {exc}") from exc

    async def generate_questions(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        contexto_adicional: Optional[str] = None,
        datos_proyecto: Optional[dict] = None,
    ) -> list:
        """
        Genera la lista de PreguntaFaltante que la IA no pudo responder desde la
        imagen pero que SÍ afectan la estructura de costos.

        Reusa la misma imagen + contexto + datos del proyecto y un system prompt
        especializado en comportamiento de ingeniero de producción.
        """
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        texto_usuario = "Analiza la imagen y responde el JSON de preguntas_faltantes."
        if contexto_adicional:
            texto_usuario += f"\nContexto adicional del vendedor para guiar el análisis: {contexto_adicional}"
        if datos_proyecto:
            texto_usuario += _formatear_datos_proyecto(datos_proyecto)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    types.Content(role="user", parts=[image_part, types.Part.from_text(text=texto_usuario)]),
                ],
                config=types.GenerateContentConfig(
                    system_instruction=self._preguntas_prompt,
                    response_mime_type="application/json",
                    max_output_tokens=3000,
                ),
            )

            raw_text = response.text or ""
            raw_json = json.loads(raw_text)
            return _parse_preguntas(raw_json.get("preguntas_faltantes", []))
        except json.JSONDecodeError:
            return []
        except Exception as exc:
            logger.warning("Error al generar preguntas faltantes con Gemini: %s", exc)
            return []