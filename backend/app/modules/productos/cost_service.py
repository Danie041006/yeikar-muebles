"""
cost_service.py
===============
Servicio de costeo paramétrico para YEIKAR.

Dado un producto y unas dimensiones personalizadas (ancho, largo),
calcula automáticamente las cantidades de cada material según la
regla de escalado definida en la tabla `producto_material`, y luego
aplica márgenes de mano de obra, gastos, ganancia e IVA para obtener
el precio de venta sugerido.

Reglas de escalado implementadas:
  FIJO      → cantidad siempre igual a cantidad_base
  LINEAL    → escala con (nuevo_largo / largo_base)
  AREA      → escala con (nuevo_ancho × nuevo_largo) / (ancho_base × largo_base)
  ESPACIADO → basado en perímetro: (2 × (largo+ancho)) / distancia_pauta_cm × tornillos_por_pieza
  POR_RANGO → saltos discretos según tabla de rangos JSON
  FORMULA   → (reservado para futuro – usa cantidad_base como fallback)

Además se evalúa `condicion_activacion` antes de aplicar la fórmula.
Si la condición no se cumple, la cantidad del material es 0.
"""

from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from app.modules.productos.model import Producto, ProductoMaterial, Material


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _evaluar_condicion(condicion: dict, nuevo_ancho: Decimal, nuevo_largo: Decimal) -> bool:
    """
    Evalúa una condición de activación de la forma:
        {"campo": "nuevo_largo", "op": ">", "valor": 2.0}
    Campos admitidos: "nuevo_largo", "nuevo_ancho"
    Operadores admitidos: ">", ">=", "<", "<=", "==", "!="

    Retorna True si el material debe incluirse, False si debe omitirse.
    Si la condición está mal formada, incluye el material (fail-open para no silenciar datos).
    """
    if not condicion or not isinstance(condicion, dict):
        return True

    campo = condicion.get("campo")
    operador = condicion.get("op")
    valor_referencia = condicion.get("valor")

    if campo is None or operador is None or valor_referencia is None:
        return True  # condición mal formada → incluir

    valor_referencia = Decimal(str(valor_referencia))

    if campo == "nuevo_largo":
        valor_actual = nuevo_largo
    elif campo == "nuevo_ancho":
        valor_actual = nuevo_ancho
    else:
        return True  # campo desconocido → incluir

    ops = {
        ">":  valor_actual >  valor_referencia,
        ">=": valor_actual >= valor_referencia,
        "<":  valor_actual <  valor_referencia,
        "<=": valor_actual <= valor_referencia,
        "==": valor_actual == valor_referencia,
        "!=": valor_actual != valor_referencia,
    }
    return ops.get(operador, True)


def _calcular_por_rango(rangos: list, nuevo_largo: Decimal) -> Decimal | None:
    """
    Busca en la lista de rangos la primera entrada donde nuevo_largo <= rango["max"]
    y devuelve la cantidad correspondiente.
    Si nuevo_largo supera todos los máximos, retorna la cantidad del último rango.
    Retorna None si la lista está vacía o mal formada.
    """
    if not rangos or not isinstance(rangos, list):
        return None

    ultima_cantidad = None
    for rango in rangos:
        try:
            max_val  = Decimal(str(rango["max"]))
            cantidad = Decimal(str(rango["cantidad"]))
            ultima_cantidad = cantidad
            if nuevo_largo <= max_val:
                return cantidad
        except (KeyError, TypeError, ValueError):
            continue

    return ultima_cantidad  # usa el último rango si supera todos los máximos


