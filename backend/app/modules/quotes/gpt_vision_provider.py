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

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

_PROMPT_PATH = Path(__file__).parent / "prompts" / "vision_prompt.md"
_PREGUNTAS_PROMPT_PATH = Path(__file__).parent / "prompts" / "preguntas_prompt.md"

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


def _load_preguntas_prompt() -> str:
    if _PREGUNTAS_PROMPT_PATH.exists():
        return _PREGUNTAS_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Devuelve el campo preguntas_faltantes con las preguntas que no puedes "
        "responder de la imagen y que afectan el costo de producción."
    )


def _parse_preguntas(raw: list) -> list[PreguntaFaltante]:
    """
    Convierte el arreglo crudo de preguntas del LLM en PreguntaFaltante.
    Descarta claves que no estén en el vocabulario del motor de costos.
    """
    preguntas: list[PreguntaFaltante] = []
    if not isinstance(raw, list):
        return preguntas

    for p in raw:
        if not isinstance(p, dict):
            continue
        clave = str(p.get("clave", "")).strip()
        if not clave:
            continue
        opciones = p.get("opciones") or []
        if not isinstance(opciones, list):
            opciones = []
        opciones_out = []
        for op in opciones:
            if isinstance(op, dict) and "valor" in op:
                opciones_out.append({
                    "valor": str(op["valor"]),
                    "etiqueta": str(op.get("etiqueta", op["valor"])),
                })
            elif isinstance(op, str):
                opciones_out.append({"valor": op, "etiqueta": op})

        preguntas.append(PreguntaFaltante(
            clave=clave,
            pregunta=str(p.get("pregunta", "")),
            tipo=str(p.get("tipo", "texto")),
            opciones=opciones_out,
            requerida=bool(p.get("requerida", False)),
            por_que=str(p.get("por_que", "")),
        ))
    return preguntas


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

    # --- Percepción del modelo (v2) ---
    percepcion = raw.get("percepcion") or atributos_raw.get("percepcion")
    if percepcion is not None:
        percepcion = str(percepcion)[:500]

    # --- Dimensiones de referencia que asumió el modelo ---
    dims = raw.get("dimensiones_referencia") or {}
    if not isinstance(dims, dict):
        dims = {}
    dimensiones_referencia = {}
    for k in ("ancho", "largo", "alto", "fondo"):
        v = dims.get(k)
        if v is not None:
            try:
                dimensiones_referencia[k] = float(v)
            except (TypeError, ValueError):
                pass

    # --- Preguntas faltantes ---
    preguntas_raw = raw.get("preguntas_faltantes", [])
    preguntas = _parse_preguntas(preguntas_raw)

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
        percepcion=percepcion,
        dimensiones_referencia=dimensiones_referencia,
        preguntas_faltantes=preguntas,
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
        percepcion=None,
        dimensiones_referencia={},
        preguntas_faltantes=[],
    )


def _formatear_datos_proyecto(datos: dict) -> str:
    """
    Convierte los datos estructurados del proyecto en un bloque legible para
    el prompt. Es CRÍTICO: el modelo DEBE calcular las cantidades para estas
    medidas exactas, no para un tamaño estándar.
    """
    lineas = ["", "## DATOS DEL PROYECTO (datos exactos del vendedor)", ""]
    dims = datos.get("dimensiones") or {}
    if isinstance(dims, dict) and dims:
        partes = []
        for k, label in (("ancho", "Ancho"), ("largo", "Largo"), ("alto", "Alto"), ("fondo", "Fondo")):
            v = dims.get(k)
            if v not in (None, "", 0):
                partes.append(f"{label}: {v} m")
        if partes:
            lineas.append(f"- Medidas solicitadas: {' · '.join(partes)}")
            lineas.append("  → Las cantidades de TODA la estructura (cantidad_sugerida) DEBEN calcularse")
            lineas.append("    para estas medidas EXACTAS. NUNCA uses un tamaño estándar o genérico.")

    for clave, etiqueta in (
        ("material_principal", "Material principal"),
        ("espesor_tablero", "Espesor tablero (mm)"),
        ("acabado", "Acabado"),
        ("nivel_detalle", "Nivel de detalle"),
        ("estructura_reforzada", "Estructura"),
    ):
        v = datos.get(clave)
        if v not in (None, "", []):
            lineas.append(f"- {etiqueta}: {v}")

    extras = datos.get("atributos_extra") or {}
    if isinstance(extras, dict) and extras:
        descripcion = ", ".join(
            f"{k.replace('_', ' ')}={'si' if v else 'no'}" if isinstance(v, bool)
            else f"{k.replace('_', ' ')}={v}"
            for k, v in extras.items() if v not in (None, "", False)
        )
        if descripcion:
            lineas.append(f"- Características adicionales: {descripcion}")

    if len(lineas) > 2:
        return "\n".join(lineas)
    return ""


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
        datos_proyecto: Optional[dict] = None,
    ) -> FurnitureAttributes:
        """
        Analiza la imagen de CUALQUIER mueble y retorna atributos estructurados.

        Pasos:
          1. Codifica la imagen en base64.
          2. Envía al modelo con response_format=json_object para garantizar JSON puro.
          3. Incluye el contexto textual del vendedor si se suministra.
          4. Incluye las medidas/opciones estructuradas del proyecto (datos_proyecto)
             para que las cantidades de la estructura se calculen para ESAS medidas,
             no para un estándar genérico.
          5. Parsea el JSON con _parse_attributes.
        """
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{b64}"

        texto_usuario = "Analiza este mueble y devuelve el JSON de atributos según las instrucciones."
        if contexto_adicional:
            texto_usuario += f"\nContexto adicional del vendedor para guiar el análisis: {contexto_adicional}"
        if datos_proyecto:
            texto_usuario += _formatear_datos_proyecto(datos_proyecto)

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
                max_completion_tokens=6000,
            )

            raw_text = response.choices[0].message.content
            logger.debug("RAW RESPONSE DEL MODELO:\n%s\n%s", raw_text, "=" * 50)
            logger.debug("FINISH REASON: %s", response.choices[0].finish_reason)
            logger.debug("USAGE: %s", response.usage)
            raw_json = json.loads(raw_text)
            return _parse_attributes(raw_json)

        except json.JSONDecodeError:
            return _fallback_attrs("El modelo no devolvió JSON válido. Requiere revisión humana.")
        except Exception as exc:
            raise RuntimeError(f"Error al llamar a OpenAI Vision API: {exc}") from exc

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
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{b64}"

        texto_usuario = "Analiza la imagen y responde el JSON de preguntas_faltantes."
        if contexto_adicional:
            texto_usuario += f"\nContexto adicional del vendedor para guiar el análisis: {contexto_adicional}"
        if datos_proyecto:
            texto_usuario += _formatear_datos_proyecto(datos_proyecto)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _load_preguntas_prompt()},
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
                max_completion_tokens=3000,
            )

            raw_text = response.choices[0].message.content
            raw_json = json.loads(raw_text)
            return _parse_preguntas(raw_json.get("preguntas_faltantes", []))
        except json.JSONDecodeError:
            return []
        except Exception as exc:
            logger.warning("Error al generar preguntas faltantes: %s", exc)
            return []
