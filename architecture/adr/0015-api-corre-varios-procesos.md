# ADR-0015 — La API corre con varios procesos

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 8f2cf1826e5d |
| Fecha         | 2026-10-28 |
| Motivo        | Q1, Q2, Q4 |
| Sustituye     | — |
| Propuesto por | `specs/003-pedir-canciones-desde-qr/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

El monolito (FastAPI) corre hoy en un solo proceso de uvicorn, tanto en el compose como en lo que ADR-0006 prevé para ECS Fargate. Python ejecuta el código de un proceso en un solo núcleo a la vez.

La feature 003 mide el límite (T014, `src/perf/client.js`, en local con 8 CPU):
- **Techo de un proceso:** con la petición más barata del cliente (su estado, con la cola vacía), un proceso atiende unas **360 peticiones por segundo**. A 600 por segundo, el p95 sube a 11 s. La API se queda en un núcleo al 100 %, mientras PostgreSQL y Redis van holgados.
- **Lo que pide Q2:** con el ritmo de la hora pico que fija la spec de 003 (1 búsqueda cada 5 minutos y 1 pedido cada 10 minutos por cliente), Q2 pide unas **870 peticiones por segundo**. Casi todas vienen del reparto del tiempo real: cada pedido hace que los 100 clientes del local vuelvan a pedir su estado (plan de 003, D6).
- **Más allá de 003:** B06 (pantalla de cola) y las features siguientes suman carga sobre la misma API.

Abaratar las consultas ayuda, pero no multiplica por tres lo que da un núcleo.

## Decisión

El monolito corre con **varios procesos de uvicorn** en cada contenedor (`uvicorn --workers N`).

- **Compose:** `N = 4`, configurable con `API_WORKERS`.
- **Producción (ECS Fargate):** `N` es el número de vCPU de la tarea. La feature de infraestructura fija la tarea y su número de tareas.
- **Sin estado en memoria:** la API ya guarda en PostgreSQL y Redis todo lo que comparten las peticiones (sesiones, caché, límites, eventos), así que cualquier proceso puede atender cualquier petición. Lo que se añada después tiene que seguir así.
- **Pool de conexiones:** cada proceso tiene el suyo. `N` × (tamaño + desborde del pool) más las conexiones del trabajador y las migraciones tiene que caber en `max_connections` de PostgreSQL (100 en el compose; en RDS, según la instancia).
- **Migraciones:** siguen corriendo una vez, antes de arrancar los procesos, no en cada uno.

## Alternativas descartadas

- **Un proceso por contenedor y más contenedores:** es lo que hará la infraestructura para escalar horizontalmente, pero en Fargate cada tarea tiene un mínimo de memoria y de coste. Con varias vCPU por tarea, un solo proceso deja núcleos ociosos.
- **Gunicorn con workers de uvicorn:** añade una dependencia para lo mismo que `uvicorn --workers`, que ya reinicia un proceso caído.
- **Reducir el reparto de D6 (que el cliente solo pida su estado cuando el cambio le afecta):** exige que los eventos digan a quién afectan sin revelar los pedidos de otros dispositivos (R011 de 003). Es más complejo y no quita el límite de un núcleo para el resto de la carga.

## Consecuencias

- La memoria de la API se multiplica por `N`: unos 150 MiB por proceso en reposo. El tope de Argon2 de `app/shared/cpu.py` es por proceso: con `N` procesos puede haber hasta `N` × núcleos hashes a la vez. La feature de infraestructura revisa el tope y la memoria de la tarea con `src/perf/accounts.js`.
- Los registros de los procesos se mezclan en la salida del contenedor. Cada línea ya lleva su petición; si hace falta, se añade el PID.
- Un estado en memoria (una caché local, un contador) daría resultados distintos según el proceso que atienda. Queda prohibido salvo que sea por proceso a propósito y sin efecto en el negocio.
- Las pruebas de carga se miden con la misma `N` con la que se despliega.
