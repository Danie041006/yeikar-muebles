# Punto de entrada de Vercel (Python serverless / ASGI).
# Vercel detecta la variable `app` y monta el FastAPI completo.
from app.main import app  # noqa: E402,F401
