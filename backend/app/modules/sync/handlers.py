"""Registro de handlers del push offline.

Cada operación que un dispositivo captura sin red se identifica con un `tipo`
(p. ej. `produccion.etapa.estado`) y un `payload` JSON. Aquí se mapea cada
tipo a una función que reutiliza los services del módulo (mismos permisos,
validaciones y auditoría que la vía online):

    handler(db, payload, usuario) -> dict

El dict devuelto puede traer:
  - `entidad`: {"tabla": ..., "id": ..., "id_local": ...} para que el cliente
    resuelva IDs locales de registros creados offline.
  - `detalle`: mensaje legible del resultado.

Para rechazos de negocio (transición inválida, stock, sin permiso) lanzar
`SyncConflicto` o `ValueError`: el motor lo marca como conflicto y el Centro de
Sincronización lo muestra al usuario. Las fases por módulo van agregando
handlers sin tocar el motor.
"""
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.modules.users.model import Usuario


class SyncConflicto(Exception):
    """La operación offline choca con el estado actual del servidor."""


Handler = Callable[[Session, Dict[str, Any], Optional[Usuario]], Dict[str, Any]]

HANDLERS: Dict[str, Handler] = {}


def handler(tipo: str):
    def decorador(fn: Handler) -> Handler:
        HANDLERS[tipo] = fn
        return fn

    return decorador


# ---------------------------------------------------------------------------
# Producción (F2): el taller captura sin red y el push reutiliza los mismos
# service/router que la vía online (permisos, validaciones y auditoría).
# ---------------------------------------------------------------------------
_CLAVES_TECNICAS = {"etapa_id", "pieza_id", "consumo_id", "mano_obra_id", "id_local", "_local_id"}


