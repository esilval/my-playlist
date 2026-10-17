# ADR-0007 — Autenticación propia del propietario y token anónimo del cliente

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · cb862bcf1c1b |
| Fecha     | 2026-10-16 |
| Motivo    | Q7, Q6, D1§7 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

El propietario necesita una cuenta (B01). El cliente es anónimo pero debe identificarse por dispositivo para el cupo (B03). La Ley 1581 y Q7 piden datos mínimos y pocos terceros con datos personales.

## Decisión

El propietario se registra con correo y contraseña gestionados por el monolito (hash Argon2id, sesión en cookie HttpOnly y Secure). El cliente recibe al entrar por el QR un identificador aleatorio de dispositivo firmado por el servidor y ligado al establecimiento; no se le pide ningún dato. El servicio de tiempo real valida esos mismos tokens.

## Alternativas descartadas

- Proveedor externo (Auth0, Clerk, Supabase Auth): da recuperación y verificación hechas, pero añade un encargado de datos que declarar y una dependencia de pago.
- Login social con Google: no hay contraseñas, pero obliga al propietario a tener cuenta de Google.

## Consecuencias

- Recuperación de contraseña, verificación de correo y limitación de intentos se construyen en el proyecto.
- El cupo por dispositivo puede saltarse borrando la cookie; se acepta en la primera versión, igual que el acceso desde fuera del local.
- Todo token lleva el establecimiento y la API lo usa para fijar el contexto de aislamiento (ADR-0009).
