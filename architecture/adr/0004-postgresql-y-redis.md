# ADR-0004 — PostgreSQL como fuente de verdad y Redis para estado vivo

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 165fd15c102b |
| Fecha     | 2026-10-16 |
| Motivo    | Q1, Q4, Q6, Q2 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

La cola exige operaciones sin carreras (orden de pedidos, cupo de 5 por dispositivo, ventana anti-repetición, límite del propietario) y un historial por local para el relleno (B07). Además los cambios se difunden en menos de 1 s (Q4) y hay que cachear búsquedas (Q1, ADR-0008).

## Decisión

PostgreSQL (RDS) es la fuente de verdad de establecimientos, cuentas, sesiones, colas, historial y suscripciones. Redis (ElastiCache) guarda la caché de búsquedas, el pub/sub de eventos hacia el servicio de tiempo real y los contadores efímeros. Si Redis se pierde, todo lo que importa se reconstruye desde Postgres.

## Alternativas descartadas

- Solo PostgreSQL: es suficiente para el volumen, pero el pub/sub con LISTEN/NOTIFY y la caché en BD cargan la base y suben la latencia.
- Firestore u otra base documental: trae listeners en tiempo real, pero ata a un proveedor y limita las transacciones y las consultas de historial.

## Consecuencias

- Dos almacenes que operar; la regla es que Redis nunca es la única copia de un dato de negocio.
- Las reglas de la cola se aplican dentro de transacciones de Postgres (con bloqueo por sesión), no en Redis.
- Las migraciones de esquema se gestionan con una herramienta única (p. ej. Alembic) desde el monolito.
