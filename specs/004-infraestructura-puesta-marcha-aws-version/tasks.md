# Tasks: Infraestructura y puesta en marcha en AWS

| Campo  | Valor       |
| ------ | ----------- |
| Spec   | `spec.md`   |
| Plan   | `plan.md`   |
| Fecha  | 2026-11-09  |
| Estado | Approved · 6fc283f00e73       |

> Cada tarea debe ser verificable por sí sola y caber en una sola sesión de
> trabajo. Si una tarea necesita una decisión que no está en `plan.md`, la tarea
> está mal descompuesta.
>
> Solo el usuario cambia el Estado, con `/sdd:approve`. Las pruebas citan el
> requisito con el prefijo de la feature:
> - en Python, `test_F004_R007_…`;
> - en el título de las pruebas del servicio de tiempo real, `F004_R007 …`;
> - en el nombre del `run` de `terraform test`, `F004_R003_…`;
> - en el título de cada caso de `docs/qa/`, `### F004_R009 …`.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecha
- `P` marca tareas paralelizables (sin dependencias entre sí)

Las tareas T001 a T008 cambian la aplicación y se prueban en local. T009 a T017 escriben la infraestructura y se prueban con `terraform test`, sin AWS real. T018 a T024 la usan en AWS y dejan sus resultados en `docs/qa/`: necesitan la cuenta de AWS y, algunas, al usuario.

## Tareas

### T001 — Configuración: `ENV=preproduction` y validaciones de producción `P`

- **Estado:** `[x]`
- **Requisitos:** R007, R022
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/shared/config.py`
  - `src/backend/tests/unit/test_config.py`
  - `src/realtime/src/server.ts`
  - `src/realtime/test/server.test.ts`
- **Hecho cuando:** pasan:
  - `test_F004_R007_production_rechaza_un_remitente_de_example_com`;
  - `test_F004_R007_production_rechaza_una_url_publica_sin_https_o_localhost`;
  - `test_F004_R007_preproduction_exige_secretos_propios`;
  - `test_F004_R022_preproduction_admite_el_catalogo_falso_smtp_y_la_politica_en_borrador`;
  - en C6, `F004_R007 en preproduction exige un REALTIME_TICKET_SECRET propio`.

  Los errores nombran la variable que falla, y las pruebas de configuración anteriores siguen en verde.

### T002 — Puerto `Metrics` y su implementación EMF `P`

- **Estado:** `[x]`
- **Requisitos:** R011
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/shared/metrics.py`
  - `src/backend/app/shared/infrastructure/__init__.py`
  - `src/backend/app/shared/infrastructure/emf.py`
  - `src/backend/tests/unit/test_metrics.py`
- **Hecho cuando:**
  - Pasan:
    - `test_F004_R011_emf_escribe_una_linea_json_con_el_bloque_aws_y_el_valor`;
    - `test_F004_R011_emf_usa_el_espacio_de_nombres_del_entorno`;
    - `test_F004_R011_emf_rechaza_dimensiones_fuera_de_route_y_service`;
    - `test_F004_R011_la_implementacion_en_memoria_guarda_lo_emitido`.
  - `test_health.py` sigue sin encontrar FastAPI, SQLAlchemy ni clientes HTTP en el dominio (S1).

### T003 — Registro por petición sin datos sensibles

- **Estado:** `[x]`
- **Requisitos:** R011, R016, R020
- **Depende de:** T002
- **Archivos:**
  - `src/backend/app/shared/observability.py`
  - `src/backend/app/main.py`
  - `src/backend/tests/unit/test_observability.py`
- **Hecho cuando:** pasan:
  - `test_F004_R011_cada_peticion_escribe_su_ruta_su_estado_y_su_duracion`;
  - `test_F004_R016_el_registro_usa_la_plantilla_de_la_ruta_sin_la_cadena_de_consulta`, con una búsqueda `?q=…` cuyo texto no aparece en la salida;
  - `test_F004_R016_el_registro_no_escribe_cabeceras_cookies_ni_cuerpos`;
  - `test_F004_R020_solo_los_401_y_403_llevan_la_ip`;
  - `test_F004_R020_la_ip_sale_de_cloudfront_viewer_address_y_no_de_x_forwarded_for`, con un `X-Forwarded-For` falso que no aparece en el registro;
  - `test_F004_R011_search_unavailable_cuenta_cada_503`;
  - `test_F004_R016_el_arranque_con_configuracion_invalida_no_escribe_valores`: con una configuración inválida, la API termina con código 1 y escribe solo los mensajes de error, sin los valores de la entrada (D7).

