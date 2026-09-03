"""Obtención segura de la IP del cliente.

uvicorn confía en `X-Forwarded-For` por defecto (proxy_headers=True), lo que
permite a un cliente falsificar su IP y evadir rate limits / lockouts de login.
Este helper solo respeta el header cuando el peer real es un proxy de confianza
(listado en FORWARDED_ALLOW_IPS, por defecto: ninguno -> IP real del socket).

Caso serverless (Vercel): el peer es el runtime interno de la plataforma y no
hay una lista estable de IPs del edge. FORWARDED_ALLOW_IPS="*" indica "confiar
en el XFF fijado por el edge de la plataforma" (el cliente no puede alterarlo
ahí porque el edge lo sobreescribe).
"""
from fastapi import Request

from app.core.config import settings


def obtener_ip_cliente(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    confiables = {x.strip() for x in settings.FORWARDED_ALLOW_IPS.split(",") if x.strip()}
    if "*" in confiables or peer in confiables:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return peer
