# ADR-001: Selección del Stack Tecnológico para YEIKAR ERP

## Fecha
2026-06-04

## Estado
Aceptado

## Contexto
YEIKAR requiere un sistema ERP para gestionar inventario, producción, costos y ventas. Actualmente usan Excel y hay desorden. Necesitamos una solución escalable, fácil de mantener y que pueda ser desarrollada por un equipo pequeño (inicialmente un desarrollador).

## Decisión
Se selecciona el siguiente stack:

| Capa | Tecnología | Justificación |
|------|------------|----------------|
| Backend | Python + FastAPI | Rápido de desarrollar, documentación automática, ideal para lógica de negocio compleja (costos, producción). |
| Base de Datos | PostgreSQL 17 | Confiable, soporta JSON, transacciones ACID, manejo de múltiples monedas y tasas de cambio. |
| Frontend | React + TypeScript + Vite + Tailwind | Interfaz moderna y reactiva, TypeScript para robustez, Vite para velocidad en desarrollo. |
| ORM | SQLAlchemy 2.0 + Alembic | Potente, independiente de la base de datos, migraciones controladas. |
| Autenticación | JWT (python-jose) | Stateless, fácil de integrar con FastAPI. |
| Contenedores | Docker + Docker Compose | Estandariza el entorno de desarrollo, facilita despliegues. |

## Alternativas Consideradas
- **Node.js + Express**: Buena opción, pero Python simplifica el cálculo de costos y reportes.
- **MySQL**: Menos soporte para funciones de monedas y check constraints complejas.
- **Django**: Más pesado, FastAPI es más ligero para una API REST.

## Consecuencias
- Se requiere aprender FastAPI y SQLAlchemy, pero la documentación es extensa.
- El frontend en React/TypeScript tiene una curva de aprendizaje media.
- El uso de Docker facilita el onboarding de nuevos desarrolladores.

## Cumplimiento de Requisitos
- ✅ Escalable: arquitectura modular.
- ✅ Mantenible: código limpio con separación de responsabilidades.
- ✅ Documentación automática (Swagger).
- ✅ Soporte para múltiples monedas.