#!/bin/sh
# Regenera los tipos de la API desde el OpenAPI que publica el backend (ADR-0002).
# Uso: npm run gen:api  (necesita uv y el backend en ../backend)
#
# openapi-typescript 7.13 declara compatibilidad solo con TypeScript 5; el proyecto usa
# TypeScript 6 y package.json lo fuerza con `overrides` (solo esta herramienta de
# generación). Comprobado: genera y compila en modo estricto. Quitar el override cuando
# openapi-typescript declare compatibilidad con TypeScript 6.
set -eu

WEB_DIR=$(cd "$(dirname "$0")/.." && pwd)
SPEC=$(mktemp -t myplaylist-openapi.XXXXXX)
trap 'rm -f "$SPEC"' EXIT

(cd "$WEB_DIR/../backend" && uv run --locked --quiet python -c \
  "import json; from app.main import create_app; print(json.dumps(create_app().openapi(), sort_keys=True))") > "$SPEC"

npx --no-install openapi-typescript "$SPEC" --output "$WEB_DIR/src/api/schema.d.ts"
