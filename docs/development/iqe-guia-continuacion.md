# Guía de Continuación — Cotizador Inteligente (IQE)

> **Para Daniel**: Esta guía está pensada para que puedas seguir trabajando
> solo aunque no tengas acceso a la IA. Está escrita con el máximo nivel de
> detalle para que cualquier desarrollador (o tú mismo) pueda entender y
> continuar sin explicaciones adicionales.

---

## ¿Qué es el IQE?

El **Intelligent Quotation Engine (IQE)** permite a los vendedores de YEIKAR
cotizar cualquier mueble personalizado en 5 pasos:

1. Sube una foto del mueble (puede ser del cliente por WhatsApp, de catálogo, etc.)
2. La IA (GPT-4o) extrae los atributos visuales: tipo de mueble, material, estilo, detalles.
3. El vendedor revisa/corrige los atributos (el humano siempre decide).
4. El sistema busca las 3 estructuras históricas más similares.
5. Se genera un borrador de cotización con costos actuales del inventario.
6. El vendedor ajusta dimensiones, materiales y precios y guarda la cotización.

**Principio clave:** `La IA interpreta → El ERP calcula → El humano decide`

---

## Mapa de archivos

```
YEIKAR/
├── backend/
│   └── app/modules/quotes/
│       ├── vision_provider.py          ← Interfaz abstracta VisionProvider + FurnitureAttributes
│       ├── gpt_vision_provider.py      ← Implementación GPT-4o (analiza fotos)
│       ├── similarity_engine.py        ← Motor de similitud coseno (puro Python, sin IA)
│       ├── intelligent_schemas.py      ← Schemas Pydantic de todos los endpoints
│       ├── intelligent_router.py       ← 5 endpoints FastAPI (/api/v1/intelligent-quotation/)
│       ├── model.py                    ← CotizacionAnalisisIA + CotizacionDetalleMaterial
│       └── prompts/
│           └── vision_prompt.md        ← Prompt del sistema para el LLM (editable sin tocar código)
│
├── backend/app/modules/productos/
│   └── model.py                        ← CamaHistoricaAtributos (legacy) + MuebleAtributos (genérico)
│
├── frontend/src/
│   ├── pages/CotizadorInteligente.tsx  ← Página del IQE (flujo de 5 pasos)
│   └── services/iqeService.ts          ← Servicio con las 5 llamadas a la API
│
├── backend/alembic/versions/
│   ├── 530ad3bcdb72_intelligent_quotes.py     ← Tablas originales IQE
│   └── a1b2c3d4e5f6_add_mueble_atributos.py  ← Tabla genérica para todos los muebles
│
└── docs/development/guia-desarrollador.md     ← Documentación técnica completa
```

---

## API del backend — Endpoints IQE

**Base URL:** `POST /api/v1/intelligent-quotation/`

### Paso 1: Analizar imagen
```
POST /analyze-image
Content-Type: multipart/form-data

Campos:
  file              : (File) Imagen JPEG/PNG/WEBP, max 10 MB
  contexto_adicional: (string, opcional) Texto del vendedor para guiar la IA
                      Ej: "Closet melamina 18mm con cierre suave"

Respuesta (FurnitureAttributesOut):
{
  "tipo_mueble": "cama",
  "familia_probable": "tapizada",
  "estilo_general": "moderno",
  "tipo_patas": "madera",
  "tiene_tapiceria": true,
  "tiene_luces": false,
  "nivel_confianza": 0.92,
  "observaciones": "Cama con cabecero alto tapizado en capitoné",
  "atributos_extra": {
    "tiene_nocheros": true,
    "tiene_espejo": false
  },
  "requiere_revision_humana": false
}
```

