"""Resetear la contraseña de un usuario que no la recuerda.

No existe forma de "ver" la contraseña: se guarda con bcrypt (hash de una sola
vía). Este script escribe un hash nuevo, revoca todas las sesiones y passkeys
del usuario y deja un evento en `audit_event`.

La contraseña NUNCA se pasa como argumento de línea de comandos (quedaría en
el historial del shell y en `ps`). Se teclea en el prompt o se pipea con
`--password-stdin`.

Ejecutar (interactivo, recomendado):
    cd backend && venv/bin/python scripts/reset_password.py --usuario paola

Ejecutar en un servidor, sin dejar rastro en el historial:
    cd backend && venv/bin/python scripts/reset_password.py --usuario paola --actor daniel --password-stdin

Opciones:
    --usuario NOMBRE       Usuario a resetear (obligatorio, case-insensitive)
    --actor NOMBRE         Usuario que autoriza el cambio (queda en auditoría)
    --password-stdin       Lee la contraseña de stdin en vez de preguntarla
    --no-revocar-sesiones  Deja vivas las sesiones/passkeys actuales
    --yes                  No pedir confirmación
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.main  # noqa: F401,E402  (carga todos los modelos y configuración)
from app.db.session import session_local  # noqa: E402

LARGO_MINIMO = 8


def leer_password(desde_stdin: bool) -> str:
    if desde_stdin:
        # Una sola línea; se recorta el \n final pero no espacios internos.
        valor = sys.stdin.readline().rstrip("\r\n")
    else:
        valor = getpass.getpass("Contraseña nueva: ")
        confirmacion = getpass.getpass("Repite la contraseña: ")
        if valor != confirmacion:
            sys.exit("ERROR: las contraseñas no coinciden.")

    if len(valor) < LARGO_MINIMO:
        sys.exit(f"ERROR: la contraseña debe tener al menos {LARGO_MINIMO} caracteres.")
    return valor


def advertencia_debilidad(password: str, nombre_usuario: str, nombre_visible: str | None = None) -> str | None:
    """Aviso, no bloqueo: la decisión es del dueño del sistema."""
    import re

    p = password.lower()
    candidatos = {nombre_usuario.lower().replace("_", "").replace(".", "")}
    if nombre_visible:
        candidatos.add(nombre_visible.lower().replace(" ", ""))

    # "Paola19872804", "paola.1987": nombre + números.
    inicial = re.match(r"[a-záéíóúñ]+", p)
    if inicial and any(c.startswith(inicial.group()) for c in candidatos if c):
        return "parece un nombre + números (fecha); es fácil de adivinar"
    if any(c and c in p for c in candidatos):
        return "la contraseña contiene el nombre de usuario"
    if any(patron in p for patron in ("1234", "12345", "123456", "qwerty", "password")):
        return "la contraseña contiene una secuencia típica (1234, qwerty...)"
    if any(anio in p for anio in ("19" + str(d) for d in range(50, 100))):
        return "la contraseña contiene un año; es fácil de adivinar"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usuario", required=True, help="Nombre de usuario a resetear")
    parser.add_argument("--actor", default=None, help="Usuario que autoriza (para auditoría)")
    parser.add_argument("--password-stdin", action="store_true", help="Leer la contraseña de stdin")
    parser.add_argument("--no-revocar-sesiones", action="store_true", help="No cerrar sesiones ni passkeys")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación")
    args = parser.parse_args()

    from app.modules.auditoria.service import record_event
    from app.modules.users import service

    db = session_local()
    try:
        usuario = service.obtener_usuario_por_nombre(db, args.usuario)
        if usuario is None:
            print(f"ERROR: no existe el usuario '{args.usuario}'.", file=sys.stderr)
            print("Usuarios disponibles:", file=sys.stderr)
            from app.modules.users.model import Usuario

            for u in db.query(Usuario).order_by(Usuario.nombre_usuario).all():
                estado = "" if u.activo else " (inactivo)"
                print(f"  - {u.nombre_usuario}{estado}", file=sys.stderr)
            return 2

        actor = None
        if args.actor:
            actor = service.obtener_usuario_por_nombre(db, args.actor)
            if actor is None:
                print(f"ERROR: no existe el usuario auditor '{args.actor}'.", file=sys.stderr)
                return 2

        revocar = not args.no_revocar_sesiones
        if not args.yes and not args.password_stdin:
            print(f"Usuario: {usuario.nombre_usuario} (id {usuario.id})")
            print(f"Sesiones y passkeys: {'se revocan' if revocar else 'se dejan vivas'}")
            respuesta = input("¿Resetear la contraseña? [s/N] ").strip().lower()
            if respuesta not in ("s", "si", "sí", "y", "yes"):
                print("Cancelado.")
                return 1

        password = leer_password(args.password_stdin)

        aviso = advertencia_debilidad(password, usuario.nombre_usuario, usuario.nombre)
        if aviso:
            print(f"AVISO: {aviso}. Recomendado cambiarla al primer ingreso.", file=sys.stderr)

        usuario.password_hash = service.obtener_password_hash(password)
        if revocar:
            service.revocar_todas_las_sesiones(db, usuario.id)

        record_event(
            db,
            actor=actor,
            action="reset_password",
            entity_type="usuario",
            entity_id=usuario.id,
            after={
                "accion": "reset_password_cli",
                "sesiones_revocadas": revocar,
                "actor_cli": args.actor,
            },
        )
        db.commit()

        if not usuario.activo:
            print(f"AVISO: '{usuario.nombre_usuario}' está INACTIVO; no podrá entrar hasta activarlo.", file=sys.stderr)

        print(f"OK: contraseña de '{usuario.nombre_usuario}' actualizada.")
        if revocar:
            print("Sesiones y passkeys revocadas: debe iniciar sesión de nuevo.")
        print("Entrega la clave a la persona por un canal directo, no por el chat del ERP.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
