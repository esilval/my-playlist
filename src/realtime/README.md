# Tiempo real

Servicio de tiempo real de MyPlaylist (C6, ADR-0005). Es Node 22 con TypeScript y Socket.IO, y hace llegar a cada pantalla conectada de un establecimiento los cambios de su sesión de música: al panel del propietario, al reproductor del local y, más adelante, a la app del cliente y a la pantalla de cola.

Solo difunde. Los navegadores reciben eventos y nunca los envían: las acciones van por la API del monolito. No lee ni escribe en PostgreSQL y no llama al monolito (S5).

## Cómo funciona

1. **El monolito publica:** cada cambio de la sesión de música se publica en Redis, en el canal `est:{establishment_id}`, después de confirmar la transacción.
2. **Este servicio reenvía:** se suscribe por patrón a `est:*` y reenvía cada mensaje a la sala de Socket.IO del mismo nombre. El nombre del evento es su `type` y el cuerpo, el mensaje tal cual.
3. **El navegador se une a su sala con un ticket:** antes de conectar pide un ticket de 60 s a la API (`POST /api/owner/realtime-ticket`) y lo manda al conectar. El servicio comprueba la firma y la caducidad con el secreto que comparte con el monolito (ADR-0014). Después, une el socket solo a la sala `est:{id}` del ticket.

Solo se reenvían los tipos de evento de la tabla de contratos del plan de la feature 002: `session.opened`, `session.closed`, `player.claimed`, `track.started`, `track.failed` y `queue.changed`. Cualquier otro mensaje, o un canal que no sea `est:{uuid}`, se descarta. Cuando una feature añada un tipo de evento, hay que sumarlo en `src/relay.ts`.

## Estructura

```
src/
├── server.ts   configuración, servidor HTTP con /health y Socket.IO; punto de entrada
├── ticket.ts   validación del ticket (firma HMAC-SHA256 y caducidad)
├── rooms.ts    autenticación al conectar y sala por establecimiento
└── relay.ts    suscripción a Redis y reenvío a las salas
test/
├── fixtures/ticket-vectors.json   vectores que genera y comprueba el monolito
├── ticket.test.ts
├── rooms.test.ts
└── relay.test.ts                  contra un Redis real
```

## Configuración

| Variable | Por defecto | Para qué |
| -------- | ----------- | -------- |
| `ENV` | — | Con `production`, exige un `REALTIME_TICKET_SECRET` propio. |
| `PORT` | `3001` | Puerto del servicio. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis del que llegan los eventos. |
| `REALTIME_TICKET_SECRET` | el de desarrollo del monolito | Secreto compartido con el monolito. Tiene que ser el mismo en los dos servicios. En producción no puede ser el de desarrollo ni tener menos de 32 caracteres. |

Sin Redis, el servicio no arranca: se suscribe antes de abrir el puerto.

## Desarrollo

Lo más sencillo es el entorno completo, desde `src/`:

```bash
docker compose up -d --build
```

Así arranca `realtime` junto con los demás servicios, y Vite reenvía `/socket.io`, también el WebSocket, por el mismo origen que la SPA (`http://localhost:5173`).

Para correrlo en la máquina, con el Redis del compose:

```bash
cd src/realtime
nvm use            # Node 22 (.nvmrc)
npm install
npm run build && npm start
```

| Script | Qué hace |
| ------ | -------- |
| `npm run build` | Compila con `tsc` a `dist/` |
| `npm start` | Arranca `dist/server.js` |
| `npm run lint` | eslint y tsc, también sobre las pruebas |
| `npm test` | Vitest; las pruebas del reenvío necesitan Redis (`REDIS_URL`) |

Los vectores de `test/fixtures/ticket-vectors.json` los genera y comprueba el monolito (`src/backend/tests/unit/test_realtime_ticket.py`). Si cambia el formato del ticket, se regeneran allí y las pruebas de este servicio comprueban que sigue validando exactamente lo que firma el monolito.
