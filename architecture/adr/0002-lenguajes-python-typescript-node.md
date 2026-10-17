# ADR-0002 — Python/FastAPI en el backend, TypeScript en frontales y tiempo real

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · d231bdbbfc77 |
| Fecha     | 2026-10-16 |
| Motivo    | Q1, Q4, Q8 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

Hay que elegir lenguajes para el monolito (ADR-0001), el servicio de tiempo real y los frontales web, que no pueden instalar nada (Q8). Los reproductores de YouTube y Spotify solo existen como SDK de JavaScript para navegador.

## Decisión

El monolito se escribe en Python con FastAPI (asíncrono, validación con Pydantic, contrato OpenAPI). El servicio de tiempo real se escribe en TypeScript sobre Node.js con Socket.IO. Los frontales, en TypeScript con React. Los tipos TypeScript de la API se generan desde el OpenAPI del backend.

## Alternativas descartadas

- TypeScript en todo el stack: un solo lenguaje, pero se prefirió Python para el backend.
- Django con Channels: incluye mucho para cuentas, pero es más pesado, menos asíncrono de serie, y el tiempo real se prefirió en Node por la madurez de Socket.IO en reconexión.
- Elixir/Phoenix: tiempo real nativo, pero con un ecosistema y talento más escasos.

## Consecuencias

- Tres runtimes (Python, Node y el navegador) con sus herramientas, dependencias y pipelines.
- El contrato OpenAPI es la fuente de verdad de los tipos compartidos; un cambio de API exige regenerar los tipos TS.
- El formato de los eventos de tiempo real se define en un esquema compartido (JSON Schema) que usan el monolito y el servicio Node.