### T004 — Métricas del reproductor y `published_at` en los eventos

- **Estado:** `[x]`
- **Requisitos:** R011
- **Depende de:** T002
- **Archivos:**
  - `src/backend/app/sessions/application/` (el caso de uso de los eventos del reproductor)
  - `src/backend/app/sessions/domain/music_session.py`
  - `src/backend/app/sessions/domain/queue.py`
  - `src/backend/app/sessions/infrastructure/repositories.py`
  - `src/backend/app/sessions/infrastructure/redis_publisher.py`
  - `src/backend/migrations/versions/0005_player_claimed_at.py`
  - `src/backend/app/main.py`
  - `src/backend/tests/integration/test_track_metrics.py`
  - `src/backend/tests/integration/test_event_publisher.py` (el contrato de 002, ampliado con `published_at`)
- **Hecho cuando:** pasan:
  - `test_F004_R011_started_y_failed_emiten_track_started_y_track_failed`;
  - `test_F004_R011_track_gap_mide_desde_el_finished_at_de_la_anterior`;
  - `test_F004_R011_track_gap_no_se_mide_si_la_cola_estaba_vacia_o_la_anterior_se_salto`;
  - `test_F004_R011_track_gap_no_se_mide_tras_una_toma_de_control`, con una toma de control a mitad de canción;
  - `test_F004_R011_cada_evento_publicado_lleva_published_at`;
  - `test_F004_R011_la_puesta_en_marcha_guarda_player_claimed_at`.

  `alembic upgrade head` y `alembic downgrade -1` funcionan con la `0005`. Las pruebas de eventos de 002 y 003, y la de RLS de `test_schema.py`, siguen en verde.

### T005 — Contador de la cuota de YouTube

- **Estado:** `[x]`
- **Requisitos:** R021
- **Depende de:** T002
- **Archivos:**
  - `src/backend/app/catalog/infrastructure/youtube.py`
  - `src/backend/app/catalog/infrastructure/quota.py`
  - `src/backend/app/main.py`
  - `src/backend/tests/unit/test_youtube_quota.py`
- **Hecho cuando:** pasan:
  - `test_F004_R021_cada_search_suma_100_y_cada_videos_list_suma_1`;
  - `test_F004_R021_el_dia_de_la_cuota_cambia_a_medianoche_del_pacifico`;
  - `test_F004_R021_emite_youtube_quota_used_con_el_total_del_dia`;
  - `test_F004_R021_la_busqueda_que_sale_de_la_cache_no_suma`.

  Si Redis falla, la búsqueda sigue funcionando y el error queda en el registro.

### T006 — Registros del trabajador sin direcciones `P`

- **Estado:** `[x]`
- **Requisitos:** R016
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/worker.py`
  - `src/backend/app/shared/outbox.py`
  - `src/backend/tests/unit/test_worker_logs.py`
- **Hecho cuando:** pasan:
  - `test_F004_R016_el_trabajador_registra_plantilla_e_id_sin_la_direccion`;
  - `test_F004_R016_un_envio_fallido_no_escribe_el_contenido_del_correo`;
  - `test_F004_R016_el_trabajador_con_configuracion_invalida_no_escribe_valores`: el trabajador arranca con la misma protección que la API (D7).

### T007 — Tiempo real: métricas y `/socket.io/health`

- **Estado:** `[x]`
- **Requisitos:** R011, R013
- **Depende de:** T001
- **Archivos:**
  - `src/realtime/src/metrics.ts`
  - `src/realtime/test/metrics.test.ts`
  - `src/realtime/src/server.ts`
  - `src/realtime/src/relay.ts`
  - `src/realtime/src/rooms.ts`
  - `src/realtime/test/server.test.ts`
- **Hecho cuando:** pasan:
  - `F004_R011 cada 60 s escribe Connections, EventsRelayed, RelayDelay y RedisErrors en EMF`;
  - `F004_R011 RelayDelay se mide desde published_at y se omite si el evento no lo trae`;
  - `F004_R013 GET /socket.io/health responde 200`.

  El suelo de cobertura de C6 (85 %) se mantiene.

### T008 — Usuarios de la base de datos, URL de conexión y mando de la imagen `P`

- **Estado:** `[x]`
- **Requisitos:** R004, R006, R016
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/ops/__init__.py`
  - `src/backend/app/ops/db_users.py`
  - `src/backend/app/ops/env.py`
  - `src/backend/Dockerfile`
  - `src/backend/migrations/versions/0001_accounts.py`
  - `src/backend/tests/integration/test_db_users.py`
  - `src/backend/tests/integration/test_migrations_rds.py`
  - `src/backend/tests/unit/test_ops_env.py`
  - `src/backend/tests/unit/test_dockerfile.py`
