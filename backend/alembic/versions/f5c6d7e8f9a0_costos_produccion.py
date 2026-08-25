"""costos de producción: catálogo de precios por área + área Preparación

Revision ID: f5c6d7e8f9a0
Revises: e2d4c6a8b1f3
Create Date: 2026-08-14

Crea la tabla `precio_produccion` (precios de producción por área para la
nómina/destajo), agrega el área "Preparación" si no existe, siembra el
LISTADO DE PRECIOS Y CATEGORÍAS DE MUEBLES (Ebanistería, Preparación,
Pintura, Tapicería) y otorga el módulo `costos_produccion` a los roles
Dueño, Administrador y Producción.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "f5c6d7e8f9a0"
down_revision: Union[str, None] = "e2d4c6a8b1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _obtener_area(conn, nombre: str):
    return conn.execute(text("SELECT id FROM area WHERE nombre = :n"), {"n": nombre}).first()


def _seed_area(conn, area_nombre: str, items: list) -> None:
    fila = _obtener_area(conn, area_nombre)
    if not fila:
        return
    area_id = fila[0]
    for orden, (descripcion, precio) in enumerate(items, start=1):
        conn.execute(
            text(
                "INSERT INTO precio_produccion (area_id, descripcion, precio, activo, orden) "
                "VALUES (:a, :d, :p, TRUE, :o)"
            ),
            {"a": area_id, "d": descripcion, "p": precio, "o": orden},
        )


def upgrade() -> None:
    conn = op.get_bind()

    # Área Preparación (la lista de precios la usa como área propia)
    if not _obtener_area(conn, "Preparación"):
        op.execute(text("INSERT INTO area (nombre) VALUES ('Preparación')"))

    op.create_table(
        "precio_produccion",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column("area_id", sa.BigInteger(), sa.ForeignKey("area.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("producto_id", sa.BigInteger(), sa.ForeignKey("producto.id", ondelete="SET NULL"), nullable=True),
        sa.Column("precio", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.func.now()),
    )
    op.create_index("ix_precio_produccion_area_activo", "precio_produccion", ["area_id", "activo"])

    # ------------------------------------------------------------
    # Seed: LISTADO DE PRECIOS Y CATEGORÍAS DE MUEBLES
    # ------------------------------------------------------------
    ebanisteria = [
        ("CADA PUESTO DE MODULAR", 70000),
        ("ARREGLOS SENCILLOS", 15000),
        ("DORMITORIOS COMPLETOS DE DIFERENTES MEDIDAS", 800000),
        ("CAMA SOLA DIFERENTES MEDIDAS", 300000),
        ("CAMA DOBLE ESPALDAR", 400000),
        ("NOCHERO", 100000),
        ("ESPALDAR CON BASTIDORES", 130000),
        ("ESPALDAR LISO", 80000),
        ("PEINADORA CON SU MARCO Y BUTACO", 350000),
        ("PEINADORA SOLA SIN ESPEJO", 300000),
        ("BUTACO SOLO", 50000),
        ("PUERTA, SOLO HOJA HECHURA", 100000),
        ("PUERTA CON MARCO HECHURA", 150000),
        ("PUERTA Y MARCO CON LA POSTURA", 250000),
        ("POSTURA DE LA PUERTA CON MARCO", 100000),
        ("MESA DE COMEDOR CON TAPA DE 4, 6 Y 8 PUESTOS", 300000),
        ("BASE DE COMEDOR SIN TAPA", 200000),
        ("BASTIDOR DE SILLA DE COMEDOR", 2000),
        ("MARCO SOLO", 50000),
        ("JUEGO DE ESTRUCTURA DE MODULAR DE 5 PUESTOS", 350000),
        ("JUEGO DE MUEBLE RECLONOMATICO DE 7 PUESTOS", 420000),
        ("MESA DE REUNION DIFERENTES MEDIDAS", 350000),
        ("SOMIER 1.0 - 1.40 - 1.60 - 2X2", 100000),
        ("PORTA LAMPARAS", 60000),
        ("SILLAS DE COMEDOR", 60000),
        ("METRO DE COCINA O CLOSET", 250000),
        ("JUEGO DE ESTRUCTURA DE 2 Y 3 POLTRONA REVESTIDA (PUESTO)", 70000),
        ("BASTIDOR CUADRADO PARA ESPALDAR DE MUEBLE", 5000),
        ("TENDIDO NORMAL", 50000),
        ("TENDIDO CON PATAS INCORPORADAS DOBLE PINO", 60000),
        ("LITERA NORMAL CON ESCALERA DUPLEX", 700000),
        ("MUEBLE TV DIFERENTES MEDIDAS", 300000),
        ("POLTRONA DECO", 150000),
        ("PATAS DE MUEBLE", 5000),
        ("COLAPATO", 15000),
        ("MESA DE CENTRO", 100000),
        ("DORMITORIO ATLANTICO", 700000),
        ("BAUL DE", 100000),
        ("BASE PARA MODULAR", 30000),
        ("ESCRITORIO EN L PENDIENTE ACLARAR MEDIDAS", 450000),
        ("BARRA DE EXHIBICION", 400000),
        ("GABETERO", 200000),
        ("PERCHEROS DE DIFERENTES MEDIDAS", 100000),
        ("PUFF", 50000),
        ("CAMA MODELO HERRAJE CON 3 GAVETAS EN EL LARGUERO, BAUL Y GATOS", 480000),
        ("SOFA CAMA", 200000),
        ("BURRO DE CAMA AEREA", 50000),
        ("CAMA DE HERRAJE CON GABETAS EN EL LARGUERO", 480000),
        ("CAMA DE HERRAJE SIN GABETAS EN LOS LARGUEROS", 400000),
    ]

    preparacion = [
        ("CAMA COMPLETA ATLANTICO", 260000),
        ("CAMA SOLA DE 1.60 Y 2X2", 70000),
        ("JUEGO DE DORMITORIO COMPLETO", 230000),
        ("CAJONERIA COMPLETA CON BUTACO", 160000),
        ("CAJONERIA COMPLETA SIN BUTACO", 110000),
        ("PEINADORA SOLA", 60000),
        ("MARCO DE PEINADORA", 20000),
        ("PEINADORA CON MARCO Y BUTACO", 110000),
        ("LITERA", 130000),
        ("BASE DE SOFA CADA PIEZA", 15000),
        ("NOCHERO CON PORTA LAMPARAS", 40000),
        ("NOCHEROS", 35000),
        ("PORTA LAMPARAS", 10000),
        ("JOYERO DE 90 CM", 30000),
        ("BASE DE COMEDOR SOLA", 45000),
        ("MESA DE COMEDOR DE 6 PUESTOS CON TAPA", 60000),
        ("MESA DE COMEDOR DE 8 PUESTOS CON TAPA", 80000),
        ("BASE DE COMEDOR H-S-8 PARA VIDRIO", 35000),
        ("BASE DE COMEDOR CON SOPORTE DE MADERA NORMAL", 45000),
        ("BASE DE COMEDOR 6 PUESTOS 3D CON TAPA MADERA", 60000),
        ("SILLAS DE COMEDOR COMPLETA CON LIJADO", 20000),
        ("SILLAS DE COMEDOR SOLO PATAS", 7000),
        ("BUTACO ALTO", 20000),
        ("BUTACO SOLO PATAS", 10000),
        ("POLTRONA", 35000),
        ("ESCRITORIO GRANDE", 130000),
        ("MESA DE CENTRO", 25000),
        ("JUEGO DE RECIBO RUSTICO SOFA DE 2 POLTRONA Y MESA DE CENTRO", 180000),
        ("MUEBLE PEQUEÑO DE LLAVES", 20000),
        ("JOYERO", 40000),
        ("MULTIMUEBLE", 60000),
        ("MUEBLE TV DE 1.64X1.60", 90000),
        ("MUEBLE SPA", 70000),
        ("ATRIL", 30000),
        ("MUEBLE TV TABLERO", 50000),
        ("MUEBLE CURVO EXHIBIDOR 2.60X1.60", 300000),
        ("EXHIBIDOR DOBLE CARA", 120000),
        ("ESCRITORIO L", 35000),
        ("BASE DE COMEDOR 3D", 15000),
        ("BASE DE POLTRONA PARA TAPIZAR", 120000),
        ("CAMA CUNA CON REJAS", 120000),
        ("ASTA CON BASE PARA BANDERA", 30000),
        ("EXHIBIDOR DOBLE CARA 5", 5000),
        ("CHAPERAS", 1000),
        ("PATAS DE CAMA Y PATAS DE SOFA SOLA", 1000),
        ("CAMAS CON GAVETAS", 80000),
        ("PERCHERO", 30000),
        ("LARGUEROS SOLOS", 20000),
        ("CABECERO SOLO", 30000),
        ("PIECERO SOLO", 10000),
        ("NOCHERO CON CAJA FUERTE", 40000),
        ("DUPLEX", 20000),
        ("1 JUEGO DE ISABELINO CON MESA", 200000),
        ("MULTIMUEBLE PEQUEÑO LLAVES", 20000),
        ("CEIBO CON MARCO", 50000),
        ("PUERTA SOLA", 35000),
        ("PUERTA CON MARCO", 50000),
        ("MUEBLE PEQUEÑO GORRAS", 20000),
        ("BUTACO (AGREGADO A MANO)", 10000),
    ]

    pintura = [
        ("CLOSET RAYADO", 200000),
        ("LITERA", 140000),
        ("CAMA COMPLETA MODELO ATLANTICO", 150000),
        ("CAMA SOLA DE 1.60 Y 2X2", 60000),
        ("DORMITORIO COMPLETO", 140000),
        ("CAJONERIA COMPLETA CON BUTACO", 130000),
        ("CAJONERIA COMPLETA SIN BUTACO", 75000),
        ("MARCO DE PEINADORA", 10000),
        ("PEINADORA SOLA", 60000),
        ("PEINADORA CON MARCO Y BUTACO", 80000),
        ("NOCHERO CON PORTA LAMPARA", 35000),
        ("NOCHERO", 35000),
        ("BASE DE COMEDOR SOLA", 40000),
        ("MESA DE COMEDOR DE 6 PTOS CON TAPA", 70000),
        ("MESA DE COMEDOR DE 8 PTOS CON TAPA", 80000),
        ("BASE DE COMEDOR MODELO H-S-8 PARA VIDRIO", 40000),
        ("SILLA DE COMEDOR SOLO PATAS", 10000),
        ("SILLA DE COMEDOR COMPLETA", 15000),
        ("BUTACO SOLO PATAS", 15000),
        ("BASE DE COMEDOR 2 TONOS", 40000),
        ("MESA DE CENTRO", 25000),
        ("MESA DE CENTRO MARMOLEADA O RALLADA", 30000),
        ("ESCRITORIO GRANDE EN L", 120000),
        ("PUERTA SOLA", 30000),
        ("PUERTA CON MARCO", 40000),
        ("PERCHERO", 30000),
        ("BUTACAS ALTAS", 15000),
        ("BUTACO", 10000),
        ("MUEBLES TV", 60000),
        ("JUEGO DE RECIBO RUSTICOS DE SOFA Y 2 POLTRONAS Y MESA DE CENTRO", 60000),
        ("COCINA EN BLANCO COMPLETA", 200000),
        ("CLOSET MEDIANO", 250000),
        ("CLOSET TV", 70000),
        ("FUSILERA", 30000),
        ("ATRIL", 25000),
        ("PATAS SOLAS DE SOFAS, CAMAS O TENDIDOS", 2000),
        ("CHAPERAS", 5000),
        ("CAMA CUNA CON REJAS", 130000),
        ("PORTA LAMPARAS", 15000),
        ("JOYERO DE 90 CM", 30000),
        ("MUEBLE DE TV TABLERO", 60000),
        ("ASTA CON BASE DE MADERA", 20000),
        ("MUEBLE CURVO EXHIBIDOR 2.60X1.60", 70000),
        ("EXHIBIDOR DOBLE CARA", 30000),
        ("POLTRONA TALLADA", 120000),
        ("POLTRONA NORMAL", 35000),
        ("CABECERO SOLO", 20000),
        ("PIEZERO", 20000),
        ("TENDIDOS CADA PATA DE CAMA", 1000),
        ("PATAS DE MUEBLE MINIMALISTA CADA UNA", 5000),
        ("CAJONES DE MUEBLE IRLANDES", 5000),
    ]

    tapiceria = [
        ("PUFF NORMAL", 40000),
        ("PUFF DE MUEBLE", 70000),
        ("PUFF MODELO BAUL", 120000),
        ("BASTIDOR LISO", 15000),
        ("BASTIDOR CON BANDA", 20000),
        ("SILLAS DE COMEDOR", 40000),
        ("SILLAS DE COMEDOR CAPITONIADAS TODAS", 60000),
        ("SOMIER DE 1-1.40-1.60", 50000),
        ("SOMIER DE 2X2 SI ES DOBLE", 100000),
        ("ESPALDAR CON BASTIDORES", 100000),
        ("CAMAS TAPIZADAS", 230000),
        ("CAMAS CAPITONIADAS", 270000),
        ("POLTRONAS TODAS TAPIZADAS", 130000),
        ("PUESTO DE MODULAR", 120000),
        ("ESPALDAR CON BASTIDORES DE SOMIER", 100000),
        ("SOFA CAMA DE 1,40", 320000),
        ("SILLA RECLINABLE", 270000),
        ("DECORATIVO NORMAL", 10000),
        ("DECORATIVO CON DISEÑO", 20000),
    ]

    _seed_area(conn, "Ebanistería", ebanisteria)
    _seed_area(conn, "Preparación", preparacion)
    _seed_area(conn, "Pintura", pintura)
    _seed_area(conn, "Tapicería", tapiceria)

    # ------------------------------------------------------------
    # Permiso del módulo: Dueño, Administrador y Producción
    # ------------------------------------------------------------
    for rol_nombre in ("Dueño", "Administrador", "Producción"):
        rol = conn.execute(text("SELECT id FROM rol WHERE nombre = :n"), {"n": rol_nombre}).first()
        if rol:
            conn.execute(
                text(
                    "INSERT INTO rol_modulo (rol_id, modulo, gestionar) VALUES (:r, 'costos_produccion', TRUE) "
                    "ON CONFLICT (rol_id, modulo) DO UPDATE SET gestionar = TRUE"
                ),
                {"r": rol[0]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM rol_modulo WHERE modulo = 'costos_produccion'"))
    op.drop_index("ix_precio_produccion_area_activo", table_name="precio_produccion")
    op.drop_table("precio_produccion")
    conn.execute(text("DELETE FROM area WHERE nombre = 'Preparación'"))
