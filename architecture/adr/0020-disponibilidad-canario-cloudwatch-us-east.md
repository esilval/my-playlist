# ADR-0020 — Observabilidad con CloudWatch en us-east-2 y un canario de disponibilidad

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 9d73c23602e4 |
| Fecha         | 2026-11-13 |
| Motivo        | Q3, Q1, Q4, Q5, Q6, Q7 |
| Sustituye     | ADR-0018 |
| Propuesto por | `specs/004-infraestructura-puesta-marcha-aws-version/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0018 eligió CloudWatch para la observabilidad, y comprobaciones de salud de Route 53 para medir la disponibilidad desde fuera (SG3, R013 de 004). Al implementarla se vio que no se puede montar así:
- **Route 53 publica las métricas de sus comprobaciones solo en us-east-1,** y lo mismo hace CloudFront con las suyas. Una alarma sobre ellas tiene que estar en us-east-1, con su tema de SNS.
- **La organización de AWS deniega CloudWatch y SNS en us-east-1** (ADR-0019, D18 del plan de 004). Se comprobó con el simulador de políticas el 2026-11-13. En cambio, en us-east-2 se permiten CloudWatch Synthetics, Lambda, CloudWatch, SNS y S3.

Sin esas alarmas, una caída del servicio vista desde fuera (CloudFront, el certificado, el DNS o el ALB) no avisaría a nadie, y R013 pide comprobar cada minuto que el servicio responde y dar la disponibilidad del mes. El resto de ADR-0018 sigue valiendo: este ADR lo repite y cambia solo la disponibilidad.

## Decisión

La observabilidad usa **Amazon CloudWatch en us-east-2**:
- **Registros:** los servicios escriben en la salida estándar una línea JSON por evento. CloudWatch Logs los guarda 30 días; es la retención de todos los grupos de registros.
- **Métricas de la aplicación:** se emiten en las mismas líneas, con el formato EMF (Embedded Metric Format), sin un agente ni otra dependencia.
- **Métricas de AWS:** las del ALB, ECS, RDS y ElastiCache, que se publican en us-east-2. Las de CloudFront y Route 53 no se usan, porque solo existen en us-east-1.
- **Disponibilidad desde fuera:** **un canario de CloudWatch Synthetics** en us-east-2, **cada minuto**. En cada ejecución recorre tres pasos contra el dominio público, a través de CloudFront, como un usuario:
  - `GET /api/health`;
  - `GET /socket.io/health`;
  - la página pública de un establecimiento de prueba.

  La alarma de SG3 salta cuando el canario falla durante 5 minutos. La disponibilidad del mes es la media de `SuccessPercent` del canario.
- **Alarmas del ALB, además:** sin tareas sanas en un grupo de destino y la tasa de 5xx. No miden lo que ve el usuario, pero avisan sin depender del canario.
- **Alarmas:** una por umbral de cada señal, con un tema de SNS en us-east-2 que envía un correo al responsable de operación.
- **Rechazos por IP:** una regla de Contributor Insights sobre los registros de la API (SG6).
- **Lo que nunca se registra:** el texto de las búsquedas, cookies, tokens ni contraseñas. Los registros de acceso de uvicorn se desactivan, porque incluyen la cadena de consulta, y los sustituye un registro propio por petición, con la plantilla de la ruta. El canario no guarda capturas ni el cuerpo de las respuestas.

## Alternativas descartadas

- **Mantener las comprobaciones de Route 53 (ADR-0018) y pedir a la organización que permita CloudWatch y SNS en us-east-1:** no cambia ningún ADR, pero T016 y la puesta en marcha quedarían parados hasta que responda, y hoy no hay acceso a la cuenta de gestión.
- **Solo alarmas del ALB:** gratis, pero no ven un fallo de CloudFront, del certificado ni del DNS. R013 pide medir lo que ve un usuario.
- **Tres canarios cada 5 minutos, o uno cada 5 minutos:** unos US$30 o US$11 al mes, pero R013 pide comprobar cada minuto, así que habría que enmendar la spec, y una caída corta podría no verse.
- **Grafana Cloud o Datadog:** mejores paneles y alertas, pero añaden un proveedor externo que recibe registros con IP (Ley 1581 y la transferencia internacional que anota ADR-0019), con su coste y su cuenta. Se puede añadir después leyendo de CloudWatch.
- **Prometheus y Grafana propios:** más control, pero son servicios que hay que operar, que también pueden caerse, y su coste en Fargate es mayor que el de CloudWatch para el piloto.

## Consecuencias

- **Coste:** el canario cuesta unos US$0,0012 por ejecución; cada minuto son unas 43 800 al mes, unos US$53. Las alarmas del ALB y la Lambda del canario son casi gratis, y sus artefactos van a un bucket de S3 con caducidad de 30 días.
- **El canario corre desde la misma región que el servicio,** no desde varias, como Route 53. Una caída de toda us-east-2 lo apagaría a la vez, y la alarma vería «sin datos»: la alarma trata la falta de datos como fallo.
- **El canario es código:** un guion de Node con su versión del entorno de Synthetics fijada, que hay que mantener cuando AWS retira versiones.
- **Si la organización cambia sus políticas** y permite us-east-1, se puede volver a las comprobaciones de Route 53 con otro ADR.
- Cada servicio sigue el formato de registro y de métricas que fija el plan de 004. Una métrica con muchas dimensiones (por establecimiento, por dispositivo) cuesta por serie, así que queda prohibido usar el establecimiento o el dispositivo como dimensión.
- Los paneles de CloudWatch son básicos: para investigar, se usa Logs Insights.
- Las métricas personalizadas y la ingesta de registros cuestan según el volumen. El plan de 004 lo estima, y lo revisa la preproducción.