- **Hecho cuando:** pasan:
  - `test_F004_R004_db_users_crea_api_y_worker_sin_bypassrls_createrole_ni_app_migrator`, contra el PostgreSQL del compose;
  - `test_F004_R004_db_users_es_idempotente_y_cambia_la_contrasena`;
  - `test_F004_R004_myplaylist_api_puede_set_role_app_api_y_no_app_migrator`;
  - `test_F004_R004_las_migraciones_corren_en_una_base_nueva_con_un_usuario_createrole_sin_superusuario`, que imita al maestro de RDS. Crea una base aparte, ejecuta `alembic upgrade head` hasta la cabeza y comprueba que ningún rol `app_*` tiene `BYPASSRLS`;
  - `test_F004_R004_la_0001_corrige_un_rol_app_que_ya_tenia_bypassrls`;
  - `test_F004_R006_env_compone_las_url_sin_escribir_la_contrasena_en_el_registro`;
  - `test_F004_R004_el_mando_de_la_imagen_no_migra_al_arrancar`;
  - `test_F004_R016_el_mando_de_la_imagen_desactiva_el_registro_de_acceso_de_uvicorn`.

  El compose sigue migrando al arrancar, como hasta ahora, y las pruebas de esquema y de RLS existentes siguen en verde.

### T009 — Esqueleto de `src/infra/`, arranque y CI de la infraestructura

- **Estado:** `[ ]`
- **Requisitos:** R002
- **Depende de:** —
- **Archivos:**
  - `src/infra/.terraform-version`
  - `src/infra/bootstrap/*.tf`
  - `src/infra/tests/bootstrap.tftest.hcl`
  - `src/infra/README.md`
  - `.github/workflows/ci.yml`
  - `.sdd/config.json`
  - `docs/qa/infra-despliegue.md` (el guion, sin resultados)
- **Hecho cuando:**
  - Pasan:
    - `run "F004_R002_el_rol_de_despliegue_solo_se_asume_desde_los_entornos_de_este_repositorio"`;
    - `run "F004_R002_el_rol_de_plan_es_de_solo_lectura"`.
  - El trabajo `infra` del CI corre `terraform fmt -check`, `validate` y `test` y está en `ci`.
  - Con `.sdd/config.json`, `sdd trace` (local y en la versión fijada en el CI) cuenta los ID de `.tftest.hcl` y de los títulos de `docs/qa/`. Si no los cuenta, se usa el comentario con el ID que prevé D15.
  - Los dos diagramas de `plan.md` se dibujan con la CLI de Mermaid sin errores.
  - `src/infra/README.md` recoge:
    - la lista de requisitos previos de D17;
    - el coste comprobado con AWS Pricing Calculator. Si el total se aparta más de un 20 % del plan, se avisa al usuario.
  - **El usuario,** con credenciales de administrador, aplica el arranque y delega los servidores de nombres de `200oklabs.com` a Route 53, y `dig NS 200oklabs.com` lo muestra.

### T010 — Red `P`

- **Estado:** `[ ]`
- **Requisitos:** R009
- **Depende de:** T009
- **Archivos:**
  - `src/infra/modules/network/*.tf`
  - `src/infra/tests/network.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R009_subredes_publicas_y_privadas_en_dos_zonas"`;
  - `run "F004_R009_los_datos_no_tienen_salida_a_internet"`;
  - `run "F004_R009_las_tareas_solo_admiten_entradas_desde_el_alb"`.

### T011 — Datos: RDS y ElastiCache `P`