def _redondear(valor: Decimal, decimales: int = 4) -> Decimal:
    cuantificador = Decimal("0." + "0" * decimales) if decimales > 0 else Decimal("1")
    return valor.quantize(cuantificador, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def calcular_costo_producto(
    db: Session,
    producto_id: int,
    nuevo_ancho: Decimal,
    nuevo_largo: Decimal,
    ganancia_porcentaje: Decimal = Decimal("40"),
    iva_porcentaje: Decimal = Decimal("0"),        # En Colombia el IVA de muebles es 0% por defecto
    pct_mano_obra: Decimal = Decimal("15"),
    pct_gastos: Decimal = Decimal("10"),
) -> dict:
    """
    Calcula el costo total y el precio de venta sugerido para un producto
    con dimensiones personalizadas.

    Parámetros
    ----------
    db                  : Sesión de SQLAlchemy
    producto_id         : ID del producto en la tabla `producto`
    nuevo_ancho         : Ancho deseado en metros
    nuevo_largo         : Largo deseado en metros
    ganancia_porcentaje : Porcentaje de ganancia sobre el costo de producción (ej. 40 → 40%)
    iva_porcentaje      : Porcentaje de IVA (ej. 19 → 19%)
    pct_mano_obra       : Porcentaje de mano de obra sobre el costo de materiales
    pct_gastos          : Porcentaje de gastos indirectos sobre el costo de materiales

    Retorna
    -------
    dict con el desglose completo: materiales, costos parciales y precio de venta.
    """
    # --- 1. Cargar producto --------------------------------------------------
    producto = db.query(Producto).filter(Producto.id == producto_id).first()
    if not producto:
        raise ValueError(f"Producto con id {producto_id} no encontrado")

    ancho_base = Decimal(str(producto.ancho_base)) if producto.ancho_base else Decimal("1.60")
    largo_base = Decimal(str(producto.largo_base)) if producto.largo_base else Decimal("1.90")
    area_base  = ancho_base * largo_base
    area_nueva = nuevo_ancho * nuevo_largo

    # --- 2. Cargar receta de materiales ------------------------------------
    receta: list[ProductoMaterial] = (
        db.query(ProductoMaterial)
        .filter(ProductoMaterial.producto_id == producto_id)
        .all()
    )

    if not receta:
        return {
            "producto_id": producto.id,
            "producto_nombre": producto.nombre,
            "advertencia": "Este producto no tiene receta de materiales definida. Cargue la receta en producto_material.",
            "dimensiones_base": {"ancho": float(ancho_base), "largo": float(largo_base)},
            "dimensiones_nuevas": {"ancho": float(nuevo_ancho), "largo": float(nuevo_largo)},
            "materiales": [],
            "costo_materiales": 0.0,
            "costo_mano_obra": 0.0,
            "costo_gastos": 0.0,
            "costo_produccion": 0.0,
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": 0.0,
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": 0.0,
        }

    # --- 3. Calcular cantidad de cada material ------------------------------
    costo_total_materiales = Decimal("0")
    detalle_materiales = []

    for pm in receta:
        material: Material = pm.material
        tipo          = pm.tipo_escala
        cantidad_base = Decimal(str(pm.cantidad_base))

        # 3a. Verificar condición de activación
        if pm.condicion_activacion:
            if not _evaluar_condicion(pm.condicion_activacion, nuevo_ancho, nuevo_largo):
                # Material no aplica para estas dimensiones
                detalle_materiales.append({
                    "material_id": material.id,
                    "material_nombre": material.nombre,
                    "nombre": material.nombre,  # Alias
                    "tipo_escala": tipo,
                    "condicion_activacion": pm.condicion_activacion,
                    "condicion_cumplida": False,
                    "cantidad_base": float(cantidad_base),
                    "cantidad_calculada": 0.0,
                    "unidad": material.unidad_medida.abreviatura if material.unidad_medida else "",
                    "costo_unitario": float(material.costo_base),
                    "costo_total": 0.0,
                    "costo_subtotal": 0.0,  # Alias
                    "observaciones": pm.observaciones,
                })
                continue

        # 3b. Override fijo
        if pm.es_fijo_override:
            cantidad = cantidad_base
        else:
            # 3c. Aplicar fórmula según tipo_escala
            if tipo == "FIJO":
                cantidad = cantidad_base

            elif tipo == "LINEAL":
                if largo_base == 0:
                    cantidad = cantidad_base
                else:
                    cantidad = cantidad_base * (nuevo_largo / largo_base)

            elif tipo == "AREA":
                if area_base == 0:
                    cantidad = cantidad_base
                else:
                    cantidad = cantidad_base * (area_nueva / area_base)

            elif tipo == "ESPACIADO":
                # Colocación a lo largo del perímetro
                distancia = (
                    Decimal(str(pm.distancia_pauta_cm))
                    if pm.distancia_pauta_cm
                    else Decimal("30")
                )
                por_pieza = pm.tornillos_por_pieza or 1

                perimetro_base = 2 * (largo_base + ancho_base)
                perimetro_nuevo = 2 * (nuevo_largo + nuevo_ancho)

                # Número de piezas = perímetro (en cm) / distancia + 1 (extremo)
                perimetro_nuevo_cm = perimetro_nuevo * 100
                perimetro_base_cm  = perimetro_base  * 100

                piezas_base  = perimetro_base_cm  / distancia + 1
                piezas_nuevas = perimetro_nuevo_cm / distancia + 1

                if piezas_base == 0:
                    cantidad = cantidad_base
                else:
                    # Escala en función de las piezas y la cantidad de tornillos/grapas por pieza
                    cantidad = (piezas_nuevas / piezas_base) * cantidad_base * Decimal(str(por_pieza))

            elif tipo == "POR_RANGO":
                resultado = _calcular_por_rango(pm.rangos, nuevo_largo)
                cantidad = resultado if resultado is not None else cantidad_base

            elif tipo == "FORMULA":
                # Placeholder: si hay fórmula personalizada, usar cantidad_base como fallback
                # (evaluación segura de expresiones matemáticas requiere un parser dedicado)
                cantidad = cantidad_base

            else:
                cantidad = cantidad_base  # tipo desconocido → usa base

        # Asegurar que la cantidad no sea negativa
        cantidad = max(Decimal("0"), _redondear(cantidad))

        costo_mat = _redondear(cantidad * Decimal(str(material.costo_base)), 2)
        costo_total_materiales += costo_mat

        detalle_materiales.append({
            "material_id": material.id,
            "material_nombre": material.nombre,
            "nombre": material.nombre,  # Alias
            "tipo_escala": tipo,
            "condicion_activacion": pm.condicion_activacion,
            "condicion_cumplida": True,
            "cantidad_base": float(cantidad_base),
            "cantidad_calculada": float(cantidad),
            "unidad": material.unidad_medida.abreviatura if material.unidad_medida else "",
            "costo_unitario": float(material.costo_base),
            "costo_total": float(costo_mat),
            "costo_subtotal": float(costo_mat),  # Alias
            "observaciones": pm.observaciones,
        })

    # --- 4. Calcular costos agregados ---------------------------------------
    costo_mano_obra = _redondear(costo_total_materiales * pct_mano_obra / Decimal("100"), 2)
    costo_gastos    = _redondear(costo_total_materiales * pct_gastos    / Decimal("100"), 2)
    costo_produccion = costo_total_materiales + costo_mano_obra + costo_gastos

    precio_sin_iva = _redondear(costo_produccion * (Decimal("1") + ganancia_porcentaje / Decimal("100")), 2)
    precio_con_iva = _redondear(precio_sin_iva   * (Decimal("1") + iva_porcentaje      / Decimal("100")), 2)

    # --- 5. Resultado -------------------------------------------------------
    return {
        "producto_id": producto.id,
        "producto_nombre": producto.nombre,
        "dimensiones_base": {
            "ancho": float(ancho_base),
            "largo": float(largo_base),
        },
        "dimensiones_nuevas": {
            "ancho": float(nuevo_ancho),
            "largo": float(nuevo_largo),
        },
        "materiales": detalle_materiales,
        "materiales_detalle": detalle_materiales,  # Alias
        "resumen_costos": {
            "costo_materiales": float(costo_total_materiales),
            "costo_mano_obra": float(costo_mano_obra),
            "pct_mano_obra": float(pct_mano_obra),
            "costo_gastos": float(costo_gastos),
            "costo_gastos_indirectos": float(costo_gastos),  # Alias
            "pct_gastos": float(pct_gastos),
            "costo_produccion": float(costo_produccion),
            "costo_total": float(costo_produccion),  # Alias
            "ganancia_porcentaje": float(ganancia_porcentaje),
            "precio_sin_iva": float(precio_sin_iva),
            "iva_porcentaje": float(iva_porcentaje),
            "precio_con_iva": float(precio_con_iva),
            "precio_sugerido": float(precio_con_iva),  # Alias
            "precio_venta": float(precio_con_iva),  # Alias
        },
        # Campos de primer nivel para facilidad de consumo desde el frontend
        "costo_materiales": float(costo_total_materiales),
        "costo_mano_obra": float(costo_mano_obra),
        "costo_gastos": float(costo_gastos),
        "costo_gastos_indirectos": float(costo_gastos),  # Alias
        "costo_produccion": float(costo_produccion),
        "costo_total": float(costo_produccion),  # Alias
        "ganancia_porcentaje": float(ganancia_porcentaje),
        "precio_sin_iva": float(precio_sin_iva),
        "iva_porcentaje": float(iva_porcentaje),
        "precio_con_iva": float(precio_con_iva),
        "precio_sugerido": float(precio_con_iva),  # Alias
        "precio_venta": float(precio_con_iva),  # Alias
    }
