# ADR-0012 — Monorepo y herramientas base

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Superseded by ADR-0013 |
| Fecha         | 2026-10-16 |
| Motivo        | Q8, Q3, G4 |
| Sustituye     | — |
| Propuesto por | `specs/001-alta-establecimiento-qr/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. Sustituye todo texto en
> cursiva. La decide el usuario con `/architecture:review`; hasta entonces, el
> plan que la cita no se puede aprobar.

## Contexto

La feature 001 es la primera con código y fija la estructura que heredan todas las demás. Hay un backend Python/FastAPI (ADR-0002), un servicio de tiempo real en Node (ADR-0005), una SPA React (ADR-0003) e infraestructura como código en AWS (ADR-0006).

## Decisión

Un único repositorio con cuatro raíces: `backend/` (FastAPI, SQLAlchemy 2 asíncrono con asyncpg, Alembic para migraciones, pytest, gestionado con uv, lint con ruff y tipos con mypy), `realtime/` (Node + TypeScript con Socket.IO, vacío hasta que una feature lo necesite), `web/` (Vite + React + TypeScript, Vitest y Testing Library, Playwright para e2e, cliente de API generado desde el OpenAPI del backend) e `infra/` (IaC de AWS). Un docker-compose levanta en local PostgreSQL, Redis y un buzón de correo de pruebas.

## Alternativas descartadas

- Un repositorio por pieza: los despliegues quedan independientes, pero los tipos generados y los cambios que cruzan la API y la web se coordinan entre repositorios.
- Django ORM o SQLModel en lugar de SQLAlchemy 2 + Alembic: S1 ya nombra SQLAlchemy y ADR-0004 propone Alembic; SQLAlchemy da control fino de transacciones y del SET LOCAL de RLS (ADR-0009).
- Poetry o pip-tools en lugar de uv: funcionan, pero uv es más rápido y unifica entorno y bloqueo de dependencias.

## Consecuencias

- Un pipeline de CI con trabajos por raíz que solo corren si cambia su carpeta.
- La herramienta de IaC (Terraform o CDK) se decide cuando la primera feature despliegue; aquí solo se reserva `infra/`.
- Las pruebas de integración del backend corren contra PostgreSQL real (contenedor), nunca SQLite, para probar RLS.