### Paso 2: Buscar similares
```
POST /find-similar
Content-Type: application/json

{
  "tipo_mueble": "cama",
  "familia_probable": "tapizada",
  "estilo_general": "moderno",
  "tipo_patas": "madera",
  "tiene_tapiceria": true,
  "tiene_luces": false,
  "atributos_extra": {"tiene_nocheros": true, "tiene_espejo": false},
  "top_n": 3
}

Respuesta (FindSimilarResponse):
{
  "resultados": [
    {
      "producto_id": 42,
      "nombre": "CAMA MODELO TAPIZADA 2X2",
      "tipo_mueble": "cama",
      "score": 0.95,
      "score_pct": 95,
      "coincidencias": ["Tapicería", "Estilo moderno", "Patas madera"],
      "diferencias": ["Nocheros"],
      "ancho_base": 1.6,
      "largo_base": 1.9,
      "tiene_receta": true,
      "es_estructura_nueva": false
    }
  ],
  "tipo_mueble_buscado": "cama",
  "hay_resultados": true,
  "mensaje": null
}
```

### Paso 3: Crear borrador
```
POST /create-draft
Content-Type: application/json

{
  "producto_base_id": 42,
  "nuevo_ancho": 1.60,
  "nuevo_largo": 2.00,
  "ganancia_porcentaje": 40,
  "iva_porcentaje": 0,
  "pct_mano_obra": 15,
  "pct_gastos": 10
}

Respuesta (DraftOut): lista de materiales con cantidades escaladas + precio final.
```

### Paso 4: Recalcular (tras ediciones del vendedor)
```
POST /recalculate
Content-Type: application/json

Igual que create-draft pero también acepta array de materiales editados:
{
  "producto_base_id": 42,
  "nuevo_ancho": 1.60,
  "nuevo_largo": 2.00,
  "materiales": [
    {"material_id": 5, "cantidad_calculada": 3.2, "activo": true},
    {"material_id": 8, "cantidad_calculada": 0.5, "activo": false}
  ],
  "ganancia_porcentaje": 40,
  "iva_porcentaje": 16,
  "pct_mano_obra": 15,
  "pct_gastos": 10
}
```

### Paso 5: Finalizar
```
POST /finalize
Content-Type: application/json

{
  "cliente_id": 12,
  "producto_base_id": 42,
  "nuevo_ancho": 1.60,
  "nuevo_largo": 2.00,
  "materiales": [...],
  "ganancia_porcentaje": 40,
  "iva_porcentaje": 0,
  "observaciones": "Tapizado en tela gris"
}

Respuesta: { "cotizacion_id": 99, "total_estimado": 850.00, "mensaje": "OK" }
```

---

## Tipos de mueble soportados

| `tipo_mueble` | ¿Tiene histórico? |
|---|---|
| `cama` | ✅ Sí (63 registros en `cama_historica_atributos`) |
| `closet`, `comedor`, `sala`, `escritorio`, etc. | ⬜ No aún — sistema listo para recibir datos |
| `otro` | Sin histórico |

**¿Qué pasa si no hay histórico?** El sistema responde `hay_resultados: false` con un mensaje
explicativo. El vendedor debe crear la receta manualmente en "Gestión de Productos".

---

## Cómo agregar históricos de un nuevo tipo de mueble

Cuando tengan productos de otro tipo en la BD con sus recetas:

```python
# backend/scripts/importar_atributos_closets.py
from app.db.session import session_local
from app.modules.productos.model import Producto, MuebleAtributos
from app.modules.quotes.vision_provider import FurnitureAttributes

db = session_local()

# Ejemplo: importar un closet existente como plantilla
attrs = FurnitureAttributes(
    tipo_mueble='closet',
    familia_probable='melamina',
    estilo_general='moderno',
    tipo_patas='sin_patas',
    tiene_tapiceria=False,
    tiene_luces=False,
    atributos_extra={
        'tiene_espejo': True,
        'tiene_cajones': True,
        'cantidad_puertas_aproximada': 4,
        'tipo_apertura': 'corredizas',
    },
    nivel_confianza=1.0,
    observaciones=None,
)

db.add(MuebleAtributos(
    producto_id=123,   # ID del producto en la BD
    tipo_mueble='closet',
    familia_probable=attrs.familia_probable,
    estilo_general=attrs.estilo_general,
    tipo_patas=attrs.tipo_patas,
    tiene_tapiceria=attrs.tiene_tapiceria,
    tiene_luces=attrs.tiene_luces,
    atributos_extra=attrs.atributos_extra,
    vector_similitud=attrs.to_vector(),
))
db.commit()
print("✅ Closet importado como plantilla histórica")
```

---

## Cómo funciona el motor de similitud

