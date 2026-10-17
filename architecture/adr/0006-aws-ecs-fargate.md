# ADR-0006 — AWS con contenedores en us-east-1

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 461eb6c8fad0 |
| Fecha     | 2026-10-16 |
| Motivo    | Q3, Q2, D1§1 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

El servicio debe estar disponible el 99,5 % del mes (Q3) para el piloto en Bogotá (D1§1), con espacio para crecer más allá de 50 locales (Q2). Hay tres piezas de servidor: el monolito, el servicio de tiempo real y los estáticos.

## Decisión

Todo se despliega en AWS, región us-east-1: el monolito y el servicio de tiempo real en contenedores sobre ECS Fargate detrás de un Application Load Balancer, PostgreSQL en RDS Multi-AZ, Redis en ElastiCache, y la SPA en S3 + CloudFront. La infraestructura se define como código.

## Alternativas descartadas

- PaaS gestionado (Render, Railway, Fly.io): menos operación, pero menos control y una vía de crecimiento más limitada.
- GCP Cloud Run: escala a cero, pero limita la duración de las conexiones WebSocket.
- Región sa-east-1 (São Paulo): desde Bogotá no da mejor latencia y cuesta entre un 30 y un 50 % más.

## Consecuencias

- Hay que mantener IaC, redes (VPC, subredes) y observabilidad; es más trabajo inicial que un PaaS.
- Multi-AZ en RDS y al menos dos tareas por servicio para cumplir Q3; esto marca el coste mínimo mensual.
- Los datos de clientes y propietarios se alojan en EE. UU.: la política de tratamiento debe informar la transferencia internacional (Ley 1581).
