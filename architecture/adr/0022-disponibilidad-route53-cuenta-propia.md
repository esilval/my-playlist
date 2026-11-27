# ADR-0022 — Disponibilidad con comprobaciones de salud de Route 53 en la cuenta propia

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · d7922a1683de |
| Fecha     | 2026-11-26 |
| Motivo    | Q3 |
| Sustituye | ADR-0020 |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

ADR-0020 reemplazó las comprobaciones de Route 53 de ADR-0018 por un canario de CloudWatch Synthetics que corre cada minuto en us-east-2. Lo hizo solo porque la organización de la cuenta antigua denegaba CloudWatch y SNS en us-east-1, la única región donde Route 53 publica las métricas de sus comprobaciones. El canario:
- cuesta unos US$53 al mes, una quinta parte del perfil de piloto de ADR-0021;
- corre desde la misma región que el servicio, así que una caída de toda us-east-2 lo apaga a la vez;
- es código propio, con una versión del entorno de Synthetics que AWS retira cada cierto tiempo.

Con la cuenta propia de ADR-0021, desaparece esa restricción.

## Decisión

Para la disponibilidad desde fuera (SG3, R013 de 004), se usan **comprobaciones de salud de Route 53**:
- **Qué comprueban:** HTTPS contra el dominio público, a través de CloudFront, cada 30 s y desde varias regiones de AWS.
- **Sobre qué rutas:** `/api/health`, `/socket.io/health` y la página pública del establecimiento de prueba, con una comprobación por ruta y búsqueda de texto en la respuesta.
- **La alarma de SG3:** está en us-east-1, con su propio tema de SNS que envía el correo al responsable, y salta cuando una comprobación falla durante 5 minutos.
- **La disponibilidad del mes:** es la media de `HealthCheckPercentageHealthy`.

El resto de ADR-0020 sigue igual: registros, EMF, métricas y alarmas en us-east-2, las alarmas del ALB, Contributor Insights, y lo que nunca se registra.

## Alternativas descartadas

- **Mantener el canario de ADR-0020:**
  - No hay que tocar el código, que ya está hecho (T016).
  - Pero cuesta unos US$50 al mes más, mira desde una sola región y hay que mantenerlo.
  - Se puede mantener si el usuario prefiere no rehacer T016 ahora: esta decisión se puede tomar independientemente de ADR-0021.
- **Un servicio externo de monitorización (UptimeRobot, Better Stack):** cuesta unos US$7 a 30 al mes y mira desde varios países, pero es otro proveedor con su cuenta, sus alertas fuera de AWS y su credencial. Route 53 da lo mismo dentro de la cuenta por unos pocos dólares.
- **Canario cada 5 minutos:** unos US$11 al mes, pero R013 pide comprobar cada minuto.

## Consecuencias

- **Coste:** unas tres comprobaciones con HTTPS y búsqueda de texto, más sus alarmas y el tema de SNS en us-east-1, cuestan unos US$5 al mes. Ahorran unos US$48 al mes frente al canario.
- **Dos regiones en observabilidad:** la alarma de SG3 y su tema de SNS viven en us-east-1, con el proveedor con alias que ya existe para el certificado. El resto sigue en us-east-2.
- **Código que hay que retirar:** el canario, su bucket y su rol, y la conservación de su grupo de registros en `infra.yml`, se retiran del módulo de observabilidad. Es una tarea nueva de 004, con sus pruebas `terraform test`.
- **Las comprobaciones no ejecutan JavaScript ni recorren la página como un usuario.** La búsqueda de texto confirma que la respuesta es la esperada, no solo un 200.