- **Estado:** `[ ]`
- **Requisitos:** R009, R010
- **Depende de:** T009
- **Archivos:**
  - `src/infra/modules/data/*.tf`
  - `src/infra/tests/data.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R009_rds_es_multi_az_y_redis_tiene_replica_con_conmutacion"`;
  - `run "F004_R010_rds_guarda_copias_7_dias"`;
  - `run "F004_R010_produccion_protege_contra_borrado_y_guarda_instantanea_final"`;
  - `run "F004_R009_redis_cifra_en_transito_y_exige_token"`.

### T012 — Secretos `P`

- **Estado:** `[ ]`
- **Requisitos:** R006
- **Depende de:** T009
- **Archivos:**
  - `src/infra/modules/secrets/*.tf`
  - `src/infra/tests/secrets.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R006_los_secretos_generados_tienen_48_caracteres"`;
  - `run "F004_R006_youtube_api_key_no_tiene_valor_en_terraform"`.

### T013 — Cómputo: ECS, ECR, ALB y la tarea de migración

- **Estado:** `[ ]`
- **Requisitos:** R001, R004, R005, R006, R009
- **Depende de:** T010, T011, T012
- **Archivos:**
  - `src/infra/modules/compute/*.tf`
  - `src/infra/tests/compute.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R009_cada_servicio_tiene_dos_tareas_o_mas_en_dos_zonas"`;
  - `run "F004_R005_los_servicios_tienen_circuit_breaker_con_vuelta_atras"`;
  - `run "F004_R004_la_api_no_migra_y_existe_la_tarea_de_migracion"`;
  - `run "F004_R006_los_secretos_llegan_como_secrets_y_no_como_environment"`;
  - `run "F004_R009_el_alb_solo_admite_cloudfront_y_su_cabecera"`;
  - `run "F004_R001_ecr_tiene_etiquetas_inmutables"`: una versión desplegada siempre es la imagen construida desde su etiqueta.

### T014 — Borde: CloudFront, certificado, la SPA y el mantenimiento

- **Estado:** `[ ]`
- **Requisitos:** R003, R014, R020
- **Depende de:** T013
- **Archivos:**
  - `src/infra/modules/edge/*.tf`
  - `src/infra/modules/edge/functions/edge.js`
  - `src/infra/modules/edge/functions/edge.test.js`
  - `src/infra/tests/edge.tftest.hcl`
- **Hecho cuando:**
  - Pasan con `node --test`, que el trabajo `infra` del CI también ejecuta:
    - `F004_R014 con maintenance=on devuelve 503 y la página de mantenimiento`;
    - `F004_R014 en /api/* devuelve 503 con error maintenance`;
    - `F004_R014 con maintenance=off deja pasar la petición`;
    - `F004_R003 reescribe a /index.html las rutas de la SPA sin extensión`;
    - `F004_R003 no reescribe /api/*, /socket.io/* ni los archivos con extensión`.
  - Pasan:
    - `run "F004_R003_todas_las_rutas_redirigen_http_a_https_con_tls_1_2"`;
    - `run "F004_R003_api_y_socket_io_van_al_alb_sin_cache"`;
    - `run "F004_R014_la_funcion_edge_esta_en_viewer_request_en_los_tres_comportamientos"`;
    - `run "F004_R003_la_distribucion_no_tiene_respuestas_de_error_personalizadas"`, para que los 404 y 403 de la API lleguen tal cual (R013 de 001);
    - `run "F004_R020_api_reenvia_cloudfront_viewer_address_al_origen"`.

### T015 — Correo: SES en el dominio `P`

- **Estado:** `[ ]`
- **Requisitos:** R008
- **Depende de:** T009
- **Archivos:**
  - `src/infra/modules/email/*.tf`
  - `src/infra/tests/email.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R008_identidad_con_dkim_mail_from_y_dmarc"`;
  - `run "F004_R008_rebotes_y_quejas_van_al_tema_de_avisos"`.

  **El usuario** pide la salida del sandbox de SES (D14), y la solicitud queda anotada en `src/infra/README.md` con su fecha.

### T016 — Observabilidad: registros, alarmas, comprobaciones y presupuesto

