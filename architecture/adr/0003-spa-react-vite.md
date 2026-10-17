# ADR-0003 — Una sola SPA React con Vite para todos los frontales

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 8be6c04bc7b8 |
| Fecha     | 2026-10-16 |
| Motivo    | Q1, Q8 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

Hay cuatro frontales web (aplicación del cliente C5, panel C7, reproductor C4 y pantalla de cola C9) que deben funcionar en cualquier navegador sin instalar nada (Q8). La app del cliente se abre desde el QR en un móvil, así que su primera carga importa.

## Decisión

Una sola SPA en React + TypeScript construida con Vite, con una ruta por frontal y code-splitting por ruta, servida como estáticos desde CDN.

## Alternativas descartadas

- Next.js con SSR: la primera carga es más rápida, pero exige un runtime Node más que desplegar y operar.
- Varias SPA separadas en un monorepo: los builds son más pequeños, pero hay más configuración para cuatro frontales que comparten casi todo.

## Consecuencias

- Sin SSR: la app del cliente depende del code-splitting para no cargar el código del panel ni del reproductor.
- Un solo despliegue de frontales; un fallo de build afecta a los cuatro.
- El reproductor (C4) vive en una pestaña de navegador del local que debe quedarse abierta.
