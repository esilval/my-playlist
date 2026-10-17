# ADR-0013 — Monorepo con el código bajo src/

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · cace12bc4c7e |
| Fecha         | 2026-10-17 |
| Motivo        | Q8, Q3, G4 |
| Sustituye     | ADR-0012 |
| Propuesto por | `specs/001-alta-establecimiento-qr/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0012 pone el código en cuatro raíces del repositorio (`backend/`, `realtime/`, `web/` e `infra/`), junto a las definiciones de negocio y arquitectura (`product/`, `architecture/`, `specs/`). Con la feature 001 terminada, el propietario del producto pide separar el código que se entrega de esas definiciones, para que la raíz del repositorio distinga a simple vista lo que se define de lo que se construye.

## Decisión

Se mantiene todo lo que decide ADR-0012 (un único repositorio, las mismas herramientas y las mismas cuatro piezas), con dos cambios:

- **El código vive bajo `src/`:** `src/backend/`, `src/realtime/`, `src/web/` e `src/infra/`. También el tooling que solo sirve al código: `src/docker-compose.yml`, `src/.env.example` y la prueba de carga `src/perf/`.
- **En la raíz quedan las definiciones y lo que exigen las herramientas:**
  - `product/`, `architecture/`, `specs/`, `docs/` y `documentation/`;
  - `.github/`, porque GitHub solo lee los workflows ahí, con las rutas apuntando a `src/`;
  - `.gitignore`.

El proyecto de docker-compose se nombra de forma explícita (`name: myplaylist`), para que la red y los volúmenes no dependan del nombre de la carpeta.

## Alternativas descartadas

- **Mantener las raíces de ADR-0012.** Funciona, pero mezcla en el mismo nivel las definiciones de negocio y el código que se entrega, que es justo lo que se quiere evitar.
- **Separar código y definiciones en dos repositorios.** La trazabilidad de `sdd`, que cruza spec, tareas y tests, y la revisión conjunta de un cambio de requisito con su código dependen de que todo esté en el mismo repositorio.
- **Mover también `.github/` a `src/`.** GitHub no lee workflows fuera de la raíz.

## Consecuencias

- Cada comando de desarrollo se ejecuta desde su carpeta bajo `src/` (por ejemplo, `cd src/backend && uv run pytest`, o `cd src && docker compose up -d`).
- El CI cambia sus filtros de rutas y sus `working-directory` a `src/backend` y `src/web`.
- Los planes y las tareas citan las rutas con el prefijo `src/`. Los de la feature 001 se actualizan con esta decisión y hay que volver a aprobarlos.
- Las rutas que el código calcula desde su propio archivo (plantillas de correo, fuentes, política) no cambian, porque son relativas a `src/backend/`.
