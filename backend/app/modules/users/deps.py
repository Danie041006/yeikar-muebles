"""
deps.py — Dependencias de autenticación y permisos por módulo.

El modelo de permisos es flexible y se administra desde el panel de
Gestión de Usuarios (sin tocar código):

  - crear/editar roles,
  - marcar/desmarcar qué módulos abre cada rol y si es solo lectura
    (`gestionar=False`) o también escritura (`gestionar=True`),
  - asignar roles a usuarios.

Dueño y Administrador siempre tienen acceso total a todos los módulos
(no necesitan filas en `rol_modulo`).
"""
from typing import Dict, List

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.modules.catalogos.model import RolModulo
from app.modules.users.model import Usuario
from app.modules.users import schemas, service

# Roles con acceso total (definidos por código, no editables desde el panel)
ROLES_SUPER = ("Dueño", "Administrador")
ROLES_ALCANCE_TOTAL = ROLES_SUPER

# Catálogo central de módulos del ERP.
# clave = identificador usado en la tabla `rol_modulo` y en las rutas.
MODULOS_CATALOGO: List[Dict[str, str]] = [
    {"clave": "dashboard", "nombre": "Panel", "descripcion": "Panel principal con los indicadores del negocio."},
    {"clave": "clientes", "nombre": "Clientes", "descripcion": "Registro y gestión de clientes."},
    {"clave": "cotizaciones", "nombre": "Cotizaciones", "descripcion": "Cotizaciones de muebles a medida."},
    {"clave": "cotizaciones_ia", "nombre": "Cotizaciones con IA", "descripcion": "Motor de cotización inteligente (IQE)."},
    {"clave": "pedidos", "nombre": "Pedidos", "descripcion": "Pedidos de clientes."},
    {"clave": "ventas", "nombre": "Ventas, pagos y abonos", "descripcion": "Facturas, cobros, abonos y cuentas por cobrar."},
    {"clave": "produccion", "nombre": "Producción", "descripcion": "Órdenes de producción y kanban por áreas."},
    {"clave": "inventario", "nombre": "Inventario", "descripcion": "Stock, movimientos y alertas."},
    {"clave": "envios", "nombre": "Envíos y despachos", "descripcion": "Despacho y entrega de pedidos."},
    {"clave": "productos", "nombre": "Gestión de productos", "descripcion": "Productos, recetas y costos."},
    {"clave": "materiales", "nombre": "Materiales", "descripcion": "Materiales e insumos."},
    {"clave": "proveedores", "nombre": "Proveedores", "descripcion": "Registro y gestión de proveedores."},
    {"clave": "empleados", "nombre": "Empleados", "descripcion": "Registro y gestión de empleados."},
    {"clave": "gastos", "nombre": "Gastos", "descripcion": "Registro y control de gastos."},
    {"clave": "cuentas", "nombre": "Cuentas y movimientos", "descripcion": "Medios de pago (efectivo, Zelle, bancos), saldos y movimientos de cada cuenta."},
    {"clave": "compras", "nombre": "Compras", "descripcion": "Compras de materiales e insumos."},
    {"clave": "reportes", "nombre": "Reportes financieros", "descripcion": "Pérdidas y ganancias, indicadores."},
    {"clave": "tasas", "nombre": "Tasas de cambio", "descripcion": "Tasas de cambio diarias."},
    {"clave": "catalogos", "nombre": "Configuración de catálogos", "descripcion": "Monedas, unidades, áreas, cargos y demás catálogos."},
    {"clave": "usuarios", "nombre": "Usuarios y privilegios", "descripcion": "Crear usuarios, asignar roles y definir privilegios."},
]

CLAVES_MODULOS = {m["clave"] for m in MODULOS_CATALOGO}

# Catálogos operativos: se pueden consultar para trabajar, pero sus mutaciones
# siguen requiriendo el permiso de gestión del módulo correspondiente.
MODULOS_LECTURA_COMPARTIDA = {"clientes", "productos", "materiales", "tasas", "catalogos"}


