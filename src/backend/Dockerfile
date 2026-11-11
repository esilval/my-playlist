# Imagen del monolito (ADR-0002, ADR-0013): la API y el trabajador usan la misma.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencias primero, para aprovechar la caché de capas.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN useradd --system --uid 1000 app
USER app

EXPOSE 8000
# El mando de producción (feature 004, plan D3, D6, D8): compone las URL de conexión con
# las partes que inyecta ECS, no migra (las migraciones son una tarea aparte) y no escribe
# el registro de acceso de uvicorn, que lleva la cadena de consulta con el texto buscado
# (R016). El compose lo sustituye por el suyo, que migra al arrancar.
CMD ["sh", "-c", "exec python -m app.ops.env uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --no-access-log"]