- **Estado:** `[ ]`
- **Requisitos:** R011, R012, R013, R016, R020, R021
- **Depende de:** T013, T014
- **Archivos:**
  - `src/infra/modules/observability/*.tf`
  - `src/infra/tests/observability.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R011_hay_una_alarma_por_umbral_de_sg1_a_sg6"`;
  - `run "F004_R012_cada_alarma_avisa_al_tema_con_la_suscripcion_por_correo"`;
  - `run "F004_R013_comprobaciones_de_route_53_cada_30_s"`;
  - `run "F004_R016_todos_los_grupos_de_registros_guardan_30_dias"`;
  - `run "F004_R016_sin_registros_de_acceso_del_alb_ni_de_cloudfront"`;
  - `run "F004_R020_contributor_insights_cuenta_401_y_403_por_ip"`;
  - `run "F004_R021_alarma_de_cuota_de_youtube_en_8000"`, con la estadística `Maximum`, un periodo de 1 minuto y `treat_missing_data = notBreaching`;
  - `run "F004_R011_el_panel_muestra_sg1_a_sg6_y_la_disponibilidad_del_mes"`;
  - `run "presupuesto_con_aviso_por_correo"` (D12, sin requisito propio).

### T017 — Entornos `production` y `preproduction`

- **Estado:** `[ ]`
- **Requisitos:** R022
- **Depende de:** T014, T015, T016
- **Archivos:**
  - `src/infra/main.tf`
  - `src/infra/variables.tf`
  - `src/infra/environments/production.tfvars`
  - `src/infra/environments/preproduction.tfvars`
  - `src/infra/environments/*.backend.hcl`
  - `src/infra/tests/environments.tftest.hcl`
- **Hecho cuando:** pasan:
  - `run "F004_R022_los_dos_entornos_usan_el_mismo_modulo_y_la_misma_capacidad"`;
  - `run "F004_R022_preproduccion_usa_el_catalogo_falso_mailpit_y_su_dominio"`;
  - `run "F004_R022_preproduccion_tiene_la_tarea_de_k6_y_produccion_no"`;
  - `run "F004_R022_todos_los_recursos_llevan_la_etiqueta_environment"`.

### T018 — Flujos de despliegue e infraestructura, y primer despliegue en preproducción

- **Estado:** `[ ]`
- **Requisitos:** R001, R002, R004, R006
- **Depende de:** T001, T002, T003, T004, T005, T006, T007, T008, T017
- **Archivos:**
  - `.github/workflows/deploy.yml`
  - `.github/workflows/infra.yml`
  - `.github/workflows/ci.yml` (actionlint)
  - `docs/qa/infra-despliegue.md`
- **Hecho cuando:**
  - actionlint pasa en el CI.
  - **El usuario** crea los entornos de GitHub con revisor y la regla de etiquetas `v*` (D17).
  - Tras etiquetar `v0.2.0-rc.1`, quedan con resultado en `docs/qa/infra-despliegue.md`, todos contra la preproducción:
    - `F004_R001`: despliegue aprobado, con la etiqueta, quién aprobó y la hora en GitHub;
    - `F004_R002`: el lanzamiento desde una rama se rechaza, y el de una etiqueta espera la aprobación;
    - `F004_R004`: una sola migración en los registros, la revisión de la cabeza y, como la preproducción es una base RDS nueva, que el maestro crea los roles `app_*` y ninguno tiene `BYPASSRLS`;
    - `F004_R006`: ningún valor de secreto en las imágenes, en los registros ni en el repositorio.

### T019 — Preproducción temporal y la prueba de carga de Q2

- **Estado:** `[ ]`
- **Requisitos:** R017, R022
- **Depende de:** T018
- **Archivos:**
  - `.github/workflows/preproduction.yml`
  - `src/perf/client.js`
  - `src/perf/README.md`
  - `docs/qa/infra-resiliencia.md`
- **Hecho cuando:**
  - `accion=levantar` deja la preproducción en marcha con la etiqueta desplegada, y `accion=destruir` la destruye y comprueba que no queda nada.
  - `preproduction.yml`, con `accion=probar-carga` y `establishments=50`, crea la preproducción, despliega, corre k6 en Fargate y destruye. Con eso:
    - **`F004_R017`:** cumple la búsqueda p95 < 2 s, el estado p95 < 1 s y 0 errores 5xx. El resultado queda en la cabecera de `client.js` y en `docs/qa/infra-resiliencia.md`. Si no cumple, se detiene la tarea y se consulta al usuario: tamaño de las tareas, clase de RDS o enmienda.
    - **`F004_R022`:** tras destruir, no queda ningún recurso con la etiqueta `environment=preproduction`, y producción no cambió. El mismo caso registra también la comprobación de `levantar` y `destruir`.

