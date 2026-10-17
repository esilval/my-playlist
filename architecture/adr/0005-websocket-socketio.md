# ADR-0005 — WebSocket propio con Socket.IO y pub/sub en Redis

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 32ca45e05d99 |
| Fecha     | 2026-10-16 |
| Motivo    | Q4, Q2, Q6 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

Los cambios de la cola deben verse en menos de 1 s (Q4) en hasta 5000 navegadores (Q2), cada uno solo con los de su establecimiento (Q6). El servicio de tiempo real va aparte del monolito (ADR-0001).

## Decisión

El monolito publica cada cambio de cola o aviso en un canal de Redis por establecimiento. El servicio Node con Socket.IO se suscribe y lo reenvía a una sala por establecimiento. Los navegadores solo reciben: los pedidos y las acciones van por la API HTTP del monolito.

## Alternativas descartadas

- Server-Sent Events: es más simple, pero Socket.IO trae reconexión, salas y fallback ya resueltos.
- Servicio gestionado (Pusher, Ably): cero operación, pero tiene coste por conexión y deja datos de cada local en un tercero que habría que declarar ante la Ley 1581.

## Consecuencias

- El servicio de tiempo real valida el token (ADR-0007) al unirse a una sala y solo admite la sala de su establecimiento.
- Con varias instancias del servicio se usa el adaptador Redis de Socket.IO; el balanceador debe admitir WebSocket con afinidad.
- Los eventos llevan una versión de cola: al reconectar, el cliente pide el estado completo por API si se perdió algún evento.
