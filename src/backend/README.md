# Backend

Monolito modular de MyPlaylist en Python 3.13 con FastAPI (ADR-0001 y ADR-0002). Sirve la API bajo `/api` y un trabajador que envía los correos. Por ahora contiene el módulo de cuentas y establecimientos (C1, feature 001).

**Stack:**
- FastAPI y Pydantic;
- SQLAlchemy 2 asíncrono con asyncpg;
- Alembic para las migraciones;
- Argon2id para las contraseñas;
- segno y Pillow para el QR;
- boto3 para SES.

Las dependencias se gestionan con [uv](https://docs.astral.sh/uv/), y el código se revisa con ruff y mypy.

## Estructura

```
app/
├── main.py              create_app(): monta los routers bajo /api y los casos de uso
├── worker.py            python -m app.worker: bandeja de salida de correo y purgas
├── shared/              config, base de datos con contexto RLS, CSRF, reloj, correo, outbox, cpu
├── accounts/            módulo C1
│   ├── domain/          reglas puras (registro, sesión, tokens, bloqueo, límites); sin FastAPI ni SQLAlchemy
│   ├── application/     casos de uso (registrar, entrar, verificar, recuperar, editar, QR…)
│   ├── infrastructure/  repositorios SQLAlchemy, Argon2, generador del QR, ficheros de la política
│   ├── api/             routers /api/auth, /api/owner y /api/public
│   ├── interface.py     lo que otros módulos pueden usar (ResolveOwner, EstablishmentByPublicCode)
│   └── policy/          política de tratamiento versionada (0000-borrador.md)
└── assets/fonts/        Inter (OFL) para el nombre impreso en el QR
migrations/              Alembic: 0001_accounts (roles, tablas, RLS, funciones SECURITY DEFINER)
tests/
├── unit/                dominio, adaptadores y plantillas
└── integration/         API y base de datos contra PostgreSQL real
```

Las capas siguen el estándar S1: el dominio no importa FastAPI ni SQLAlchemy. Hashing, correo y reloj son puertos.

## Puntos clave

- **Aislamiento (ADR-0009):**
  - Cada tabla lleva `establishment_id` y una política RLS.
  - Cada transacción ejecuta `SET LOCAL ROLE app_api` (o `app_worker`) y fija `app.establishment_id`.
  - Lo que ocurre antes de conocer el establecimiento (inicio de sesión, tokens, página pública) va por funciones `SECURITY DEFINER` acotadas.
  - El usuario de conexión de cada entorno debe ser miembro de `app_api` y `app_worker`.
- **Sesión:**
  - Cookie opaca `mp_session` (HttpOnly, Secure, SameSite=Lax, `Path=/api`), guardada como hash en PostgreSQL.
  - Caduca tras 12 h de inactividad.
- **CSRF:** las peticiones que modifican algo exigen la cabecera `X-MyPlaylist-Client`, y si llega `Origin`, tiene que ser el de la SPA.
- **Correo:**
  - Bandeja de salida en PostgreSQL. `app.worker` la envía con reintentos y espera exponencial.
  - Adaptadores: SES en AWS, SMTP contra Mailpit en local y memoria en las pruebas.
- **Argon2id:** 19 MiB, 2 pasadas y 1 hilo, fijados con la prueba de carga (`src/perf`). Se calcula en hilos, como mucho uno por núcleo (`app/shared/cpu.py`).

El contrato completo de la API está en [`specs/001-alta-establecimiento-qr/plan.md`](../../specs/001-alta-establecimiento-qr/plan.md#contratos). En marcha, el OpenAPI se sirve en `/openapi.json`.

## Desarrollo

Lo más sencillo es el entorno completo, desde `src/`:

```bash
docker compose up -d --build     # api en :8000, worker, PostgreSQL, Redis y Mailpit
```

Para correr la API en la máquina, con PostgreSQL y Mailpit del compose:

```bash
cd src/backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload    # http://localhost:8000/api/health
uv run python -m app.worker             # en otra terminal: envía los correos a Mailpit
```

### Configuración

Se lee de variables de entorno o de un `.env` ([`app/shared/config.py`](app/shared/config.py)):

| Variable | Por defecto | Para qué |
| -------- | ----------- | -------- |
| `ENV` | `local` | `local`, `test` o `production`. En producción exige SES y una política que no sea el borrador. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/myplaylist` | Base de datos |
| `PUBLIC_BASE_URL` | `http://localhost:5173` | Origen de la SPA: enlaces de los correos y URL del QR. Cambiarlo invalida los QR impresos. |
| `EMAIL_BACKEND` | `smtp` | `ses`, `smtp` o `memory` |
| `EMAIL_FROM` | `MyPlaylist <no-responder@example.com>` | Remitente |
| `SMTP_HOST` / `SMTP_PORT` | `localhost` / `1025` | Mailpit en local |
| `AWS_REGION` | `us-east-1` | SES |
| `DATA_POLICY_VERSION` | `0000-borrador` | Versión vigente de la política de tratamiento |
| `ARGON2_TIME_COST` / `ARGON2_MEMORY_COST_KIB` / `ARGON2_PARALLELISM` | `2` / `19456` / `1` | Coste del hash. Si se cambia, hay que repetir la prueba de carga. |

## Pruebas

```bash
uv run pytest                    # todo; las de integración necesitan PostgreSQL y Mailpit
uv run pytest tests/unit         # solo unitarias, sin servicios
uv run ruff check && uv run ruff format --check
uv run mypy app tests migrations
```

Las pruebas de integración crean la base `<nombre>_test` en el PostgreSQL de `DATABASE_URL`, la migran y prueban con el rol `app_api`; nunca con SQLite, para probar RLS de verdad. Cada prueba lleva el ID del requisito que verifica: `test_F001_R015_…`.

## Migraciones

```bash
uv run alembic upgrade head
uv run alembic revision -m "descripción"     # nueva migración en migrations/versions/
```

El rol `app_migrator` es dueño de las tablas y de las funciones `SECURITY DEFINER`. La API y el trabajador nunca se conectan con permisos de migración.