### T020 — Retirar y volver

- **Estado:** `[ ]`
- **Requisitos:** R014, R015
- **Depende de:** T019
- **Archivos:**
  - `.github/workflows/maintenance.yml`
  - `docs/qa/infra-operacion.md`
- **Hecho cuando:** con la preproducción levantada (`accion=levantar`), quedan con resultado en `docs/qa/infra-operacion.md`:
  - **`F004_R014`:** `maintenance.yml retirar` deja en menos de 10 minutos la página de mantenimiento en la dirección del QR y en el panel; un pedido no se acepta, no sale ningún correo y los datos siguen en la base;
  - **`F004_R015`:** `maintenance.yml volver` deja entrar con la misma cuenta y ver el mismo establecimiento y QR.

### T021 — Resiliencia en preproducción

- **Estado:** `[ ]`
- **Requisitos:** R005, R007, R009, R010
- **Depende de:** T019
- **Archivos:** `docs/qa/infra-resiliencia.md`
- **Hecho cuando:** con la preproducción levantada, quedan con resultado:
  - **`F004_R005`:**
    - una etiqueta con una migración que falla a propósito detiene el despliegue, y la revisión anterior sigue atendiendo;
    - una versión que no supera la comprobación de salud vuelve atrás sola.
  - **`F004_R007`:** un despliegue con un secreto de desarrollo no recibe tráfico, y el flujo nombra la variable.
  - **`F004_R009`:**
    - bajo tráfico constante, parar una tarea de cada servicio deja como mucho un 1 % de errores, y la capacidad vuelve en menos de 5 minutos;
    - tras forzar la conmutación de RDS, el servicio vuelve a atender en menos de 5 minutos, y siguen en la base todos los pedidos confirmados (respuesta 201) antes de la conmutación, contados por la prueba y comparados con una consulta.
  - **`F004_R010`:** restaurar a un momento dado en una instancia aparte recupera los pedidos hechos antes.

### T022 — Operación en preproducción: señales, alertas y registros

- **Estado:** `[ ]`
- **Requisitos:** R011, R012, R013, R016, R020, R021
- **Depende de:** T019
- **Archivos:** `docs/qa/infra-operacion.md`
- **Hecho cuando:** con la preproducción levantada, quedan con resultado:
  - **`F004_R011`:** el panel muestra la cifra de cada señal, de SG1 a SG6.
  - **`F004_R012`:** cada alarma forzada llega por correo en menos de 5 minutos, también fuera del horario de los locales.
  - **`F004_R013`:** una retirada de 5 minutos aparece en la comprobación y en la disponibilidad del mes.
  - **`F004_R016`:** en los registros de un inicio de sesión, una búsqueda y un pedido no aparecen la contraseña, los tokens, las cookies ni el texto buscado.
  - **`F004_R020`:** 60 rechazos desde una IP en un minuto envían un correo con esa IP.
  - **`F004_R021`:** la alarma de cuota forzada envía un correo.

  Al terminar, `accion=destruir` no deja recursos.

### T023 — Producción: entorno y versión candidata

- **Estado:** `[ ]`
- **Requisitos:** R001, R003, R006, R008
- **Depende de:** T020, T021, T022, T026
- **Archivos:** `docs/qa/infra-despliegue.md`, `docs/qa/infra-navegadores.md`
- **Hecho cuando:**
  - **Antes de empezar** están cumplidos los requisitos previos de D17: SES fuera del sandbox, `YOUTUBE_API_KEY` en Secrets Manager y la suscripción a los avisos confirmada. Si falta alguno, se detiene la tarea y se avisa al usuario.
  - `infra.yml` aplica producción con aprobación, y `deploy.yml` despliega `v0.2.0-rc.N` con aprobación.
  - Quedan con resultado:
    - `F004_R001` en producción;
    - `F004_R003`: HTTP redirige a HTTPS y el certificado de `myplaylist.200oklabs.com` es válido;
    - `F004_R006` en producción;
    - `F004_R008`: el correo de verificación llega a la bandeja de entrada de Gmail y de Outlook, con la autenticación del dominio aprobada en sus cabeceras.

