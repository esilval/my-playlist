# ADR-0001 — Monolito modular más un servicio de tiempo real

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · c02840b88ca2 |
| Fecha     | 2026-10-16 |
| Motivo    | Q2, Q3, Q4 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

El piloto es modesto (50 locales, 5000 clientes a la vez, Q2) y pide 99,5 % de disponibilidad (Q3), lo que favorece pocas piezas desplegables. Pero las conexiones persistentes de todas las pantallas (C6, Q4 < 1 s) tienen un perfil de carga distinto al de las peticiones HTTP y conviene escalarlas por separado.

## Decisión

El backend es un monolito modular con un módulo por componente de servidor (C1, C2, C3, C8) y límites internos explícitos. La difusión en tiempo real (C6) es un servicio aparte que recibe los cambios del monolito por Redis y los empuja a los navegadores. Los frontales (C4, C5, C7, C9) son web estática (ADR-0003).

## Alternativas descartadas

- Monolito único con WebSocket dentro: más simple, pero las conexiones persistentes compiten con las peticiones de API y escalan juntas.
- Microservicios, uno por componente: coste operativo y de coordinación desproporcionado para un piloto, y cada servicio más es un punto de fallo para Q3.

## Consecuencias

- Dos despliegues de servidor y un canal entre ellos (Redis pub/sub) que hay que versionar.
- Los módulos del monolito solo se hablan por sus interfaces públicas (S2–S5), para poder extraer uno más adelante sin reescribirlo.
- Si el servicio de tiempo real cae, la API sigue aceptando pedidos y la música sigue sonando; las pantallas se resincronizan al reconectar.