# Configura el esquema OAuth2: espera token en la URL /api/auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ------------------------------------------------------------
# Autenticación
# ------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Usuario:
    """
    Valida el token JWT y retorna el usuario autenticado.
    Lanza HTTP 401 si el token es inválido o el usuario no existe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type", "access")
        if username is None or token_type != "access":
            raise credentials_exception
        token_data = schemas.TokenData(nombre_usuario=username)
    except JWTError:
        raise credentials_exception

    user = service.obtener_usuario_por_nombre(db, username=token_data.nombre_usuario)
    if user is None or not user.activo:
        raise credentials_exception
    return user


# ------------------------------------------------------------
# Permisos por módulo
# ------------------------------------------------------------
def es_admin_user(usuario: Usuario) -> bool:
    """True si el usuario tiene un rol con acceso total (Dueño/Administrador)."""
    return any(r.nombre in ROLES_SUPER for r in usuario.roles)


def tiene_alcance_total(usuario: Usuario) -> bool:
    """Indica si el usuario puede consultar registros de toda la operación."""
    return any(r.nombre in ROLES_ALCANCE_TOTAL for r in usuario.roles)


def filtrar_registros_propios(query, columna, usuario: Usuario):
    """Aplica alcance por fila. Los registros históricos NULL quedan reservados a dueños."""
    if tiene_alcance_total(usuario):
        return query
    return query.filter(columna == usuario.id)


def obtener_accesos_usuario(db: Session, usuario: Usuario) -> Dict[str, bool]:
    """Devuelve {modulo: gestionar} agregando todos los roles del usuario."""
    if es_admin_user(usuario):
        return {m["clave"]: True for m in MODULOS_CATALOGO}
    if not usuario.roles:
        return {"dashboard": True}
    rol_ids = [r.id for r in usuario.roles]
    filas = db.query(RolModulo).filter(RolModulo.rol_id.in_(rol_ids)).all()
    accesos: Dict[str, bool] = {}
    for fila in filas:
        if fila.modulo in CLAVES_MODULOS:
            accesos[fila.modulo] = accesos.get(fila.modulo, False) or bool(fila.gestionar)
    accesos["dashboard"] = True
    return accesos


def modulos_accesibles(db: Session, usuario: Usuario) -> List[dict]:
    """Lista de {modulo, gestionar} ordenada según el catálogo (para /me)."""
    accesos = obtener_accesos_usuario(db, usuario)
    return [
        {"modulo": m["clave"], "gestionar": bool(accesos.get(m["clave"], False))}
        for m in MODULOS_CATALOGO
        if m["clave"] in accesos
    ]


def obtener_permisos_rol(db: Session, rol_id: int) -> List[dict]:
    """Estado {modulo, gestionar} de TODOS los módulos del catálogo para un rol."""
    existentes = {
        f.modulo: bool(f.gestionar)
        for f in db.query(RolModulo).filter(RolModulo.rol_id == rol_id).all()
    }
    return [
        {"modulo": m["clave"], "gestionar": bool(existentes.get(m["clave"], False))}
        for m in MODULOS_CATALOGO
    ]


def guardar_permisos_rol(db: Session, rol_id: int, permisos: List[dict]) -> None:
    """Reemplaza los permisos de un rol por los recibidos."""
    vistos = set()
    for permiso in permisos:
        modulo = permiso.get("modulo")
        if modulo not in CLAVES_MODULOS:
            raise HTTPException(status_code=400, detail=f"Módulo desconocido: {modulo}")
        vistos.add(modulo)
    db.query(RolModulo).filter(RolModulo.rol_id == rol_id).delete()
    for permiso in permisos:
        db.add(RolModulo(
            rol_id=rol_id,
            modulo=permiso["modulo"],
            gestionar=bool(permiso.get("gestionar", False)),
        ))
    db.commit()


def require_module(modulo: str, solo_escritura: bool = False):
    """Dependencia reutilizable: exige acceso al módulo para el usuario.

    - GET/HEAD/OPTIONS → basta con tener el módulo (lectura).
    - Otros métodos   → el módulo debe estar con `gestionar=True`.
    - `solo_escritura=True` → las lecturas solo exigen estar autenticado.
    """
    if modulo not in CLAVES_MODULOS:
        raise ValueError(f"Módulo no registrado en el catálogo: {modulo}")

    def _depend(
        request: Request,
        db: Session = Depends(get_db),
        usuario_actual: Usuario = Depends(get_current_user),
    ) -> Usuario:
        es_lectura = request.method in ("GET", "HEAD", "OPTIONS")
        if es_admin_user(usuario_actual):
            return usuario_actual
        if es_lectura and solo_escritura:
            return usuario_actual
        accesos = obtener_accesos_usuario(db, usuario_actual)
        if es_lectura and modulo in MODULOS_LECTURA_COMPARTIDA:
            return usuario_actual
        if modulo not in accesos:
            raise HTTPException(status_code=403, detail="No tienes permisos para acceder a este módulo")
        if not es_lectura and not accesos[modulo]:
            raise HTTPException(status_code=403, detail="No tienes permisos para modificar datos en este módulo")
        return usuario_actual

    return _depend


def es_admin(usuario_actual: Usuario = Depends(get_current_user)) -> Usuario:
    """Dependencia para endpoints exclusivos de Dueño/Administrador."""
    if not es_admin_user(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")
    return usuario_actual
