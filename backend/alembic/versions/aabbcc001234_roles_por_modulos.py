"""roles_por_modulos: tabla rol_modulo, seed de roles y asignaciones iniciales.

Revision ID: aabbcc001234
Revises: 7a1b2c3d4e5f
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "aabbcc001234"
down_revision = "7a1b2c3d4e5f"
branch_labels = None
depends_on = None


def _existe_tabla(conn, nombre: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:t"),
            {"t": nombre},
        ).first()
    )


def _insertar_rol(conn, nombre: str, descripcion: str) -> int:
    fila = conn.execute(text("SELECT id FROM rol WHERE nombre = :n"), {"n": nombre}).first()
    if fila:
        conn.execute(
            text("UPDATE rol SET descripcion = :d, activo = TRUE WHERE id = :id"),
            {"d": descripcion, "id": fila[0]},
        )
        return fila[0]
    resultado = conn.execute(
        text("INSERT INTO rol (nombre, descripcion, activo) VALUES (:n, :d, TRUE) RETURNING id"),
        {"n": nombre, "d": descripcion},
    )
    return resultado.scalar()


def _set_permisos_rol(conn, rol_id: int, permisos: dict) -> None:
    """permisos: {modulo: gestionar}"""
    conn.execute(text("DELETE FROM rol_modulo WHERE rol_id = :rid"), {"rid": rol_id})
    for modulo, gestionar in permisos.items():
        conn.execute(
            text("INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:rid, :m, :g)"),
            {"rid": rol_id, "m": modulo, "g": gestionar},
        )


def _asignar_roles_usuario(conn, nombre_usuario: str, roles: list) -> None:
    fila = conn.execute(
        text("SELECT id FROM usuario WHERE nombre_usuario = :n"), {"n": nombre_usuario}
    ).first()
    if not fila:
        return
    uid = fila[0]
    conn.execute(text("DELETE FROM usuario_rol WHERE usuario_id = :uid"), {"uid": uid})
    for rol_nombre in roles:
        rol_fila = conn.execute(
            text("SELECT id FROM rol WHERE nombre = :n"), {"n": rol_nombre}
        ).first()
        if rol_fila:
            conn.execute(
                text("INSERT INTO usuario_rol (usuario_id, rol_id) VALUES (:u, :r)"),
                {"u": uid, "r": rol_fila[0]},
            )


def upgrade() -> None:
    conn = op.get_bind()

    if not _existe_tabla(conn, "rol_modulo"):
        op.create_table(
            "rol_modulo",
            sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
            sa.Column("rol_id", sa.BigInteger(), sa.ForeignKey("rol.id", ondelete="CASCADE"), nullable=False),
            sa.Column("modulo", sa.String(50), nullable=False),
            sa.Column("gestionar", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.UniqueConstraint("rol_id", "modulo", name="uq_rol_modulo"),
        )
        op.create_index("ix_rol_modulo_rol_id", "rol_modulo", ["rol_id"])
        op.create_index("ix_rol_modulo_modulo", "rol_modulo", ["modulo"])

    # ---- Seed de roles ----
    rol_dueño = _insertar_rol(conn, "Dueño", "Acceso total al ERP y a la configuración del sistema")
    rol_admin = _insertar_rol(conn, "Administrador", "Acceso total, gestión de usuarios y configuración")
    rol_ventas = _insertar_rol(conn, "Ventas", "Cotizaciones, pedidos, facturación, pagos y abonos")
    rol_produccion = _insertar_rol(conn, "Producción", "Órdenes de producción y kanban por áreas")
    rol_inventario = _insertar_rol(conn, "Inventario", "Stock, movimientos, materiales y alertas")
    rol_fletes = _insertar_rol(conn, "Fletes", "Envíos y despachos de pedidos")

    # ---- Permisos por módulo (flexibles desde el panel) ----
    _set_permisos_rol(conn, rol_ventas, {
        "clientes": True, "cotizaciones": True, "cotizaciones_ia": True,
        "pedidos": True, "ventas": True, "productos": False, "tasas": False,
        "envios": False,
    })
    _set_permisos_rol(conn, rol_produccion, {
        "produccion": True, "productos": False, "materiales": False, "empleados": False,
    })
    _set_permisos_rol(conn, rol_inventario, {
        "inventario": True, "productos": False, "materiales": True,
    })
    _set_permisos_rol(conn, rol_fletes, {
        "envios": True, "ventas": False, "empleados": False,
    })

    # ---- Asignaciones iniciales ----
    # daniel (dueño del negocio) → Dueño + Administrador
    _asignar_roles_usuario(conn, "daniel", ["Dueño", "Administrador"])
    # jackson → Ventas (cotizaciones, pedidos, pagos y abonos)
    _asignar_roles_usuario(conn, "jackson", ["Ventas"])
    # carolina → Ventas + Producción + Inventario
    _asignar_roles_usuario(conn, "carolina", ["Ventas", "Producción", "Inventario"])


def downgrade() -> None:
    conn = op.get_bind()
    if _existe_tabla(conn, "rol_modulo"):
        op.drop_index("ix_rol_modulo_modulo", table_name="rol_modulo")
        op.drop_index("ix_rol_modulo_rol_id", table_name="rol_modulo")
        op.drop_table("rol_modulo")