### T024 — Dispositivos y navegadores reales en producción

- **Estado:** `[ ]`
- **Requisitos:** R018, R019
- **Depende de:** T023
- **Archivos:** `docs/qa/infra-navegadores.md`
- **Hecho cuando:** **el usuario** hace las pruebas, y quedan con dispositivo, navegador, versión, fecha y resultado:
  - **`F004_R018`:** escanear el QR impreso con un iPhone (Safari) y un Android (Chrome), buscar y pedir una canción;
  - **`F004_R019`:** el recorrido del propietario (registro, verificación, QR, sesión y reproducción) en Chrome, Edge, Firefox y Safari de escritorio.

  Con eso se cierran también las pruebas pendientes de 001 y 002 (escaneo del QR, Safari y Edge).

### T025 — Documentación

- **Estado:** `[ ]`
- **Requisitos:** R001
- **Depende de:** T023
- **Archivos:**
  - `src/infra/README.md`
  - `README.md`
  - `src/backend/README.md`
  - `src/perf/README.md`
- **Hecho cuando:** `src/infra/README.md` explica, con los mandos reales:
  - el arranque;
  - los requisitos previos;
  - cómo desplegar, retirar y volver;
  - la preproducción;
  - el procedimiento de emergencia sin GitHub;
  - que las migraciones tienen que ser compatibles con la versión anterior (D8).

  El README raíz marca la feature 004 como implementada y enlaza la guía. `src/backend/README.md` describe `ENV=preproduction`, `app.ops` y el registro por petición.

### T027 — Protección de arranque compartida `P`

- **Estado:** `[ ]`
- **Requisitos:** R016
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/shared/config.py`
  - `src/backend/app/main.py`
  - `src/backend/app/worker.py`
  - `src/backend/tests/unit/test_config.py`
- **Hecho cuando:**
  - `settings_or_exit()` vive en `app/shared/config.py`, y la usan la API y el trabajador, sin copias.
  - Pasa `test_F004_R016_settings_or_exit_escribe_solo_los_mensajes_y_termina_con_1`, en el mismo proceso, con `capsys`.
  - Siguen en verde `test_F004_R016_el_arranque_con_configuracion_invalida_no_escribe_valores` y `test_F004_R016_el_trabajador_con_configuracion_invalida_no_escribe_valores`.

### T026 — La política de tratamiento definitiva `P`

- **Estado:** `[ ]`
- **Requisitos:** R007
- **Depende de:** —
- **Archivos:**
  - `src/backend/app/accounts/policy/<versión>.md`
  - `src/infra/environments/production.tfvars`
  - `src/backend/tests/unit/test_data_policy.py`
- **Hecho cuando:**
  - **El negocio** entrega el texto definitivo de la política de tratamiento. Debe incluir la transferencia internacional de datos a EE. UU. (ADR-0006) y la retención de 30 días de los registros con IP (R016).
  - El texto queda en `src/backend/app/accounts/policy/` con su versión, y `DATA_POLICY_VERSION` de producción la nombra.
  - Pasa `test_F004_R007_production_arranca_con_la_politica_definitiva_y_la_sirve`.
  - El borrador `0000-borrador` sigue sirviendo en local y en la preproducción.

  Hasta que llegue el texto, la tarea queda abierta y bloquea T023.

## Cobertura

| Requisito | Tareas |
| --------- | ------ |
| R001 | T013, T018, T023, T025 |
| R002 | T009, T018 |
| R003 | T014, T023 |
| R004 | T008, T013, T018 |
| R005 | T013, T021 |
| R006 | T008, T012, T013, T018, T023 |
| R007 | T001, T021, T026 |
| R008 | T015, T023 |
| R009 | T010, T011, T013, T021 |
| R010 | T011, T021 |
| R011 | T002, T003, T004, T007, T016, T022 |
| R012 | T016, T022 |
| R013 | T007, T016, T022 |
| R014 | T014, T020 |
| R015 | T020 |
| R016 | T003, T006, T008, T016, T022, T027 |
| R017 | T019 |
| R018 | T024 |
| R019 | T024 |
| R020 | T003, T014, T016, T022 |
| R021 | T005, T016, T022 |
| R022 | T001, T017, T019 |

> Todo requisito MUST debe tener al menos una tarea.
