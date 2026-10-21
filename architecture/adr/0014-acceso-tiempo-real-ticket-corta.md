# ADR-0014 — Acceso al tiempo real con un ticket de corta duración firmado por el monolito

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · f99be0bf1a93 |
| Fecha         | 2026-10-21 |
| Motivo        | Q4, Q6 |
| Sustituye     | — |
| Propuesto por | `specs/002-sesion-musica-reproductor-local/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0005 pide que el servicio de tiempo real (C6) valide el token de quien se conecta y solo le deje unirse a la sala de su establecimiento. ADR-0007 dice que valida «esos mismos tokens». Pero la sesión del propietario es una cookie opaca (`mp_session`), cuyo hash vive en PostgreSQL. La cookie solo viaja a `/api` (`Path=/api`), y solo el monolito sabe resolverla (C1).

Para validarla, C6 tendría que leer las tablas de cuentas o llamar al monolito en cada conexión. La feature 002 es la primera que usa el tiempo real: el reproductor y el panel del propietario. B03 (clientes con token anónimo) y B06 (pantalla de cola) lo usarán igual.

## Decisión

El monolito emite un **ticket de tiempo real**, y es lo único que C6 valida.

- **Qué es el ticket:** un token firmado con HMAC-SHA256 con un secreto que comparten el monolito y C6. Lleva:
  - el establecimiento;
  - el tipo de quien se conecta (`owner`, `player` o, más adelante, `client` y `screen`);
  - la caducidad, de 60 s;
  - un identificador aleatorio.
- **Cómo se obtiene:** se pide con una petición autenticada a la API (`POST /api/owner/realtime-ticket` para el propietario; B03 añadirá la del cliente con su token anónimo).
- **Cómo lo usa C6:** comprueba la firma y la caducidad al conectar, y une el socket solo a la sala `est:{establishment_id}`. No consulta PostgreSQL ni llama al monolito.
- **Reconexión:** el navegador pide un ticket nuevo antes de cada conexión o reconexión. Un socket ya conectado no caduca con su ticket.
- **El ticket solo sirve para recibir:** las acciones siguen yendo por la API HTTP del monolito (ADR-0005).

## Alternativas descartadas

- **C6 lee la sesión en PostgreSQL:** acopla el servicio de tiempo real a las tablas y a RLS de C1, y le da acceso a la base de datos solo para autenticar.
- **C6 llama al monolito para validar cada conexión:** añade una dependencia C6 → monolito y un salto de red en cada reconexión. Con 5000 clientes reconectando tras un corte (Q2), la carga cae sobre la API.
- **Enviar la cookie de sesión al servicio de tiempo real:** obliga a ampliar su `Path`, la expone a otro servicio y no sirve para el token anónimo del cliente.
- **Un JWT de larga duración:** no se puede revocar sin estado. Con 60 s de vida, que un ticket robado siga valiendo es un riesgo acotado, y solo permite recibir eventos.

## Consecuencias

- Hay un secreto nuevo (`REALTIME_TICKET_SECRET`) que el monolito y C6 deben compartir. En AWS llega por el entorno de cada tarea, y si cambia, invalida los tickets en circulación (como mucho 60 s).
- Cerrar la sesión del propietario no expulsa al instante un socket ya conectado: sigue recibiendo los eventos de su sala hasta que se desconecta, aunque sus acciones fallan porque piden la cookie. Por eso los eventos solo llevan lo que se muestra en pantalla (qué suena, avisos) y nunca datos de la cuenta. Si una feature necesita expulsar sockets, se publica un evento de desconexión por la sala.
- B03 y B06 reutilizan el mismo mecanismo, cada uno con su tipo de ticket.
