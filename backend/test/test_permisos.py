#!/usr/bin/env python3
"""
Pruebas del sistema de roles y privilegios por módulo.

Requisitos: PostgreSQL activo con la migración `aabbcc001234` aplicada.
Ejecutar con el venv del backend:
  backend/venv/bin/python -m pytest backend/test/test_permisos.py -v
"""
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import session_local
from app.modules.users import service
from app.modules.users.model import Usuario
from app.modules.catalogos.model import Rol

client = TestClient(app)


def _login(nombre: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": nombre, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _crear_usuario_y_roles(db, nombre: str, password: str, roles: list):
    for nombre_rol in roles:
        if not db.query(Rol).filter(Rol.nombre == nombre_rol).first():
            db.add(Rol(nombre=nombre_rol, descripcion=f"Test {nombre_rol}", activo=True))
            db.commit()
    usr = Usuario(
        nombre_usuario=nombre,
        email=f"{nombre}@test.co",
        password_hash=service.obtener_password_hash(password),
        activo=True,
    )
    db.add(usr)
    db.commit()
    db.refresh(usr)
    for nombre_rol in roles:
        rol = db.query(Rol).filter(Rol.nombre == nombre_rol).first()
        usr.roles.append(rol)
    db.commit()
    return usr


class TestPermisos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db = session_local()
        try:
            cls.admin = _crear_usuario_y_roles(db, "test_admin", "test123", ["Dueño"])
            cls.ventas = _crear_usuario_y_roles(db, "test_ventas", "test123", ["Ventas"])
            cls.fletes = _crear_usuario_y_roles(db, "test_fletes", "test123", ["Fletes"])
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        db = session_local()
        try:
            for nombre in ("test_admin", "test_ventas", "test_fletes"):
                usr = db.query(Usuario).filter(Usuario.nombre_usuario == nombre).first()
                if usr:
                    db.delete(usr)
            db.commit()
        finally:
            db.close()

    def setUp(self):
        self.h_admin = {"Authorization": f"Bearer {_login('test_admin', 'test123')}"}
        self.h_ventas = {"Authorization": f"Bearer {_login('test_ventas', 'test123')}"}
        self.h_fletes = {"Authorization": f"Bearer {_login('test_fletes', 'test123')}"}

    def test_admin_accede_a_todo(self):
        r = self.client.get("/api/v1/gasto/gastos/", headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)

    def test_ventas_accede_a_cotizaciones_pero_no_a_gastos(self):
        self.assertEqual(self.client.get("/api/v1/cotizacion/", headers=self.h_ventas).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/gasto/gastos/", headers=self.h_ventas).status_code, 403)

    def test_fletes_accede_a_envios_no_a_gastos(self):
        self.assertEqual(self.client.get("/api/v1/envio/", headers=self.h_fletes).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/gasto/gastos/", headers=self.h_fletes).status_code, 403)

    def test_iqe_requiere_autenticacion(self):
        r = self.client.post("/api/v1/intelligent-quotation/import-structure",
                             json={"estructura_propuesta": []})
        self.assertEqual(r.status_code, 401)

    def test_admin_manager_usuario_requiere_admin(self):
        self.assertEqual(self.client.get("/api/auth/users").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/users", headers=self.h_ventas).status_code, 403)
        self.assertEqual(self.client.get("/api/auth/users", headers=self.h_admin).status_code, 200)

    def test_permisos_por_modulo_consistente_con_me(self):
        r = self.client.get("/api/auth/me", headers=self.h_ventas)
        self.assertEqual(r.status_code, 200)
        modulos = {m["modulo"]: m["gestionar"] for m in r.json()["modulos"]}
        self.assertIn("cotizaciones", modulos)
        self.assertEqual(modulos["cotizaciones"], True)
        self.assertNotIn("gasto", modulos)

    @property
    def client(self):
        return client


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))