# Infraestructura

Infraestructura de MyPlaylist en AWS, **us-east-2** (ADR-0019), definida con Terraform
(ADR-0016). La
plantea la feature 004 en `specs/004-infraestructura-puesta-marcha-aws-version/`; su plan
explica cada decisión (D1 a D18).

| Carpeta | Qué hay |
| ------- | ------- |
| `bootstrap/` | El arranque: se aplica una sola vez, a mano. Crea el bucket del estado (en us-east-2), la zona de Route 53 de `200oklabs.com`, los roles de despliegue y de plan y, si la organización lo permite, el proveedor OIDC de GitHub (D17, D18). |
| `tests/` | `terraform test`, con el proveedor de AWS simulado: no toca AWS (D15). |

Terraform se fija en `.terraform-version` (1.17.2), y los proveedores en
`.terraform.lock.hcl`, que se versiona con los hashes de Linux y macOS.

## Pruebas

Desde `src/infra/`, sin credenciales de AWS:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform test
```

El CI corre lo mismo en el trabajo `infra` de cada PR que toca `src/infra/`.

## Secretos (D6)

`modules/secrets` crea un secreto de Secrets Manager por valor, con el nombre `myplaylist/<entorno>/<nombre>`. Las tareas de ECS reciben su ARN en `secrets`, nunca su valor.

| Secreto | Quién lo genera | ¿Queda en el estado? | Cómo se rota |
| ------- | --------------- | -------------------- | ------------ |
| `realtime-ticket-secret`, `device-token-secret`, `database-api-password`, `database-worker-password` | Terraform: efímero (`random_password`, 48 caracteres) y escrito con `secret_string_wo` | No | Subir su número en `rotation` y volver a desplegar. Las dos contraseñas de la base las vuelve a asignar `app.ops.db_users` en la tarea de migración (D5). |
| `redis-auth-token` | Terraform, igual que los anteriores | No: al componer el entorno (T017), ElastiCache lo leerá del secreto con un recurso efímero y lo escribirá con `auth_token_wo` | Subir a la vez `rotation["redis-auth-token"]` y `redis_auth_token_version` del módulo de datos. |
| `youtube-api-key` | Una persona, con `aws secretsmanager put-secret-value` | No: Terraform solo crea el secreto, sin valor | Volver a ejecutar `put-secret-value` y reiniciar las tareas de la API. |
| Usuario maestro de RDS | RDS (`manage_master_user_password`) | No | Lo rota RDS. |
| `cloudfront-origin-header` | Terraform, igual que los anteriores | **Sí**, en la configuración de CloudFront y en las reglas del ALB, que no tienen atributo de solo escritura | Subir su número en `rotation` y aplicar: el módulo de cómputo (las reglas del ALB) y el de borde (T014, el origen de CloudFront) lo leen del mismo secreto, y los dos lo reciben en el mismo `apply`. |

**Lo que sí queda en el estado:** solo la cabecera secreta entre CloudFront y el ALB (D1). Si se filtrara, permitiría llegar al ALB sin pasar por CloudFront, pero nunca dar acceso a los datos.

**Rotar la cabecera corta `/api/*` y `/socket.io/*` unos minutos:** la regla del ALB cambia en segundos, pero el origen de CloudFront tarda de 5 a 15 minutos en propagarse, y mientras tanto el ALB responde 403. Hasta que el plan prevea una rotación en dos pasos, se rota fuera de las horas de servicio.

**El alfabeto de los secretos generados es un contrato:** solo letras, números y `-_` (`override_special`). El tiempo real pone el token de Redis en `REDIS_URL` sin escaparlo (ver «Cómputo»): cambiar el alfabeto rompería su conexión.

**Al revisar un PR que toque `src/infra/`:** `terraform test` no ve recursos efímeros ni atributos de solo escritura. El trabajo `infra` del CI falla si encuentra en `modules/` un `resource "random_password"` (dejaría el valor en el estado) o un `secret_string =` (lo escribiría en claro).

## Cómputo (D1, D3, D8)

`modules/compute` crea los repositorios de ECR, el clúster de ECS con los servicios `api`, `worker` y `realtime`, la tarea de migración y el ALB.

- **El ALB** solo escucha en 443, en `origin.<dominio>`, con un certificado de ACM en us-east-2 validado por DNS. Cada regla exige la cabecera `X-Origin-Verify` con el valor del secreto `cloudfront-origin-header`; lo demás recibe 403. CloudFront llega a ese nombre por HTTPS (T014).
- **Los servicios** arrancan con al menos dos tareas repartidas en las dos zonas, con vuelta atrás automática si las nuevas no superan su comprobación de salud. Terraform no deshace el número de tareas (autoescalado y retirada, D10) ni la definición de tarea (la registra cada despliegue, D9).
- **La tarea de migración** es la única con el usuario maestro de RDS: ejecuta `alembic upgrade head` y `python -m app.ops.db_users` (D5, D8). La lanza el flujo de despliegue; no es un servicio.
- **Los secretos** llegan en `secrets`, por su ARN, y cada rol de ejecución solo lee los de su tarea. La clave de YouTube solo va con `CATALOG_PROVIDER=youtube`: en preproducción su secreto no tiene valor, y ECS no arrancaría una tarea que lo pidiera.
- **`REDIS_URL` del tiempo real:** la imagen de Node no tiene `app.ops.env`, así que el mando de la tarea la compone con `REDIS_HOST`, `REDIS_PORT` y el token, que solo tiene letras, números y `-_` (D6) y va en la URL sin escapar.
- **El primer `apply` de un entorno** crea los servicios con la etiqueta de `image_tag`, que todavía no está en ECR: sus tareas no arrancan hasta el primer despliegue (T018), que sube las imágenes y registra las definiciones.
- **Orden:** el entorno (T017) aplica este módulo después del de secretos, para que la cabecera ya tenga su versión cuando el ALB la lea.
- **Las definiciones de tarea las registra el despliegue:** Terraform ignora `task_definition` en los servicios, así que un cambio de su configuración o de sus secretos llega con el siguiente despliegue. La revisión que registra Terraform lleva la `image_tag` inicial: el despliegue (T018) parte siempre de la última revisión de cada familia, nunca de la de Terraform.

## Datos (D4)

- **PostgreSQL:** RDS Multi-AZ con copias de 7 días. En producción tiene protección contra borrado, y al destruirse deja la instantánea `myplaylist-production-final`. Si producción se destruyera otra vez, antes hay que borrar o renombrar esa instantánea.
- **Redis:** ElastiCache con una réplica. El token de AUTH se escribe con solo escritura (`auth_token_wo`) y no queda en el estado. Para rotarlo, se cambia el secreto y se sube `redis_auth_token_version`. El grupo aplica sus cambios al momento, porque ElastiCache no cambia el token de otro modo.

## Red (D2)

`modules/network` crea una VPC en dos zonas, sin NAT. Las pruebas (`tests/network.tftest.hcl`) comprueban los recursos que nombran, pero no ven uno nuevo. Por eso, al revisar un PR que toque `modules/network/`, hay que comprobar que:
- no aparece ningún `aws_vpc_security_group_ingress_rule` ni `aws_vpc_security_group_egress_rule` fuera de los que ya hay;
- no aparece ninguna `aws_route` sobre la tabla privada;
- no aparece ningún `aws_nat_gateway`.

La regla del ALB con la lista de prefijos de CloudFront cuenta como 55 en la cuota de 60 reglas del grupo: no cabe otra que la use.

## Lo que impone la organización de AWS (D18)

La cuenta `955519187424` pertenece a la organización de AWS `o-domf4iizxl`, administrada
desde la cuenta `616793442849`. Sus políticas (SCP) mandan sobre los permisos de cualquier
usuario de la cuenta:
- **Recursos regionales, solo en us-east-2.** En us-east-1 solo pasan los servicios
  globales (IAM, Route 53, CloudFront, ACM): por eso el certificado de CloudFront es lo
  único que va en us-east-1.
- **Sin proveedores de identidad** OIDC ni SAML (`p-n79p9if6`): ni crearlos ni listarlos.

### Comprobación previa

Antes de aplicar el arranque o un cambio de la organización, se simulan las acciones que
hacen falta, con la región en el contexto:

```bash
export AWS_PROFILE=myplaylist
ARN=$(aws sts get-caller-identity --query Arn --output text)
aws iam simulate-principal-policy --policy-source-arn "$ARN" \
  --context-entries ContextKeyName=aws:RequestedRegion,ContextKeyValues=us-east-2,ContextKeyType=string \
  --action-names s3:CreateBucket s3:PutBucketPolicy s3:PutObject \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
aws iam simulate-principal-policy --policy-source-arn "$ARN" \
  --context-entries ContextKeyName=aws:RequestedRegion,ContextKeyValues=us-east-1,ContextKeyType=string \
  --action-names route53:CreateHostedZone iam:CreateRole iam:PutRolePolicy iam:CreateOpenIDConnectProvider \
  --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text
```

| Fecha | Quién | Resultado |
| ----- | ----- | --------- |
| 2026-11-11 | Claude, con el perfil `myplaylist` (usuario `esilvalo`) | En us-east-2 se permiten todas las del arranque y las regionales de la feature (S3, VPC, ECS, ECR, ALB, RDS, ElastiCache, Secrets Manager, SES, SNS, CloudWatch, KMS, autoescalado). En us-east-1 se permiten Route 53, IAM (roles y políticas), CloudFront, ACM, Budgets y Pricing. Solo `iam:CreateOpenIDConnectProvider` está denegado. El bucket `myplaylist-200oklabs-terraform-state` está libre. |

### El proveedor OIDC de GitHub

Mientras la organización no lo permita, el arranque **no lo crea**
(`create_github_oidc_provider = false`) y los roles lo referencian por su ARN fijo,
`arn:aws:iam::955519187424:oidc-provider/token.actions.githubusercontent.com`. Lo crea quien
administra la organización, o da una excepción y se vuelve a aplicar el arranque con
`-var create_github_oidc_provider=true`. Sin él, los flujos de despliegue (T018) no
funcionan.

Petición a quien administra la organización:

> En la cuenta `955519187424`, la SCP `p-n79p9if6` impide crear el proveedor de identidad
> OIDC de GitHub Actions. Necesitamos que se cree en esa cuenta el proveedor OIDC con URL
> `https://token.actions.githubusercontent.com` y audiencia `sts.amazonaws.com`, o una
> excepción que permita `iam:CreateOpenIDConnectProvider`, `iam:GetOpenIDConnectProvider` e
> `iam:TagOpenIDConnectProvider` sobre
> `arn:aws:iam::955519187424:oidc-provider/token.actions.githubusercontent.com`. Es para
> desplegar desde GitHub Actions con credenciales temporales, sin claves de acceso
> guardadas. Los roles que lo usan solo aceptan los entornos protegidos del repositorio
> `esilval/my-playlist`.

| Fecha de la petición | Respuesta | Fecha de la respuesta |
| -------------------- | --------- | --------------------- |
| | pendiente | |

## Requisitos previos manuales (D17)

Lo que no se puede automatizar, en este orden:

1. **Credenciales de administrador** de la cuenta de AWS del negocio en el equipo de quien
   aplica el arranque (`aws configure sso` o un perfil con claves). Solo para el arranque.
2. **Aplicar el arranque** (ver abajo) y **delegar los servidores de nombres**: poner en el
   registrador de `200oklabs.com` los cuatro que devuelve `terraform output name_servers`.
   Se comprueba con `dig NS 200oklabs.com +short`.
3. **Pedir la salida del sandbox de SES** (D14) **en us-east-2** (ADR-0019), en la consola
   de SES, «Request production access». Tarda de 1 a 3 días hábiles. Anota aquí la fecha y la respuesta.
4. **Introducir `YOUTUBE_API_KEY`** en Secrets Manager, con
   `aws secretsmanager put-secret-value`, cuando exista el secreto (T012).
5. **Confirmar la suscripción a los avisos**: el correo que envía SNS al responsable de
   operación (T016).
6. **Crear los entornos de GitHub** `production` y `preproduction`, con un revisor y la
   regla de despliegue que solo admite etiquetas `v*` (T018). Cada uno lleva el secreto
   `AWS_DEPLOY_ROLE_ARN` con el valor de `terraform output deploy_role_arn`. El repositorio
   lleva la variable `AWS_PLAN_ROLE_ARN` con el de `plan_role_arn`.
7. **Pedir a Google la ampliación de la cuota de YouTube**, si la prueba con usuarios lo
   exige (10 000 unidades al día; 100 por búsqueda sin caché).

| Paso | Fecha | Quién | Resultado |
| ---- | ----- | ----- | --------- |
| 2. Arranque | 2026-11-11 | El usuario, con el perfil `myplaylist` | Aplicado: 12 recursos, sin el proveedor OIDC. Zona `Z0639081273LJQWTITRKS`. Estado migrado a `s3://myplaylist-200oklabs-terraform-state/bootstrap/terraform.tfstate`, y `terraform plan` no encuentra diferencias. |
| 2. Servidores de nombres | 2026-11-11 | El usuario, en el registrador | Delegados: `dig NS 200oklabs.com` devuelve `ns-493.awsdns-61.com`, `ns-810.awsdns-37.net`, `ns-1031.awsdns-00.org` y `ns-1779.awsdns-30.co.uk`. |
| 3. Salida del sandbox de SES | | | pendiente |

## Arranque

Con las credenciales de administrador del paso 1, desde `src/infra/bootstrap/`:

```bash
terraform init
terraform apply
terraform output
```

El primer `apply` deja el estado en local. Después se migra al bucket que acaba de crear,
y `backend.tf` se versiona en un PR:

```bash
cp backend.tf.example backend.tf
terraform init -migrate-state
rm terraform.tfstate terraform.tfstate.backup   # ya están en S3
```

El estado nunca se versiona (`.gitignore`). Un cambio posterior del arranque se hace
igual: PR con el cambio y `terraform apply` a mano, con credenciales de administrador.

**Roles que crea** (ADR-0017):
- **`myplaylist-github-deploy`:** solo lo asume un trabajo de este repositorio que corre en
  los entornos `production` o `preproduction`. Esos entornos exigen aprobación y solo
  admiten etiquetas `v*`. Sus permisos son amplios (administrador), porque crea toda la
  infraestructura: lo que lo acota es quién puede asumirlo. Es el mismo rol para los dos
  entornos, en la misma cuenta: **relajar las reglas de `preproduction`** (por ejemplo,
  admitir ramas o quitar el revisor) **abre también producción**. Los dos entornos llevan
  siempre las mismas reglas.
- **`myplaylist-github-plan`:** lo asumen los PR de este repositorio para comentar el
  `terraform plan`. Puede leer la cuenta (`ReadOnlyAccess`) y el estado, y solo escribir
  el archivo de bloqueo del estado.

## Coste

Precios de lista bajo demanda en us-east-2, comprobados el 2026-11-11 con la API de
precios de AWS (`aws pricing get-products`), para 730 horas al mes. El plan estimaba unos
US$450; el total comprobado está dentro del 20 % (T009).

| Recurso | Precio unitario | Plan (US$/mes) | Comprobado (US$/mes) |
| ------- | --------------- | -------------- | -------------------- |
| ECS `api`: 2 × (2 vCPU, 4 GiB) | US$0,04048 por vCPU-hora y US$0,004445 por GB-hora | ~145 | 144,2 |
| ECS `worker`: 2 × (0,25 vCPU, 0,5 GiB) | ídem | ~18 | 18,0 |
| ECS `realtime`: 2 × (0,5 vCPU, 1 GiB) | ídem | ~36 | 36,0 |
| RDS `db.t4g.medium` Multi-AZ y 20 GiB gp3 | US$0,129 por hora; US$0,23 por GB-mes | ~100 | 98,8 |
| ElastiCache 2 × `cache.t4g.small` | US$0,032 por nodo-hora | ~47 | 46,7 |
| ALB | US$0,0225 por hora y US$0,008 por LCU-hora (1 o 2 LCU de media) | ~25 | 22 a 28 |
| IP públicas (6 tareas y el ALB en dos zonas) | US$0,005 por hora | ~30 | 29,2 |
| CloudWatch: unos 21 GB de registros, 40 métricas y 13 alarmas | US$0,50 por GB; US$0,30 por métrica; US$0,10 por alarma | ~30 a 45 | ~25 |
| Secrets Manager: 8 secretos | US$0,40 por secreto | | 3,2 |
| Route 53, CloudFront, ECR, S3 y SES | | ~15 | ~11 |
| **Total en producción, en reposo** | | **~450 a 460** | **~435 a 440** |

- **Lo que no está en la tabla:** el autoescalado de la API en la hora pico (US$0,20 por tarea y hora) y la transferencia de datos. CloudFront incluye 1 TB al mes en su capa gratuita.
- **La cifra de registros es una estimación:** supone unas 20 peticiones por segundo de media y unos 400 bytes por línea. La revisa la preproducción (T019).
- **Preproducción:** unos US$0,60 por hora con todo en marcha. Una prueba de carga, de unas 3 horas, cuesta unos US$2 o 3.