El `similarity_engine.py` **no usa IA**. Solo matemáticas:

1. Los atributos del mueble se convierten a un vector numérico de 8 dimensiones:
   ```
   [tapiceria, luces, espejo, cajones/nocheros, patas, estilo, familia, complejidad]
   ```
2. Se calcula la **similitud de coseno** entre el vector del mueble nuevo y cada histórico.
3. Se ordenan los resultados y se retorna el Top N.

El umbral `SCORE_MINIMO_CONFIABLE = 0.40` determina cuándo marcar un resultado
como `es_estructura_nueva: true` (advertencia de que es una base aproximada).

---

## Modificar el prompt de la IA (sin tocar código)

El sistema prompt está en:
```
backend/app/modules/quotes/prompts/vision_prompt.md
```

Puedes editar este archivo directamente. Cambios que puedes hacer:
- Agregar un nuevo tipo de mueble a la lista.
- Cambiar los valores aceptados para `familia_probable`.
- Agregar nuevos campos para un tipo específico (ej. `tiene_cajones_internos` para closets).

El código **no necesita cambiarse** porque los campos extra son capturados automáticamente
en `atributos_extra` por `_parse_attributes()` en `gpt_vision_provider.py`.

---

## Cambiar el proveedor de IA

Para cambiar de GPT-4o a Gemini (o cualquier otro):

1. Crea `backend/app/modules/quotes/gemini_vision_provider.py` que herede de `VisionProvider`.
2. Implementa `async def analyze(self, image_bytes, mime_type, contexto_adicional) -> FurnitureAttributes`.
3. En `.env`, cambia: `IQE_VISION_PROVIDER=gemini`

El factory en `intelligent_router.py` se encarga de instanciar el proveedor correcto.

---

## Variables de entorno necesarias

```bash
# En backend/.env
OPENAI_API_KEY=sk-...          # API key de OpenAI
OPENAI_VISION_MODEL=gpt-4o     # Modelo a usar (gpt-4o o gpt-4o-mini para más barato)
IQE_VISION_PROVIDER=gpt        # 'gpt' | 'gemini' (switch de proveedor)
IQE_CONFIANZA_MINIMA=0.70      # Si IA < 70% confianza → requiere_revision_humana: true
```

---

## Flujo en el frontend (CotizadorInteligente.tsx)

La página tiene un estado `paso` que puede ser:
`'upload' → 'validar' → 'similares' → 'borrador' → 'finalizar'`

Cada transición hace exactamente una llamada a la API:
- `upload → validar`: `iqeService.analyzeImage(file, contexto)`
- `validar → similares`: `iqeService.findSimilar(atributos_validados)`
- `similares → borrador`: `iqeService.createDraft(producto_base_id, dimensiones)`
- `borrador → borrador` (recalcular): `iqeService.recalculate(materiales_editados)`
- `borrador → finalizar`: `iqeService.finalize(cliente_id, materiales_finales)`

**Estado importante:**
- `atributos`: Los atributos que detectó la IA, editables por el vendedor en el paso 2.
- `similares`: Lista de Top N de `findSimilar`.
- `similarSeleccionado`: La plantilla base elegida por el vendedor.
- `borrador`: El `DraftOut` con materiales y costos.
- `materialesEditados`: Dict `{material_id: cantidad_editada}` para overrides manuales.
- `dimensiones`: Form con ancho, largo, ganancia, IVA, % mano de obra, % gastos.

---

## Tareas pendientes (próximos pasos)

### Corto plazo
- [ ] **Generación de PDF**: El endpoint `/finalize` ya guarda la cotización pero aún no genera PDF.
      El PDF debe crearse con `reportlab` o `weasyprint` en el backend.
      Ver `backend/app/modules/quotes/intelligent_router.py` → función `finalize_quotation()`.
- [ ] **Mostrar cliente en la lista de cotizaciones**: Añadir columna que indique si fue creada con IA.
      Hay un campo `analisis_id` en `cotizacion_analisis_ia` que sirve para trazar el origen.

### Mediano plazo
- [ ] **Cargar históricos de closets, comedores, etc.**: Una vez que haya productos con recetas para
      esos tipos, usar el script de ejemplo de arriba para registrar sus vectores en `mueble_atributos`.
