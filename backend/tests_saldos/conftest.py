"""Suite aislada: exige PostgreSQL local de pruebas antes de importar la app."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy.orm import Session

url = os.environ.get("TEST_DATABASE_URL", "")
destino = urlparse(url)
if destino.hostname not in {"127.0.0.1", "localhost"} or not destino.path.endswith("_test"):
    raise RuntimeError("Indica TEST_DATABASE_URL local, con una base terminada en _test. Nunca producción.")
os.environ["DATABASE_URL"] = url
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.db.base import Base
from app.db.session import engine


@pytest.fixture(scope="session", autouse=True)
def esquema():
    Base.metadata.create_all(engine)


@pytest.fixture
def db():
    with engine.connect() as conexion:
        transaccion = conexion.begin()
        with Session(bind=conexion, join_transaction_mode="create_savepoint") as sesion:
            yield sesion
        transaccion.rollback()


@pytest.fixture
def negocio(db):
    from datetime import date
    from app.modules.catalogos.model import Moneda, Rol, RolModulo
    from app.modules.clients.model import Client
    from app.modules.orders.model import Pedido
    from app.modules.quotes.model import Cotizacion
    from app.modules.reports.model import MetodoCaja
    from app.modules.sales.model import Venta
    from app.modules.users.model import Usuario

    db.add_all([
        Moneda(id=1, nombre="Pesos", codigo="COP", simbolo="$"),
        Moneda(id=2, nombre="Dólares", codigo="USD", simbolo="US$"),
    ])
    rol = Rol(nombre="Cobros QA")
    db.add(rol)
    db.flush()
    db.add(RolModulo(rol_id=rol.id, modulo="ventas", gestionar=True))
    usuario = Usuario(nombre_usuario="paola_qa", nombre="Paola QA", password_hash="no-login", roles=[rol])
    cliente = Client(nombre="Cliente QA", telefono="555")
    db.add_all([usuario, cliente])
    db.flush()
    db.add_all([MetodoCaja(codigo="USD_QA", nombre="Zelle QA", moneda_id=2),
                MetodoCaja(codigo="COP_QA", nombre="Banco QA", moneda_id=1)])

    def venta(total=7546, moneda_id=2):
        cot = Cotizacion(cliente_id=cliente.id, fecha=date.today(), estado="APROBADA",
                         moneda_id=moneda_id, total_estimado=total, tasa_cambio=4000 if moneda_id == 2 else 1)
        db.add(cot)
        db.flush()
        pedido = Pedido(cotizacion_id=cot.id, cliente_id=cliente.id, fecha=date.today(), estado="APROBADO")
        db.add(pedido)
        db.flush()
        factura = Venta(pedido_id=pedido.id, cliente_id=cliente.id, fecha=date.today(),
                        moneda_id=moneda_id, total=total, tasa_cambio=4000 if moneda_id == 2 else 1,
                        total_en_moneda_base=total * (4000 if moneda_id == 2 else 1))
        db.add(factura)
        db.flush()
        return factura

    db.flush()
    return cliente, usuario, venta


@pytest.fixture
def client(db, negocio):
    from fastapi.testclient import TestClient
    from app.db.session import get_db
    from app.modules.users.deps import get_current_user

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: negocio[1]
    with TestClient(app) as navegador:
        yield navegador
    app.dependency_overrides.clear()
