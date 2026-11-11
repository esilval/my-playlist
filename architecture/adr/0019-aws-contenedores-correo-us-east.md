# ADR-0019 — AWS con contenedores y correo en us-east-2

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 1c2e7b0759fc |
| Fecha         | 2026-11-11 |
| Motivo        | Q3, Q2, Q7, D1§1, D1§7 |
| Sustituye     | ADR-0006, ADR-0011 |
| Propuesto por | `specs/004-infraestructura-puesta-marcha-aws-version/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0006 fija AWS en us-east-1 para todo el servicio, y ADR-0011 envía los correos con SES desde la misma región. Al preparar el arranque de la feature 004 se comprobó que la cuenta de AWS del negocio (`955519187424`) pertenece a una organización de AWS (`o-domf4iizxl`). Sus políticas (SCP) solo permiten crear recursos regionales en **us-east-2 (Ohio)**:
- **En us-east-1** solo pasan las llamadas a los servicios globales: IAM, Route 53, CloudFront, ACM, Budgets y Pricing. VPC, ECS, ECR, RDS, ElastiCache, S3, Secrets Manager, SES, SNS y CloudWatch están denegados (sentencia `UsEast1Partitional`).
- **En cualquier otra región** está todo denegado.

Se comprobó con el simulador de políticas y con llamadas reales `--dry-run`. La organización es de otra cuenta (`616793442849`), así que esta cuenta no puede cambiar esas políticas. El usuario eligió adaptarse a us-east-2 en lugar de pedir una excepción.

Las razones de ADR-0006 y ADR-0011 siguen valiendo: Q3, Q2, Q7, la Ley 1581 y el piloto en Bogotá. Solo cambia la región.

## Decisión

Todo se despliega en AWS. Los servicios regionales van en **us-east-2**:
- el monolito y el servicio de tiempo real en contenedores sobre ECS Fargate, detrás de un Application Load Balancer;
- PostgreSQL en RDS Multi-AZ y Redis en ElastiCache;
- la SPA en S3, servida con CloudFront;
- Secrets Manager, CloudWatch y SNS.

Los servicios globales se siguen pidiendo a us-east-1, como exige AWS:
- el certificado de ACM que usa CloudFront, que tiene que estar en us-east-1;
- IAM y Route 53.

En Terraform, el proveedor por defecto es us-east-2, y un proveedor con alias apunta a us-east-1 solo para el certificado de CloudFront. La infraestructura se define como código (ADR-0016).

Los correos transaccionales se envían con **Amazon SES en us-east-2**, desde un dominio propio con SPF, DKIM y DMARC. El monolito los envía tras un puerto de dominio «enviar correo» (S1). En desarrollo y en pruebas, un adaptador los guarda en memoria o en un buzón local en lugar de enviarlos.

## Alternativas descartadas

- **Pedir a la organización una excepción para us-east-1:** no cambia ningún ADR, pero depende de una persona de fuera del proyecto y de cuánto tarde. Desde Bogotá, us-east-1 y us-east-2 dan una latencia parecida, y los dos están a precio de lista de EE. UU.
- **Otra cuenta de AWS, fuera de la organización:** quita las restricciones, pero exige otra cuenta, otra facturación y repetir las comprobaciones.
- **sa-east-1 (São Paulo):** sigue descartada (ADR-0006), y además la organización la deniega.
- **Lo que descartaban ADR-0006 y ADR-0011:**
  - un PaaS gestionado, que da menos control;
  - GCP Cloud Run, que limita la duración de los WebSocket;
  - Postmark o SendGrid, que serían otro encargado de datos personales;
  - un SMTP propio, con mala entregabilidad.

  Siguen descartados por las mismas razones.

## Consecuencias

- **Lo que ya traían ADR-0006 y ADR-0011:**
  - hay que mantener IaC, redes y observabilidad;
  - para Q3 hacen falta RDS Multi-AZ y al menos dos tareas por servicio;
  - los datos se alojan en EE. UU., y la política de tratamiento tiene que informar de esa transferencia internacional (Ley 1581);
  - hay que salir del sandbox de SES antes del piloto;
  - los rebotes y las quejas llegan por SNS;
  - el envío se hace fuera de la petición del usuario.
- **El sandbox de SES es por región:** la solicitud de salida se hace en us-east-2.
- **Dos proveedores en Terraform:** el certificado de CloudFront vive en us-east-1 y todo lo demás en us-east-2. Un recurso regional creado en us-east-1 fallará al aplicarse.
- **Las políticas de la organización mandan:** si cambian, por ejemplo para permitir us-east-1 o para dejar de permitir us-east-2, esta decisión se revisa. La feature 004 lo comprueba con el simulador de políticas antes de cada arranque.
- **Precios:** los de us-east-2 son los mismos que los de us-east-1 para Fargate, RDS, ElastiCache y el ALB, o muy parecidos. La comprobación de costes de la feature 004 se hace con los de us-east-2.