def _datos_schema(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {clave: valor for clave, valor in payload.items() if clave not in _CLAVES_TECNICAS}


def _entidad(tabla: str, pk: int | str, payload: Dict[str, Any], detalle: str) -> Dict[str, Any]:
    entidad: Dict[str, Any] = {"tabla": tabla, "id": pk}
    if payload.get("id_local"):
        entidad["id_local"] = payload["id_local"]
    return {"entidad": entidad, "detalle": detalle}


@handler("produccion.etapa.estado")
def _etapa_estado(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import service as produccion

    etapa_id = payload.get("etapa_id")
    estado = payload.get("estado")
    if not etapa_id or not estado:
        raise SyncConflicto("La operación no trae etapa_id o estado.")
    etapa = produccion.cambiar_estado_etapa_produccion(db, int(etapa_id), str(estado), usuario)
    if etapa is None:
        raise SyncConflicto("La etapa no existe o no está disponible para este usuario.")
    return {
        "entidad": {"tabla": "etapa_produccion", "id": etapa.id},
        "detalle": f"Etapa #{etapa.id} → {etapa.estado}",
    }


@handler("produccion.etapa.pasar-area")
def _etapa_pasar_area(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    # El cuerpo de este endpoint vive en el router (no en el service): se llama
    # la función directo para no duplicar reglas ni tocar producción.
    from app.modules.production import schemas as prod_schemas
    from app.modules.production.router import pasar_a_area

    etapa_id = payload.get("etapa_id")
    if not etapa_id:
        raise SyncConflicto("La operación no trae etapa_id.")
    esquema = prod_schemas.PasarAAreaRequest(**_datos_schema(payload))
    etapa = pasar_a_area(id=int(etapa_id), payload=esquema, db=db, usuario_actual=usuario)
    return _entidad("etapa_produccion", etapa.id, payload, f"Etapa #{etapa_id} pasó al área {etapa.area_id}")


@handler("produccion.etapa.asignado.agregar")
def _etapa_asignado_agregar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import schemas as prod_schemas
    from app.modules.production.router import agregar_asignado_adicional

    etapa_id = payload.get("etapa_id")
    if not etapa_id:
        raise SyncConflicto("La operación no trae etapa_id.")
    esquema = prod_schemas.AsignadoAdicionalCreate(**_datos_schema(payload))
    asignado = agregar_asignado_adicional(id=int(etapa_id), esquema=esquema, db=db, usuario_actual=usuario)
    return _entidad("etapa_asignado_adicional", asignado.id, payload, f"Empleado agregado a la etapa #{etapa_id}")


@handler("produccion.etapa.asignado.quitar")
def _etapa_asignado_quitar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production.router import quitar_asignado_adicional

    etapa_id = payload.get("etapa_id")
    empleado_id = payload.get("empleado_id")
    if not etapa_id or not empleado_id:
        raise SyncConflicto("La operación no trae etapa_id o empleado_id.")
    quitar_asignado_adicional(id=int(etapa_id), empleado_id=int(empleado_id), db=db, usuario_actual=usuario)
    return {"detalle": f"Empleado {empleado_id} quitado de la etapa #{etapa_id}"}


@handler("produccion.pieza.actualizar")
def _pieza_actualizar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import schemas as prod_schemas
    from app.modules.production import service as produccion

    pieza_id = payload.get("pieza_id")
    if not pieza_id:
        raise SyncConflicto("La operación no trae pieza_id.")
    pieza = produccion.actualizar_pieza_orden(db, int(pieza_id), prod_schemas.PiezaOrdenUpdate(**_datos_schema(payload)), usuario)
    if pieza is None:
        raise SyncConflicto("La pieza no existe o no está disponible para este usuario.")
    return _entidad("orden_pieza", pieza.id, payload, f"Pieza #{pieza.id} actualizada")


@handler("produccion.consumo.registrar")
def _consumo_registrar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import schemas as prod_schemas
    from app.modules.production import service as produccion

    consumo = produccion.crear_consumo_material(db, prod_schemas.ConsumoMaterialCreate(**_datos_schema(payload)), usuario)
    return _entidad("consumo_material", consumo.id, payload, f"Consumo #{consumo.id} registrado")


@handler("produccion.consumo.confirmar")
def _consumo_confirmar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import schemas as prod_schemas
    from app.modules.production import service as produccion

    consumo_id = payload.get("consumo_id")
    if not consumo_id:
        raise SyncConflicto("La operación no trae consumo_id.")
    if int(consumo_id) < 0:
        raise SyncConflicto("Este consumo todavía no existe en el servidor; confírmalo al reconectar.")
    consumo = produccion.confirmar_consumo_material(db, int(consumo_id), prod_schemas.ConsumoConfirmarCreate(**_datos_schema(payload)), usuario)
    return _entidad("consumo_material", consumo.id, payload, f"Consumo #{consumo.id} confirmado")


@handler("produccion.consumo.eliminar")
def _consumo_eliminar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import service as produccion

    consumo_id = payload.get("consumo_id")
    if not consumo_id:
        raise SyncConflicto("La operación no trae consumo_id.")
    if int(consumo_id) < 0:
        raise SyncConflicto("Este consumo solo existe en el dispositivo; no se puede eliminar en el servidor.")
    if not produccion.eliminar_consumo_material(db, int(consumo_id), usuario):
        raise SyncConflicto("El consumo ya no existe en el servidor.")
    return {"detalle": f"Consumo #{consumo_id} eliminado"}


@handler("produccion.mano-obra.registrar")
def _mano_obra_registrar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import schemas as prod_schemas
    from app.modules.production import service as produccion

    mano = produccion.crear_mano_obra(db, prod_schemas.ManoObraCreate(**_datos_schema(payload)), usuario)
    return _entidad("mano_obra", mano.id, payload, f"Mano de obra #{mano.id} registrada")


@handler("produccion.mano-obra.eliminar")
def _mano_obra_eliminar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.production import service as produccion

    mano_id = payload.get("mano_obra_id")
    if not mano_id:
        raise SyncConflicto("La operación no trae mano_obra_id.")
    if int(mano_id) < 0:
        raise SyncConflicto("Esta mano de obra solo existe en el dispositivo; no se puede eliminar en el servidor.")
    if not produccion.eliminar_mano_obra(db, int(mano_id), usuario):
        raise SyncConflicto("La mano de obra ya no existe en el servidor.")
    return {"detalle": f"Mano de obra #{mano_id} eliminada"}


# ---------------------------------------------------------------------------
# Clientes / Cotizaciones / Pedidos (F3)
# ---------------------------------------------------------------------------
def _sin(payload: Dict[str, Any], *claves: str) -> Dict[str, Any]:
    return {clave: valor for clave, valor in payload.items() if clave not in claves}


@handler("cliente.crear")
def _cliente_crear(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.clients import schemas as cli_schemas
    from app.modules.clients import service as clientes

    cliente = clientes.create_client(db, cli_schemas.ClientCreate(**_datos_schema(payload)), usuario)
    return _entidad("cliente", cliente.id, payload, f"Cliente #{cliente.id} creado")


@handler("cliente.actualizar")
def _cliente_actualizar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.clients import schemas as cli_schemas
    from app.modules.clients import service as clientes

    cliente_id = payload.get("cliente_id")
    if not cliente_id:
        raise SyncConflicto("La operación no trae cliente_id.")
    cliente = clientes.update_client(db, int(cliente_id), cli_schemas.ClientUpdate(**_sin(_datos_schema(payload), "cliente_id")), usuario)
    if cliente is None:
        raise SyncConflicto("El cliente no existe o no está disponible para este usuario.")
    return _entidad("cliente", cliente.id, payload, f"Cliente #{cliente.id} actualizado")


@handler("cliente.eliminar")
def _cliente_eliminar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.clients import service as clientes

    cliente_id = payload.get("cliente_id")
    if not cliente_id:
        raise SyncConflicto("La operación no trae cliente_id.")
    if not clientes.delete_client(db, int(cliente_id), usuario):
        raise SyncConflicto("El cliente ya no existe en el servidor.")
    return {"detalle": f"Cliente #{cliente_id} eliminado"}


@handler("cotizacion.crear")
def _cotizacion_crear(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.quotes import schemas as cot_schemas
    from app.modules.quotes import service as cotizaciones

    cotizacion = cotizaciones.crear_cotizacion(db, cot_schemas.CotizacionCreate(**_datos_schema(payload)), usuario)
    return _entidad("cotizacion", cotizacion.id, payload, f"Cotización #{cotizacion.id} creada")


@handler("cotizacion.actualizar")
def _cotizacion_actualizar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.quotes import schemas as cot_schemas
    from app.modules.quotes import service as cotizaciones

    cotizacion_id = payload.get("cotizacion_id")
    if not cotizacion_id:
        raise SyncConflicto("La operación no trae cotizacion_id.")
    cotizacion = cotizaciones.actualizar_cotizacion(db, int(cotizacion_id), cot_schemas.CotizacionUpdate(**_sin(_datos_schema(payload), "cotizacion_id")), usuario)
    if cotizacion is None:
        raise SyncConflicto("La cotización no existe o no está disponible para este usuario.")
    return _entidad("cotizacion", cotizacion.id, payload, f"Cotización #{cotizacion.id} actualizada")


@handler("cotizacion.eliminar")
def _cotizacion_eliminar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.quotes import service as cotizaciones

    cotizacion_id = payload.get("cotizacion_id")
    if not cotizacion_id:
        raise SyncConflicto("La operación no trae cotizacion_id.")
    if not cotizaciones.eliminar_cotizacion(db, int(cotizacion_id), usuario):
        raise SyncConflicto("La cotización ya no existe en el servidor.")
    return {"detalle": f"Cotización #{cotizacion_id} eliminada"}


@handler("pedido.actualizar")
def _pedido_actualizar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.orders import schemas as ped_schemas
    from app.modules.orders import service as pedidos

    pedido_id = payload.get("pedido_id")
    if not pedido_id:
        raise SyncConflicto("La operación no trae pedido_id.")
    pedido = pedidos.actualizar_pedido(db, int(pedido_id), ped_schemas.PedidoUpdate(**_sin(_datos_schema(payload), "pedido_id")), usuario)
    if pedido is None:
        raise SyncConflicto("El pedido no existe o no está disponible para este usuario.")
    return _entidad("pedido", pedido.id, payload, f"Pedido #{pedido.id} actualizado")


@handler("pedido.eliminar")
def _pedido_eliminar(db: Session, payload: Dict[str, Any], usuario: Optional[Usuario]) -> Dict[str, Any]:
    from app.modules.orders import service as pedidos

    pedido_id = payload.get("pedido_id")
    if not pedido_id:
        raise SyncConflicto("La operación no trae pedido_id.")
    if not pedidos.eliminar_pedido(db, int(pedido_id), usuario):
        raise SyncConflicto("El pedido ya no existe en el servidor.")
    return {"detalle": f"Pedido #{pedido_id} eliminado"}
