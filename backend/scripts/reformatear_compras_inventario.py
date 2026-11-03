"""Reformatear las compras de inventario que ya están en caja.

Las entradas de inventario pagadas de una cuenta generan un Gasto y su salida
de caja espejo. Antes quedaban como "Compra TELA CUSCO HIELO x15", sin persona
y sin clasificación. Este script las deja legibles:

    Compra de material: 15 metros de TELA CUSCO HIELO

y completa, cuando están en blanco:
  - `gasto.clasificacion`  → GASTO_FABRICA (GASTO_OFICINA si es de oficina)
  - `movimiento_caja.persona_entidad` → proveedor (o quien registró)
  - `movimiento_caja.usuario_id` / `gasto.creado_por_id` → --usuario-id

No toca conceptos que alguien haya editado a mano (salvo --forzar). Dry-run
por defecto: sin --aplicar solo imprime lo que cambiaría.

Ejecutar:
    cd backend && venv/bin/python scripts/reformatear_compras_inventario.py
    cd backend && venv/bin/python scripts/reformatear_compras_inventario.py \
        --gasto-ids 494,495 --usuario-id 969 --aplicar
"""

import argparse
from datetime import datetime

import app.main  # noqa: F401
from app.db.session import session_local


def _fecha(valor: str | None):
    if not valor:
        return None
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _ids(valor: str | None):
    if not valor:
        return None
    return [int(x) for x in valor.replace(" ", "").split(",") if x]


def main(
    aplicar: bool = False,
    gasto_ids: list[int] | None = None,
    desde=None,
    hasta=None,
    usuario_id: int | None = None,
    forzar: bool = False,
):
    from app.modules.gastos.model import Gasto
    from app.modules.inventory.model import MovimientoInventario
    from app.modules.inventory.service import _descripcion_compra_material
    from app.modules.productos.model import Material
    from app.modules.proveedores.model import Proveedor
    from app.modules.reports.model import MovimientoCaja
    from app.modules.users.model import Usuario

    db = session_local()
    try:
        usuario = None
        if usuario_id:
            usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
            if usuario is None:
                raise SystemExit(f"No existe el usuario #{usuario_id}")
            print(f"Usuario para completar registros: {usuario.nombre or usuario.nombre_usuario} (#{usuario.id})")

        consulta = (
            db.query(MovimientoInventario, Gasto)
            .join(Gasto, Gasto.id == MovimientoInventario.gasto_id)
            .filter(MovimientoInventario.tipo == "ENTRADA")
            .order_by(Gasto.id)
        )
        if gasto_ids:
            consulta = consulta.filter(Gasto.id.in_(gasto_ids))
        if desde:
            consulta = consulta.filter(Gasto.fecha >= desde)
        if hasta:
            consulta = consulta.filter(Gasto.fecha <= hasta)

        cambios = 0
        for mov_inv, gasto in consulta.all():
            material = db.query(Material).filter(Material.id == mov_inv.material_id).first()
            if material is None:
                continue
            unidad = material.unidad_medida.nombre if material.unidad_medida else None
            descripcion = _descripcion_compra_material(material.nombre, mov_inv.cantidad, unidad)

            mov_caja = (
                db.query(MovimientoCaja)
                .filter(MovimientoCaja.referencia == f"Gasto #{gasto.id}")
                .first()
            )

            # Solo se reescribe el texto si sigue siendo el automático viejo
            # ("Compra <material> x<cantidad>"). Un concepto editado a mano se
            # respeta salvo --forzar.
            legacy = f"Compra {material.nombre} x"
            textos_viejos = {gasto.descripcion, mov_caja.concepto if mov_caja else None}
            conservar_texto = not forzar and any(
                t and not t.startswith(legacy) for t in textos_viejos
            )

            clasificacion = (
                "GASTO_OFICINA"
                if (mov_inv.departamento or "").strip().upper() == "OFICINA"
                else "GASTO_FABRICA"
            )

            persona = (mov_inv.proveedor_nombre or "").strip()
            if not persona and mov_inv.proveedor_id:
                persona = (
                    db.query(Proveedor.nombre)
                    .filter(Proveedor.id == mov_inv.proveedor_id)
                    .scalar()
                    or ""
                ).strip()
            if not persona and usuario is not None:
                persona = (usuario.nombre or usuario.nombre_usuario or "").strip()

            cambios_fila = []
            if not conservar_texto and gasto.descripcion != descripcion:
                cambios_fila.append(f"gasto: '{gasto.descripcion}' → '{descripcion}'")
                if aplicar:
                    gasto.descripcion = descripcion
            if gasto.clasificacion != clasificacion:
                cambios_fila.append(f"clasificación: {gasto.clasificacion or '—'} → {clasificacion}")
                if aplicar:
                    gasto.clasificacion = clasificacion
            if usuario and not gasto.creado_por_id:
                cambios_fila.append(f"creado_por: — → #{usuario.id}")
                if aplicar:
                    gasto.creado_por_id = usuario.id

            if mov_caja is not None:
                if not conservar_texto and mov_caja.concepto != descripcion:
                    cambios_fila.append(f"caja.concepto: '{mov_caja.concepto}' → '{descripcion}'")
                    if aplicar:
                        mov_caja.concepto = descripcion
                if not (mov_caja.persona_entidad or "").strip() and persona:
                    cambios_fila.append(f"persona_entidad: — → '{persona}'")
                    if aplicar:
                        mov_caja.persona_entidad = persona
                if usuario and not mov_caja.usuario_id:
                    cambios_fila.append(f"caja.usuario_id: — → #{usuario.id}")
                    if aplicar:
                        mov_caja.usuario_id = usuario.id

            if not cambios_fila:
                continue

            cambios += 1
            print(f"\nGasto #{gasto.id} · {gasto.fecha} · mov.inventario #{mov_inv.id}")
            for linea in cambios_fila:
                print(f"  - {linea}")

        if aplicar:
            db.commit()
            print(f"\n✅ {cambios} compra(s) actualizadas.")
        else:
            print(f"\n(dry-run) {cambios} compra(s) cambiarían. Repite con --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios (sin esto es dry-run)")
    parser.add_argument("--gasto-ids", help="Lista de ids de gasto separados por coma")
    parser.add_argument("--desde", help="Fecha mínima del gasto (YYYY-MM-DD)")
    parser.add_argument("--hasta", help="Fecha máxima del gasto (YYYY-MM-DD)")
    parser.add_argument("--usuario-id", type=int, help="Usuario para completar 'Registrado por' cuando esté vacío")
    parser.add_argument("--forzar", action="store_true", help="Reescribir también textos editados a mano")
    args = parser.parse_args()

    main(
        aplicar=args.aplicar,
        gasto_ids=_ids(args.gasto_ids),
        desde=_fecha(args.desde),
        hasta=_fecha(args.hasta),
        usuario_id=args.usuario_id,
        forzar=args.forzar,
    )
