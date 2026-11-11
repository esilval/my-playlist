# Pruebas de entorno: el despliegue

Feature 004 (infraestructura y puesta en marcha en AWS), plan D15. Estas pruebas solo se
pueden hacer contra AWS: la preproducción primero (tarea T018) y producción después
(T023). Cada caso lleva el ID de su requisito en el título, para que `sdd trace` lo cuente
(`.sdd/config.json`).

**Un caso sin resultado no cierra su tarea** (constitución, «Pruebas»). Mientras ponga
«pendiente», el requisito no está comprobado en el entorno, aunque `sdd trace` lo cuente.

Cada resultado anota la fecha, el entorno (`preproduction` o `production`), la etiqueta
desplegada y quién lo hizo.

## Preparación

1. El arranque está aplicado (`src/infra/README.md`, «Arranque»), y los servidores de
   nombres de `200oklabs.com` apuntan a Route 53.
2. Los entornos `production` y `preproduction` de GitHub existen, con un revisor y la
   regla de despliegue que solo admite etiquetas `v*` (plan D17).
3. La etiqueta que se va a desplegar existe, por ejemplo `v0.2.0-rc.1`.

## Casos

### F004_R001 Despliegue de una versión etiquetada con aprobación

1. Lanza `deploy.yml` con la etiqueta.
2. Comprueba que espera la aprobación del entorno, y apruébalo.
3. Al terminar, comprueba en GitHub (Deployments) la etiqueta, quién aprobó y la hora.
4. Comprueba que las tareas de ECS usan las imágenes de esa etiqueta.
5. Repite el despliegue desde otro equipo o lanzándolo de nuevo: el resultado es el mismo.

- **Resultado:** pendiente (T018 en preproducción, T023 en producción).

### F004_R002 Sin etiqueta o sin aprobación no se despliega

1. Lanza `deploy.yml` desde una rama, sin etiqueta: se rechaza en el primer paso y nada
   cambia.
2. Lanza `deploy.yml` con una etiqueta y no lo apruebes: espera, y lo que está en marcha
   no cambia.

- **Resultado:** pendiente (T018).

### F004_R004 Una sola migración, antes de atender

1. En los registros del despliegue, la tarea de migración corre una vez, antes de
   actualizar los servicios.
2. `alembic_version` está en la cabeza de la versión desplegada.
3. **Primera vez en una base RDS nueva** (la preproducción, en su primera creación): el
   usuario maestro crea los roles `app_*`, y ningún rol `app_*` ni de servicio tiene
   `BYPASSRLS` (plan D5, D8).

- **Resultado:** pendiente (T018).

### F004_R006 Ningún secreto en las imágenes, los registros ni el repositorio

1. `docker history` e `inspect` de las imágenes publicadas en ECR: ningún valor de
   Secrets Manager.
2. Los registros del despliegue y de las primeras peticiones en CloudWatch: ningún
   valor de los secretos.
3. gitleaks del repositorio en verde (CI, trabajo `secrets`).

- **Resultado:** pendiente (T018 en preproducción, T023 en producción).

### F004_R003 Solo HTTPS en el dominio

1. `curl -sI http://myplaylist.200oklabs.com/l/<código>` responde con una redirección
   a `https://` en la misma ruta.
2. El certificado de `https://myplaylist.200oklabs.com` es válido en un navegador actual,
   sin advertencias.

- **Resultado:** pendiente (T023).