- [ ] **Botón "Guardar como plantilla"**: Al finalizar la cotización, ofrecer guardar esa combinación
      de atributos + receta como un nuevo producto en el catálogo para futuras cotizaciones.
- [ ] **GeminiVisionProvider**: Implementar y hacer benchmark contra GPT-4o con imágenes reales.

### Largo plazo
- [ ] Integración WhatsApp Business → el cliente manda foto y el vendedor recibe el borrador.
- [ ] Modelo propio fine-tuned con muebles de YEIKAR.

## Directrices de Desarrollo para Productos Nuevos (Customizados)

Cuando un cliente solicita un diseño completamente nuevo que **no existe en el catálogo** (por ejemplo, una mesa o closet con detalles únicos), la IA no encontrará un modelo idéntico. Aquí se explica cómo debe actuar el software para resolver esto de manera automática y limpia:

### 1. Estrategia de Fallback: Plantillas Genéricas por Categoría
En lugar de fallar o devolver una lista vacía cuando el score de similitud es inferior a `0.40`, el backend debe ofrecer un "comodín" o plantilla por defecto para esa categoría de mueble.
* **Cómo implementarlo**: Registra en la base de datos un producto base "comodín" para cada tipo de mueble (ej. `"CAMA GENÉRICA TAPIZADA"`, `"CLOSET GENÉRICO MELAMINA"`).
* Si el motor de similitud devuelve resultados con score bajo o no encuentra coincidencias, el backend debe:
  1. Identificar el `tipo_mueble` y `familia_probable` seleccionados.
  2. Cargar la receta de ese producto base comodín.
  3. Dejar que el vendedor modifique las dimensiones (ancho, largo) y el motor recalculará los costos de forma proporcional usando la receta paramétrica genérica.

### 2. Mensajes del Vendedor como Guía Primaria
El vendedor puede escribir: *"El cliente quiere una cama de 2.0x2.0 de Roble con cabecero sin nocheros"*. 
* **Regla para los desarrolladores**: El texto de guía del vendedor actúa como un filtro que **sobreescribe** lo que la IA detecte visualmente. 
* El prompt de la IA ya está entrenado en [`vision_prompt.md`](file:///home/daniel-castellanos/YEIKAR/backend/app/modules/quotes/prompts/vision_prompt.md) para dar prioridad absoluta a estas indicaciones textuales.

---

## ¿Qué decirle a los desarrolladores? (Instrucciones exactas)

1. **La IA NO calcula precios ni recetas**: Su único rol es estructurar la foto y el texto del vendedor en un JSON de atributos normalizados (`FurnitureAttributes`).
2. **El cálculo es del ERP**: Toda la matemática financiera y el consumo de materiales se realiza en el ERP (`cost_service.py` y `RecipeEngine`) utilizando fórmulas determinísticas y precios reales del inventario.
3. **Validación Humana Obligatoria**: El paso 2 (pantalla de confirmación de atributos) no es opcional. El vendedor debe validar lo que interpretó la IA antes de consultar la base de datos de similitud.
4. **Cargar los comodines de costo**: Asegurarse de que en la base de datos existan las recetas paramétricas bases para cada familia de mueble (melamina, madera sólida, tapizada) para que sirvan de punto de partida para cualquier diseño nuevo.

---

## Troubleshooting rápido

| Problema | Causa | Solución |
|---|---|---|
| `503 Service Unavailable` en `/analyze-image` | `OPENAI_API_KEY` no configurada | Verificar `.env` |
| `hay_resultados: false` para camas | `cama_historica_atributos` vacía | Ejecutar `importar_atributos_historicos.py` |
| Score siempre 0% | Vector del histórico con formato incorrecto | Verificar `vector_similitud` en BD: debe ser lista de 8 floats |
| `requiere_revision_humana: true` | Confianza IA < 70% | Normal si la foto es de baja calidad; el vendedor debe revisar |
| Error TypeScript al compilar | Campo que no existe en el tipo | Revisar interfaces en `iqeService.ts` vs respuestas reales del backend |

---

*Última actualización: Julio 2026*
*Arquitecto: IA + Daniel Castellanos*
