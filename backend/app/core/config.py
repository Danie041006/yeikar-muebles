from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
import secrets

load_dotenv()

def _secret_key() -> str:
    """SECRET_KEY explícita siempre. En desarrollo (DEBUG=true) sin variable,
    se genera una aleatoria por arranque; nunca se usa una clave predecible.
    En producción una SECRET_KEY ausente o débil aborta el arranque."""
    key = os.getenv("SECRET_KEY", "")
    debug = os.getenv("DEBUG", "False").lower() == "true"
    if key:
        return key
    if debug:
        return secrets.token_hex(32)
    return ""

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://yeikar:yeikar123@localhost:5432/yeikar")
    SECRET_KEY: str = _secret_key()
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", 1200))
    LOGIN_MAX_INTENTOS: int = int(os.getenv("LOGIN_MAX_INTENTOS", 5))
    LOGIN_VENTANA_MINUTOS: int = int(os.getenv("LOGIN_VENTANA_MINUTOS", 15))
    LOGIN_MAX_INTENTOS_IP: int = int(os.getenv("LOGIN_MAX_INTENTOS_IP", 30))
    LOGIN_IP_DISTINTAS_PARA_BLOQUEO: int = int(os.getenv("LOGIN_IP_DISTINTAS_PARA_BLOQUEO", 3))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", 8))
    # IPs de proxies de confianza (coma separada). Si está vacío, se ignora
    # el header X-Forwarded-For y se usa la IP real del socket (anti-spoofing).
    FORWARDED_ALLOW_IPS: str = os.getenv("FORWARDED_ALLOW_IPS", "")

settings = Settings()

_KEYS_CONOCIDAS_DEBILES = {
    "mi-clave-super-secreta",
    "cambia-esto-en-produccion",
    "cambia-esto-en-produccion-usa-minimo-32-caracteres",
    "your-secret-key-here",
    "generate-with-openssl-rand-hex-32",
}

if not settings.DEBUG and (
    not settings.SECRET_KEY
    or len(settings.SECRET_KEY) < 32
    or settings.SECRET_KEY in _KEYS_CONOCIDAS_DEBILES
):
    raise RuntimeError("SECRET_KEY debe configurarse en produccion. Define una clave segura (p.ej. `openssl rand -hex 32`) en la variable de entorno SECRET_KEY.")

