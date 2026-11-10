# ADR-0017 — Despliegue desde GitHub Actions con aprobación y OIDC

| Campo         | Valor |
| ------------- | ----- |
| Estado        | Approved · 5e9ea26528cc |
| Fecha         | 2026-11-09 |
| Motivo        | Q3 |
| Sustituye     | — |
| Propuesto por | `specs/004-infraestructura-puesta-marcha-aws-version/plan.md` |

> Decisión propuesta desde `sdd`: afecta a más de una feature o es cara de
> revertir, y ninguna decisión aprobada la cubre. La decide el usuario con
> `/architecture:review`; hasta entonces, el plan que la cita no se puede aprobar.

## Contexto

La constitución exige que desplegar a producción lo apruebe explícitamente una persona, y la feature 004 pide que el despliegue salga siempre de una versión etiquetada y por el mismo procedimiento (R001, R002 de 004). Hoy el CI corre en GitHub Actions y `main` está protegida. Cada versión futura usará el mismo camino, así que cambiarlo afecta a todas las features.

## Decisión

El despliegue lo hace un flujo de **GitHub Actions** (`.github/workflows/deploy.yml`):
- **Disparo:** al publicar una etiqueta `v*` o a mano, siempre con el nombre de una etiqueta existente.
- **Pasos:** el flujo construye las imágenes y la SPA, y despliega en el entorno de GitHub `production`.
- **Aprobación:** el entorno `production` exige la aprobación de un revisor y solo admite etiquetas `v*`. Una rama o un commit sin etiqueta no pueden desplegar.
- **Acceso a AWS:** con OIDC, asumiendo un rol con los permisos justos. No hay claves de AWS guardadas en GitHub.
- **Registro:** el despliegue queda en GitHub, con la etiqueta, quién lo aprobó y la hora.
- **Preproducción:** la levanta, prueba y destruye otro flujo manual, sobre el entorno `preproduction`, con la misma aprobación.
- **Retirar el servicio:** también es un flujo manual con aprobación.

## Alternativas descartadas

- **AWS CodePipeline y CodeBuild:** mantienen todo dentro de AWS, pero duplican el CI que ya está en GitHub, y la aprobación vive lejos de los PR y las etiquetas.
- **Desplegar desde el equipo del desarrollador con un script:** depende de su equipo y de sus credenciales, no deja registro y no cumple R001.
- **Claves de acceso de AWS como secretos de GitHub:** son credenciales de larga duración que hay que rotar. Con OIDC, cada ejecución recibe credenciales temporales.

## Consecuencias

- Hoy hay un solo desarrollador, así que el entorno `production` le permite aprobar sus propios despliegues: la aprobación es un paso explícito, no una revisión por otra persona. Cuando haya más personas, se activa «prevent self-review».
- El rol de despliegue tiene permisos amplios sobre la cuenta. Solo lo puede asumir el flujo de este repositorio desde los entornos protegidos.
- GitHub Actions pasa a ser parte del camino crítico del despliegue. Si falla, el procedimiento manual de emergencia queda documentado, con los mismos pasos.
