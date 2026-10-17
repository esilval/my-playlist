# ADR-0009 — Aislamiento por establecimiento con columna y Row-Level Security

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 98f087b56f02 |
| Fecha     | 2026-10-16 |
| Motivo    | Q6, G2, D1§2 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

Ninguna búsqueda, pedido ni cola de un establecimiento puede verse ni tocarse desde otro (Q6, invariante del brief). Todos los establecimientos comparten base de datos, Redis y servicio de tiempo real.

## Decisión

Toda tabla de negocio lleva establishment_id y tiene una política Row-Level Security en PostgreSQL. El monolito fija el establecimiento del token en cada transacción (SET LOCAL) con un rol sin BYPASSRLS. Las claves y los canales de Redis y las salas de Socket.IO se prefijan con el establecimiento.

## Alternativas descartadas

- Filtro solo en la aplicación: es más simple, pero basta olvidar un filtro en una consulta para romper Q6.
- Un esquema de Postgres por establecimiento: el aislamiento es fuerte, pero las migraciones se multiplican por cada local.

## Consecuencias

- Cada tabla nueva necesita su política RLS; la comprobación de migraciones debe exigirla.
- Los procesos que cruzan establecimientos (cobro, métricas) usan un rol aparte, auditado y fuera de la API pública.
- Las pruebas de aislamiento (Q6) forman parte de la suite de cada feature.
