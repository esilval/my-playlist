# Backend

Monolito modular de MyPlaylist en Python 3.13 con FastAPI (ADR-0001 y ADR-0002). Sirve la API bajo `/api` y un trabajador que envía los correos. Contiene tres módulos: cuentas y establecimientos (C1, feature 001), la sesión de música y su cola (C2, features 002 y 003) y el catálogo de música (C3, feature 003).

**Stack:**
- FastAPI y Pydantic;
- SQLAlchemy 2 asíncrono con asyncpg;
- Alembic para las migraciones;
- Argon2id para las contraseñas;
- segno y Pillow para el QR;
- boto3 para SES;
- redis para los eventos de tiempo real, la caché de búsquedas y el límite por dispositivo;
- httpx2 para la YouTube Data API.

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
│   ├── interface.py     lo que otros módulos pueden usar (ResolveOwner, EstablishmentByPublicCode,
│   │                    EstablishmentIdByPublicCode)
│   └── policy/          política de tratamiento versionada (0000-borrador.md)
├── sessions/            módulo C2: sesión de música, cola, reproductor y pedidos del cliente
│   ├── api/             /api/owner/music-session… y las rutas del cliente (client.py)
│   └── devtools.py      python -m app.sessions.devtools enqueue: agrega canciones en local
├── catalog/             módulo C3: búsqueda de canciones (puerto MusicCatalog, YouTube y falso)
└── assets/fonts/        Inter (OFL) para el nombre impreso en el QR
migrations/              Alembic: 0001_accounts, 0002_music_sessions, 0003_queue_requests y
                         0004_public_establishment_id
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
- **Catálogo (C3, feature 003):**
  - El puerto `MusicCatalog` tiene dos adaptadores. `YouTubeCatalog` usa la YouTube Data API v3 y solo devuelve videos que se pueden insertar; espera como mucho 1,5 s. `FakeCatalog`, el de local y las pruebas, no sale a la red.
  - **El catálogo falso** devuelve 5 resultados deterministas por búsqueda, con referencias `fake:<slug>-<n>` y títulos «Canción n de <slug>», donde el slug es el texto sin tildes, en minúsculas y con guiones («Café Tacvba» da «Canción 1 de cafe-tacvba»). El reproductor falso de la web las entiende: suenan 3 s. Algunos textos tienen un comportamiento especial: `error` da un solo resultado, «Canción que falla», que falla al sonar; `caído` simula el proveedor caído (503), `nada` no da resultados y `retirada` da canciones que ya no existen al pedirlas (422).
  - Las búsquedas se guardan 24 h en Redis por establecimiento, y cada dispositivo puede hacer 10 por minuto. Sin Redis, la búsqueda sigue, sin caché ni límite. Al pedir una canción, siempre se pregunta al proveedor.
  - **YouTube real en local:** `CATALOG_PROVIDER=youtube` y `YOUTUBE_API_KEY` (una clave de la YouTube Data API v3, que nunca se versiona), en `src/.env`. La cuota por defecto da para unas 100 búsquedas al día.
- **El cliente que pide desde el QR (feature 003):**
  - Rutas públicas bajo `/api/public/establishments/{code}/`: `music`, `search`, `requests` y `realtime-ticket`.
  - El dispositivo se identifica con la cookie `mp_device`, firmada y ligada al establecimiento (`Path` de sus rutas, HttpOnly, Secure, SameSite=Lax, un año). No se guarda ningún dato personal.
  - Cupo de 5 canciones pendientes por dispositivo; una canción pendiente no se repite.
- **Procesos (ADR-0015):** en el compose, la API corre con `API_WORKERS` procesos de uvicorn, 4 por defecto y no más en local, por las 100 conexiones de PostgreSQL. Cada proceso tiene un pool fijo de 15 conexiones, sin desborde (plan D11), que se llena con la primera carga y después se reutiliza. En producción, uno por vCPU de la tarea. Ningún proceso guarda estado en memoria: todo vive en PostgreSQL y Redis.
- **Redis en producción:** tiene que ser la versión 7 o posterior. El límite de búsquedas usa `EXPIRE … NX`.

Los contratos completos de la API están en el plan de cada feature (por ejemplo, [`specs/003-pedir-canciones-desde-qr/plan.md`](../../specs/003-pedir-canciones-desde-qr/plan.md#contratos)). En marcha, el OpenAPI se sirve en `/openapi.json`.

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
| `REDIS_URL` | `redis://localhost:6379/0` | Eventos de tiempo real, caché de búsquedas y límite por dispositivo |
| `REALTIME_TICKET_SECRET` | un valor de desarrollo | Firma de los tickets de tiempo real, compartida con `src/realtime` (ADR-0014). En producción, uno propio. |
| `CATALOG_PROVIDER` | `fake` | `fake` o `youtube`. En producción tiene que ser `youtube`. |
| `YOUTUBE_API_KEY` | vacía | Clave de la YouTube Data API v3. Obligatoria con `youtube`. |
| `DEVICE_TOKEN_SECRET` | un valor de desarrollo | Firma de la cookie del dispositivo del cliente. En producción, uno propio de al menos 32 caracteres. |

## Pruebas

```bash
uv run pytest                    # todo; las de integración necesitan PostgreSQL y Mailpit
uv run pytest tests/unit         # solo unitarias, sin servicios
uv run ruff check && uv run ruff format --check
uv run mypy app tests migrations
```

Las pruebas de integración crean la base `<nombre>_test` en el PostgreSQL de `DATABASE_URL`, la migran y prueban con el rol `app_api`; nunca con SQLite, para probar RLS de verdad. También usan el Redis del compose. Antes de correrlas, desde `src/`: `docker compose up -d postgres redis mailpit`. Cada prueba lleva el ID del requisito que verifica: `test_F001_R015_…`.

Las del cliente que pide desde el QR (feature 003):
- `tests/integration/test_client_music.py`: las rutas públicas contra la API real;
- `tests/integration/test_request_track.py`: los casos de uso del pedido y del estado del cliente;
- `tests/integration/test_catalog_cache.py`: la caché y el límite de búsquedas en Redis;
- `tests/integration/test_isolation.py`: la cookie de un establecimiento no vale en otro (R011);
- `tests/integration/test_sessions_schema.py` y `test_definer_functions.py`: la columna nueva de la cola y la función que resuelve el código del QR;
- `tests/unit/test_youtube_catalog.py`, `test_fake_catalog.py`, `test_catalog_config.py`, `test_device_token.py` y `test_music_session_rules.py`.

El ticket de tiempo real del cliente se prueba también en el servicio de tiempo real: `src/realtime/test/rooms.test.ts`.

## Migraciones

```bash
uv run alembic upgrade head
uv run alembic revision -m "descripción"     # nueva migración en migrations/versions/
```

El rol `app_migrator` es dueño de las tablas y de las funciones `SECURITY DEFINER`. La API y el trabajador nunca se conectan con permisos de migración.
