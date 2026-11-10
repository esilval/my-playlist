# ADR-0018 — Observabilidad con CloudWatch

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 42ff7185bb9b |
| Fecha         | 2026-11-09 |
| Motivo        | Q3, Q1, Q4, Q5, Q6, Q7 |
| Sustituye     | — |
| Propuesto por | `specs/004-infraestructura-puesta-marcha-aws-version/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0006 anota que hay que mantener la observabilidad, sin decir con qué. `operations/v0.1.0.md` fija las señales SG1 a SG8 con su umbral, y la feature 004 exige medirlas de forma continua, conservar su historial 30 días, avisar por correo en menos de 5 minutos y guardar como mucho 30 días los registros con la IP (R011 a R013 y R016 de 004). Cada feature futura añadirá sus métricas con la misma herramienta y el mismo formato.

## Decisión

La observabilidad usa **Amazon CloudWatch**:
- **Registros:** los servicios escriben en la salida estándar una línea JSON por evento. CloudWatch Logs los guarda 30 días; es la retención de todos los grupos de registros.
- **Métricas de la aplicación:** se emiten en las mismas líneas, con el formato EMF (Embedded Metric Format), sin un agente ni otra dependencia.
- **Métricas de AWS:** las del ALB, ECS, RDS, ElastiCache y CloudFront.
- **Disponibilidad desde fuera:** comprobaciones de salud de Route 53 cada 30 segundos, desde varias regiones.
- **Alarmas:** una por umbral de cada señal, con un tema de SNS que envía un correo al responsable de operación.
- **Rechazos por IP:** una regla de Contributor Insights sobre los registros de la API (SG6).
- **Lo que nunca se registra:** el texto de las búsquedas, cookies, tokens ni contraseñas. Los registros de acceso de uvicorn se desactivan, porque incluyen la cadena de consulta, y los sustituye un registro propio por petición, con la plantilla de la ruta.

## Alternativas descartadas

- **Grafana Cloud o Datadog:** mejores paneles y alertas, pero añaden un proveedor externo que recibe registros con IP (Ley 1581 y la transferencia internacional que anota ADR-0006), con su coste y su cuenta. Se puede añadir después leyendo de CloudWatch.
- **Prometheus y Grafana propios:** más control, pero son servicios que hay que operar, que también pueden caerse, y su coste en Fargate es mayor que el de CloudWatch para el piloto.
- **CloudWatch Synthetics cada minuto:** mide recorridos completos, pero cuesta unos US$50 al mes por canario a ese ritmo. Las comprobaciones de Route 53 cuestan menos de US$5 y cubren la disponibilidad (SG3).

## Consecuencias

- Cada servicio sigue el formato de registro y de métricas que fija el plan de 004. Una métrica con muchas dimensiones (por establecimiento, por dispositivo) cuesta por serie, así que queda prohibido usar el establecimiento o el dispositivo como dimensión.
- Los paneles de CloudWatch son básicos: para investigar, se usa Logs Insights.
- Las métricas personalizadas y la ingesta de registros cuestan según el volumen. El plan de 004 lo estima, y lo revisa la preproducción.
