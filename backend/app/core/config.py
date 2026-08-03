from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://yeikar:yeikar123@localhost:5432/yeikar")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "mi-clave-super-secreta")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", 1200))
    LOGIN_MAX_INTENTOS: int = int(os.getenv("LOGIN_MAX_INTENTOS", 5))
    LOGIN_VENTANA_MINUTOS: int = int(os.getenv("LOGIN_VENTANA_MINUTOS", 15))
    LOGIN_MAX_INTENTOS_IP: int = int(os.getenv("LOGIN_MAX_INTENTOS_IP", 30))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", 8))

settings = Settings()

if not settings.DEBUG and (not settings.SECRET_KEY or settings.SECRET_KEY in {"mi-clave-super-secreta", "cambia-esto-en-produccion", "your-secret-key-here"}):
    raise RuntimeError("SECRET_KEY debe configurarse en produccion. Define una clave segura (p.ej. `openssl rand -hex 32`) en la variable de entorno SECRET_KEY.")

