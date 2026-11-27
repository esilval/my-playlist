# ADR-0021 — Cuenta de AWS propia, fuera de la organización, con un perfil de capacidad para el piloto

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 0d3d5293c3e6 |
| Fecha     | 2026-11-26 |
| Motivo    | Q3, Q2, Q7, D1§7 |
| Sustituye | ADR-0019 |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

ADR-0019 adaptó el despliegue a la cuenta `955519187424`, que pertenece a la organización `o-domf4iizxl` de otra cuenta (`616793442849`). Sus SCP deniegan tres cosas que la puesta en marcha necesita:
- los proveedores OIDC, que necesita ADR-0017;
- la salida del sandbox de SES, que necesita R008 de 004;
- CloudWatch y SNS en us-east-1, que obligaron a usar el canario de ADR-0020.

El caso de soporte 179460898900807 se abrió el 2026-11-13 y, tras unas tres semanas, sigue sin respuesta. T009, T015 y T018 de 004 están paradas, y con ellas la versión 0.2.0 y el piloto.

Se evaluaron cuatro salidas: otra nube (GCP), un VPS, Vercel y otra cuenta de AWS (`docs/arquitectura/2026-11-26-evaluacion-proveedor-despliegue.md`):
- **El problema no es AWS, es la cuenta.** Las 3115 líneas de Terraform, las 76 pruebas de `terraform test`, los flujos y la política de tratamiento, que ya nombra a AWS como encargado en EE. UU., valen tal cual en cualquier cuenta de AWS sin esas SCP.
- **La capacidad aprobada está pensada para la hora pico de Q2 todo el mes:** unos US$500 a 515 al mes en reposo. Un MVP que empieza con pocos locales no debería pagar ese pico mientras no llega.

## Decisión

El servicio se despliega en una **cuenta de AWS nueva e independiente**, cuya cuenta raíz es del negocio, con su propia facturación y sin ninguna organización por encima.

Todo lo demás de ADR-0019 sigue igual:
- Los servicios regionales van en us-east-2: ECS Fargate detrás de un ALB, RDS PostgreSQL Multi-AZ, ElastiCache, S3 con CloudFront, Secrets Manager, CloudWatch, SNS y SES.
- us-east-1 se usa para el certificado de CloudFront y los servicios globales.
- El acceso desde GitHub es por OIDC (ADR-0017), y la infraestructura se define en Terraform (ADR-0016).

La capacidad se fija con un **perfil de piloto**, sin cambiar los requisitos:
- **Mínimo en reposo, siempre en dos zonas:**
  - la API: 2 × (1 vCPU, 2 GiB);
  - el tiempo real: 2 × (0,25 vCPU, 0,5 GiB);
  - el trabajador: 1 × (0,25 vCPU, 0,5 GiB);
  - RDS: `db.t4g.small` Multi-AZ;
  - ElastiCache: 2 × `cache.t4g.micro`.
- **Hora pico:** el autoescalado de la API y del tiempo real llega hasta la capacidad que la prueba de carga de T019 demuestre necesaria para Q2.
- **Si la prueba de carga no se cumple con el perfil de piloto,** se sube al tamaño que mide, y el coste se recalcula en el plan de 004.
- **Los tamaños concretos viven en las variables de cada entorno,** no en este ADR.

## Alternativas descartadas

- **Seguir esperando el caso de soporte:** no cambia nada, pero el piloto sigue parado sin fecha, y la cuenta seguiría dependiendo de una organización ajena, que puede cambiar sus SCP en cualquier momento.
- **GCP: Cloud Run, Cloud SQL y Memorystore:**
  - Cloud Run ya admite WebSocket, con un máximo de 60 min por conexión.
  - Pero hay que reescribir toda la infraestructura y las pruebas, y GCP no tiene correo transaccional: hay que añadir un proveedor más.
  - Un socket abierto factura la instancia todo el tiempo.
  - Cuesta lo mismo o más que AWS: unos US$400 a 450 al mes con alta disponibilidad.
- **Un VPS con Docker Compose:**
  - **Uno solo:** unos US$150 a 175 al mes en DigitalOcean o Hetzner, que triplicó sus precios en junio de 2026. Pero no cumple R009 (perder una instancia o una zona sin intervención), y la base de datos, las copias, los parches y la seguridad pasan a operarlos el único desarrollador.
  - **Para cumplir R009** hacen falta dos VPS, un balanceador y PostgreSQL gestionado con réplica: unos US$245 al mes, lo mismo que el perfil de piloto en AWS, y con la infraestructura reescrita.
- **Vercel:**
  - Sirve bien la SPA, y sus funciones admiten WebSocket desde 2026, pero con conexiones de unos 5 minutos.
  - El trabajador (ADR-0015), los procesos de larga duración y Redis pub/sub (S5) tendrían que rehacerse con colas y servicios de terceros (Neon, Upstash).
  - Cada uno de esos terceros es otro encargado de datos personales en la política de tratamiento.
- **Mantener la capacidad aprobada en la cuenta nueva:** sin trabajo, pero se pagan unos US$250 al mes más por una hora pico que el piloto todavía no tiene.
- **Quitar Multi-AZ, o dejar una tarea por servicio:** ahorra unos US$60 más, pero rompe R009 y Q3.

## Consecuencias

- **Coste:** unos **US$265 al mes en reposo** en producción, con las comprobaciones de Route 53 de ADR-0022, frente a los US$500 a 515 de ahora (un 48 % menos). Si se mantiene el canario de ADR-0020, son unos US$312. Un Compute Savings Plan a un año baja unos US$20 más. El detalle está en el documento de evaluación.
- **El trabajo hecho se conserva:** el código, los módulos, las pruebas y los flujos. Lo que cambia:
  - las variables de capacidad del perfil de piloto;
  - el arranque en la cuenta nueva: el bucket del estado, la zona DNS y el rol de despliegue;
  - el cambio de los servidores de nombres del dominio a la zona nueva.
- **Se quitan los parches por la organización (D18 del plan de 004):** el OIDC vuelve a ADR-0017, se pide la salida del sandbox de SES en la cuenta nueva, y la retirada del rol de plan (D16) se puede revisar.
- **La cuenta antigua:**
  - Sus recursos del arranque se destruyen o se dejan sin uso. Lo decide el usuario, que también cierra el caso de soporte.
  - No se migran datos, porque producción nunca llegó a desplegarse.
- **La cuenta raíz nueva** lleva MFA y no se usa para operar. El día a día va por un usuario o un rol de IAM, y la facturación se vigila con el presupuesto de AWS Budgets que ya existe.
- **El perfil de piloto se revisa** con la prueba de carga de T019 y cuando el número de locales activos se acerque al de Q2.
- **La política de tratamiento no cambia:** el encargado sigue siendo AWS y los datos siguen en EE. UU. Lo que se fija es la cuenta y la capacidad.
- **El atajo a un VPS queda documentado como plan B,** por si el coste mensual no se puede sostener antes de tener ingresos. Exigiría enmendar R009 de 004.
