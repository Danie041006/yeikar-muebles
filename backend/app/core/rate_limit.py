"""Rate limit por IP en memoria, por-proceso (en produccion con 2 workers el total efectivo es ~2x)."""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.client_ip import obtener_ip_cliente

class RateLimitMiddleware(BaseHTTPMiddleware):
    VENTANA_SEGUNDOS = 60
    MAX_CLAVES = 10_000

    def __init__(self, app):
        super().__init__(app)
        self._requests = {}

    def reset(self) -> None:
        """Limpia el contador por IP (lo usan los tests: la suite comparte una
        sola IP y agotaría la ventana de 60s sin esto)."""
        self._requests.clear()

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        if len(self._requests) > self.MAX_CLAVES:
            ahora = time.monotonic()
            vencidas = [
                ip for ip, (inicio, _) in self._requests.items()
                if ahora - inicio >= self.VENTANA_SEGUNDOS
            ]
            for ip in vencidas:
                del self._requests[ip]

        ip = obtener_ip_cliente(request)
        ahora = time.monotonic()
        inicio, contador = self._requests.get(ip, (ahora, 0))
        if ahora - inicio >= self.VENTANA_SEGUNDOS:
            inicio, contador = ahora, 0

        limite = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        if contador >= limite:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas solicitudes. Intenta de nuevo en un momento."},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limite),
                    "X-RateLimit-Remaining": "0",
                },
            )

        self._requests[ip] = (inicio, contador + 1)
        return await call_next(request)
