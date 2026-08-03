"""
gpt_vision_provider.py
=======================
Implementación concreta del VisionProvider usando la API de OpenAI.
Soporta CUALQUIER tipo de mueble que fabrica YEIKAR.

El prompt en vision_prompt.md define los campos esperados para cada tipo.
Este archivo solo se encarga de llamar a la API, parsear el JSON y
construir el objeto FurnitureAttributes genérico.

Configuración requerida en .env:
  OPENAI_API_KEY=sk-...
  OPENAI_VISION_MODEL=gpt-4o
"""

import json
import base64
import os
from pathlib import Path
from typing import Optional

from app.modules.quotes.vision_provider import (
    VisionProvider,
    FurnitureAttributes,
    TIPOS_MUEBLE_VALIDOS,
    FAMILIAS_VALIDAS,
    ESTILOS_VALIDOS,
    PATAS_VALIDAS,
)

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

_PROMPT_PATH = Path(__file__).parent / "prompts" / "vision_prompt.md"

# Campos comunes que siempre se extraen del JSON de la IA
_CAMPOS_COMUNES = {
    "tipo_mueble", "familia_probable", "estilo_general", "tipo_patas",
    "tiene_tapiceria", "tiene_luces", "nivel_confianza", "observaciones",
}


def _load_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Analiza el mueble en la imagen. Responde ÚNICAMENTE con JSON. "
        "Incluye: tipo_mueble, familia_probable, estilo_general, tipo_patas, "
        "tiene_tapiceria, tiene_luces, nivel_confianza, observaciones."
    )


def _parse_attributes(raw: dict) -> FurnitureAttributes:
    """
    Convierte el JSON crudo del LLM en FurnitureAttributes.

    Estrategia:
      - Soporta formato anidado con clave 'atributos' y formato plano heredado.
      - Valida y normaliza los campos comunes.
      - Todos los demás campos del JSON van a 'atributos_extra'.
    """
    # Si viene con el formato anidado, lo extraemos de 'atributos'
    atributos_raw = raw.get("atributos") if isinstance(raw.get("atributos"), dict) else raw

    # --- Validar tipo_mueble ---
    tipo = raw.get("tipo_mueble", atributos_raw.get("tipo_mueble", "otro"))
    if tipo not in TIPOS_MUEBLE_VALIDOS:
        tipo = "otro"

    # --- Validar confianza ---
    try:
        confianza = float(raw.get("nivel_confianza", atributos_raw.get("nivel_confianza", 0.0)))
        confianza = max(0.0, min(1.0, confianza))
    except (TypeError, ValueError):
        confianza = 0.0

    # --- Validar familia ---
    familia = atributos_raw.get("familia_probable")
    if familia not in FAMILIAS_VALIDAS:
        familia = None

    # --- Validar estilo ---
    estilo = atributos_raw.get("estilo_general")
    if estilo not in ESTILOS_VALIDOS:
        estilo = None

    # --- Validar patas ---
    patas = atributos_raw.get("tipo_patas")
    if patas not in PATAS_VALIDAS:
        patas = None

    # --- Tapicería y luces (comunes) ---
    tiene_tapiceria = bool(atributos_raw.get("tiene_tapiceria", False))
    tiene_luces = bool(atributos_raw.get("tiene_luces", False))

    # --- Observaciones ---
    obs_raw = atributos_raw.get("observaciones")
    observaciones = str(obs_raw)[:200] if obs_raw else None

    # --- Atributos extra ---
    extra_nested = atributos_raw.get("atributos_extra")
    if isinstance(extra_nested, dict):
        atributos_extra = {k: v for k, v in extra_nested.items() if v is not None}
    else:
        atributos_extra = {
            k: v
            for k, v in atributos_raw.items()
            if k not in _CAMPOS_COMUNES and v is not None
        }

    # --- Estructura propuesta ---
    estructura_propuesta = raw.get("estructura_propuesta", [])
    if not isinstance(estructura_propuesta, list):
        estructura_propuesta = []

    return FurnitureAttributes(
        tipo_mueble=tipo,
        familia_probable=familia,
        estilo_general=estilo,
        tipo_patas=patas,
        tiene_tapiceria=tiene_tapiceria,
        tiene_luces=tiene_luces,
        nivel_confianza=confianza,
        observaciones=observaciones,
        atributos_extra=atributos_extra,
        estructura_propuesta=estructura_propuesta,
    )


def _fallback_attrs(msg: str) -> FurnitureAttributes:
    """Devuelve atributos vacíos con confianza 0 cuando la IA falla."""
    return FurnitureAttributes(
        tipo_mueble="otro",
        familia_probable=None,
        estilo_general=None,
        tipo_patas=None,
        tiene_tapiceria=False,
        tiene_luces=False,
        nivel_confianza=0.0,
        observaciones=msg[:200],
        atributos_extra={},
        estructura_propuesta=[],
    )


class GPTVisionProvider(VisionProvider):
    """Proveedor de visión usando OpenAI (GPT-4o o compatible)."""

    def __init__(self):
        if not _OPENAI_AVAILABLE:
            raise ImportError("openai no está instalado. Ejecuta: pip install openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no está configurada en el entorno.")
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
        self._system_prompt = _load_prompt()

    async def analyze(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        contexto_adicional: Optional[str] = None,
    ) -> FurnitureAttributes:
        """
        Analiza la imagen de CUALQUIER mueble y retorna atributos estructurados.

        Pasos:
          1. Codifica la imagen en base64.
          2. Envía al modelo con response_format=json_object para garantizar JSON puro.
          3. Incluye el contexto textual del vendedor si se suministra.
          4. Parsea el JSON con _parse_attributes.
        """
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{b64}"

        texto_usuario = "Analiza este mueble y devuelve el JSON de atributos según las instrucciones."
        if contexto_adicional:
            texto_usuario += f"\nContexto adicional del vendedor para guiar el análisis: {contexto_adicional}"

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"},
                            },
                            {
                                "type": "text",
                                "text": texto_usuario,
                            },
                        ],
                    },
                ],
                max_completion_tokens=4000,
                
            )

            raw_text = response.choices[0].message.content
            print(f"🔍 RAW RESPONSE DEL MODELO:\n{raw_text}\n{'='*50}")
            print(f"🔍 FINISH REASON: {response.choices[0].finish_reason}")
            print(f"🔍 USAGE: {response.usage}")
            raw_json = json.loads(raw_text)
            return _parse_attributes(raw_json)

        except json.JSONDecodeError:
            return _fallback_attrs("El modelo no devolvió JSON válido. Requiere revisión humana.")
        except Exception as exc:
            raise RuntimeError(f"Error al llamar a OpenAI Vision API: {exc}") from exc
