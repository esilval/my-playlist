# ADR-0011 — Correo transaccional con Amazon SES

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 79b2a89c1a50 |
| Fecha         | 2026-10-16 |
| Motivo        | Q7, Q3, D1§7 |
| Sustituye     | — |
| Propuesto por | `specs/001-alta-establecimiento-qr/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. Sustituye todo texto en
> cursiva. La decide el usuario con `/architecture:review`; hasta entonces, el
> plan que la cita no se puede aprobar.

## Contexto

La feature 001 envía correos de verificación (R017) y de recuperación de contraseña (R016). Después los necesitarán B09 (recibos, aviso de vencimiento) y los avisos al propietario. El correo del propietario es un dato personal (Ley 1581, Q7) y el servicio corre en AWS (ADR-0006).

## Decisión

Los correos transaccionales se envían con Amazon SES en us-east-1, desde un dominio propio con SPF, DKIM y DMARC. El monolito los envía tras un puerto de dominio «enviar correo» (S1). En desarrollo y en pruebas, un adaptador guarda los mensajes en memoria o en un buzón local en lugar de enviarlos.

## Alternativas descartadas

- Postmark o SendGrid: entregan mejor de serie y traen panel, pero son otro encargado de datos personales que hay que declarar ante la Ley 1581 y pagar aparte.
- SMTP propio: gratis, pero la entregabilidad es mala y hay que operarlo; además pone en riesgo Q3 para la verificación.

## Consecuencias

- Hay que salir del sandbox de SES (solicitud a AWS) antes del piloto; mientras tanto solo llegan correos a direcciones verificadas.
- Rebotes y quejas se reciben por SNS y deben atenderse para no perder la cuenta de envío.
- El envío se hace fuera de la petición del usuario (cola o tarea en segundo plano), para que un fallo de SES no rompa el registro; el reenvío lo cubre el propio producto (R018).
