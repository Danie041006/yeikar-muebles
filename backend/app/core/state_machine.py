"""Máquinas de estado del flujo de producción/ventas.

Cada entidad define las transiciones legales de negocio. Un cambio de estado
fuera de la matriz se rechaza con 400 (no se puede saltar etapas del proceso:
una cotización no se entrega sin fabricarse, una orden cancelada no se revive,
un envío entregado no retrocede).

Flujo de negocio YEIKAR:
  cotización → pedido → producción (etapas por área) → TERMINADO → envío → ENTREGADO
"""

TRANSICIONES_PEDIDO = {
    "COTIZADO": {"APROBADO", "CANCELADO"},
    "APROBADO": {"PRODUCCION", "CANCELADO"},
    "PRODUCCION": {"PAUSADO", "TERMINADO", "CANCELADO"},
    "PAUSADO": {"PRODUCCION", "CANCELADO"},
    "TERMINADO": {"ENTREGADO"},
    "ENTREGADO": set(),
    "CANCELADO": set(),
}

TRANSICIONES_ORDEN_PRODUCCION = {
    "PENDIENTE": {"EN_PRODUCCION", "CANCELADA"},
    "EN_PRODUCCION": {"PAUSADA", "FINALIZADA", "CANCELADA"},
    "PAUSADA": {"EN_PRODUCCION", "CANCELADA"},
    "FINALIZADA": set(),
    "CANCELADA": set(),
}

TRANSICIONES_ETAPA_PRODUCCION = {
    "ASIGNADA": {"EN_PROCESO"},
    "EN_PROCESO": {"PAUSADA", "COMPLETADA"},
    "PAUSADA": {"EN_PROCESO"},
    "COMPLETADA": set(),
}

TRANSICIONES_ENVIO = {
    "PREPARADO": {"EN_TRANSITO"},
    "EN_TRANSITO": {"ENTREGADO", "FALLIDO"},
    "ENTREGADO": set(),
    "FALLIDO": set(),
}


def validar_transicion(transiciones: dict, estado_actual: str, nuevo_estado: str, nombre_entidad: str):
    """Valida un cambio de estado contra la matriz. Lanza ValueError con mensaje claro."""
    permitidos = transiciones.get(estado_actual)
    if permitidos is None:
        raise ValueError(f"Estado '{estado_actual}' no es válido para {nombre_entidad}.")
    if nuevo_estado == estado_actual:
        # Re-marcar el MISMO estado: permitido solo si no es terminal. Un estado
        # terminal (p.ej. ENTREGADO, FINALIZADA, CANCELADA) no se puede re-marcar:
        # antes se aceptaba 200 veces, violando el contrato "terminal".
        if not permitidos:
            raise ValueError(
                f"No se puede cambiar el estado de {nombre_entidad}: el estado '{estado_actual}' es terminal."
            )
        return
    if nuevo_estado not in permitidos:
        if not permitidos:
            raise ValueError(
                f"No se puede cambiar el estado de {nombre_entidad}: el estado '{estado_actual}' es terminal."
            )
        raise ValueError(
            f"Transición no permitida para {nombre_entidad}: '{estado_actual}' → '{nuevo_estado}'. "
            f"Solo se permite: {', '.join(sorted(permitidos))}."
        )
