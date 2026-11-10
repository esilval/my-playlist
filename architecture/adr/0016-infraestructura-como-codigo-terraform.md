# ADR-0016 — Infraestructura como código con Terraform

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 46df64caa1f9 |
| Fecha         | 2026-11-09 |
| Motivo        | Q3, Q2 |
| Sustituye     | — |
| Propuesto por | `specs/004-infraestructura-puesta-marcha-aws-version/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

ADR-0006 decide que todo se despliega en AWS y que la infraestructura se define como código, pero no con qué herramienta. La feature 004 crea el entorno de producción y una preproducción temporal con la misma definición (R022 de 004), que se levanta y se destruye en cada prueba de carga. Todo lo que añadan las features siguientes (la pantalla de cola, el relleno, el cobro) pasa por la misma herramienta, así que cambiarla después obliga a reescribir toda la infraestructura.

## Decisión

La infraestructura se define con **Terraform** (licencia BUSL, versión fijada en el repositorio) en `src/infra/`:
- **Módulos y entornos:** un módulo raíz con dos entornos, `production` y `preproduction`. Cada entorno tiene su archivo de variables y su propio estado.
- **Estado:** remoto en S3, cifrado, con versionado y con el bloqueo nativo de S3. Ninguna persona lo edita a mano.
- **Arranque:** el bucket del estado, la zona DNS y el rol de despliegue se crean una sola vez desde `src/infra/bootstrap/`, con su propio estado.
- **Pruebas:** `terraform fmt`, `validate` y `terraform test` corren en el CI de cada PR que toca `src/infra/`.
- **Proveedores:** las versiones se fijan en `.terraform.lock.hcl`, que se versiona, igual que los lockfiles de npm.

## Alternativas descartadas

- **AWS CDK (TypeScript o Python):** genera CloudFormation y tiene buenas abstracciones, pero sus despliegues son más lentos de crear y destruir, lo que importa en la preproducción temporal. Sus errores llegan a mitad del despliegue de CloudFormation, no en el plan, y ata la infraestructura a AWS.
- **CloudFormation a mano:** sin abstracciones ni pruebas locales, y con plantillas largas y difíciles de revisar en un PR.
- **OpenTofu:** es compatible con Terraform y de licencia abierta. Queda como salida si la licencia de Terraform llegara a ser un problema; hoy tiene menos documentación y menos proveedores verificados.
- **Pulumi:** infraestructura en un lenguaje general, pero añade su servicio de estado o un backend propio y tiene menos adopción.

## Consecuencias

- Se añade Terraform al CI y a las herramientas del desarrollador, con su versión fijada.
- El estado guarda valores sensibles, como las contraseñas que genera Terraform. El bucket es privado, está cifrado y solo lo leen el rol de despliegue y el administrador.
- Un cambio hecho a mano en la consola de AWS se pierde en el siguiente `apply`. Todo cambio de infraestructura entra por PR.
- Las features siguientes añaden su infraestructura en `src/infra/` y la prueban con `terraform test`.
