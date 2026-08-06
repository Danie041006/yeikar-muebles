from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.db.base import Base
from app.db.session import engine
from app.core.config import settings
from app.modules.clients.router import router as clientes_router
from app.modules.users.router import router as auth_router
from app.modules.catalogos.router import router as catalogos_router
from app.modules.productos.router import router as productos_router, material_router as materiales_router
from app.modules.proveedores.router import router as proveedores_router
from app.modules.empleados.router import router as empleados_router
from app.modules.quotes.router import router as cotizaciones_router
from app.modules.orders.router import router as pedidos_router
from app.modules.production.router import router as produccion_router
from app.modules.sales.router import router as sales_router, pago_router as pagos_router
from app.modules.gastos.router import router as gastos_router
from app.modules.tasas_cambio.router import router as tasas_router
from app.modules.inventory.router import router as inventario_router
from app.modules.purchases.router import router as compras_router
from app.modules.reports.router import router as reportes_router
from app.modules.reports.cuentas_router import router as cuentas_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.envios.router import router as envios_router
from app.modules.quotes.intelligent_router import router as iqe_router
from app.modules.auditoria.router import router as auditoria_router
app = FastAPI(
    title="YEIKAR API",
    version="0.0.1",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None if not settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)
origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "Welcome to YEIKAR API"}
app.include_router(clientes_router, prefix="/api/v1/cliente", tags=["cliente"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(catalogos_router, prefix="/api/v1/catalogos", tags=["catalogos"])
app.include_router(productos_router, prefix="/api/v1", tags=["productos"])
app.include_router(materiales_router, prefix="/api/v1/material", tags=["materiales"])
app.include_router(proveedores_router, prefix="/api/v1/proveedor", tags=["proveedores"])
app.include_router(empleados_router, prefix="/api/v1/empleado", tags=["empleados"])
app.include_router(cotizaciones_router, prefix="/api/v1/cotizacion", tags=["cotizaciones"])
app.include_router(pedidos_router, prefix="/api/v1/pedido", tags=["pedidos"])
app.include_router(produccion_router, prefix="/api/v1/produccion", tags=["produccion"])
app.include_router(sales_router, prefix="/api/v1/venta", tags=["ventas"])
app.include_router(pagos_router, prefix="/api/v1/pago", tags=["pagos"])
app.include_router(gastos_router, prefix="/api/v1/gasto", tags=["gastos"])
app.include_router(tasas_router, prefix="/api/v1/tasa", tags=["tasas de cambio"])
app.include_router(inventario_router, prefix="/api/v1", tags=["inventario"])
app.include_router(compras_router, prefix="/api/v1", tags=["compras"])
app.include_router(reportes_router, prefix="/api/v1", tags=["reportes"])
app.include_router(cuentas_router, prefix="/api/v1", tags=["cuentas"])
app.include_router(dashboard_router, prefix="/api/v1", tags=["dashboard"])
app.include_router(envios_router, prefix="/api/v1/envio", tags=["envios"])
app.include_router(iqe_router, prefix="/api/v1/intelligent-quotation", tags=["cotización inteligente"])
app.include_router(auditoria_router, prefix="/api/v1/auditoria", tags=["auditoría"])
