# Tasks: Sesión de música y reproductor del local

| Campo  | Valor       |
| ------ | ----------- |
| Spec   | `spec.md`   |
| Plan   | `plan.md`   |
| Fecha  | 2026-10-21  |
| Estado | Approved · 2cfb7b1a2298       |

> Cada tarea debe ser verificable por sí sola y caber en una sola sesión de
> trabajo. Si una tarea necesita una decisión que no está en `plan.md`, la tarea
> está mal descompuesta.
>
> Solo el usuario cambia el Estado, con `/sdd:approve`. Las pruebas citan el
> requisito con el prefijo de la feature: `test_F002_R001_…` en Python y
> `F002_R001 …` en el título de las pruebas web y del servicio de tiempo real.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecha
- `P` marca tareas paralelizables (sin dependencias entre sí)

## Tareas

### T001 — Migración de la sesión de música y la cola `P`

- **Estado:** `[x]`
- **Requisitos:** R003, R006, R013
- **Depende de:** —
- **Archivos:** `src/backend/migrations/versions/0002_music_sessions.py`, `src/backend/tests/integration/test_sessions_schema.py`
- **Hecho cuando:**
  - `alembic upgrade head` y `downgrade` hasta `0001_accounts` funcionan contra el PostgreSQL local.
  - Existen `music_session` y `queue_item` con los tipos, los índices y las políticas RLS de D2.
  - Pasan:
    - `test_F002_R003_una_sola_sesion_abierta_por_establecimiento` (la segunda fila abierta viola el índice único parcial);
    - `test_F002_R006_una_sola_cancion_sonando_por_sesion`;
    - `test_F002_R013_rls_oculta_sesiones_y_cola_de_otro_establecimiento` (con el rol `app_api` y otro `app.establishment_id`, 0 filas).
  - La prueba que recorre `pg_tables` de la feature 001 sigue pasando con las tablas nuevas.

### T002 — Dominio: sesión de música y máquina de estados de la cola `P`

- **Estado:** `[x]`
- **Requisitos:** R003, R005, R006, R007, R010, R011, R012
- **Depende de:** —
- **Archivos:** `src/backend/app/sessions/__init__.py`, `src/backend/app/sessions/domain/{__init__.py,music_session.py,queue.py,ports.py}`, `src/backend/tests/unit/test_queue_state.py`, `src/backend/tests/unit/test_music_session_rules.py`, `src/backend/tests/unit/test_health.py`
- **Hecho cuando:** pasan:
  - `test_F002_R003_abrir_con_una_abierta_no_crea_otra`;
  - `test_F002_R005_avanza_en_el_orden_de_la_cola`;
  - `test_F002_R006_terminada_o_saltada_no_vuelve_a_sonar`;
  - `test_F002_R007_fallida_se_salta_con_motivo`;
  - `test_F002_R010_poner_en_marcha_incrementa_la_epoca_y_rechaza_la_vieja`;
  - `test_F002_R010_poner_en_marcha_devuelve_la_que_sonaba_desde_el_principio`;
  - `test_F002_R011_cerrar_descarta_pendientes_y_conserva_sonadas`;
  - `test_F002_R011_cerrar_deja_la_que_sonaba_como_sonada`;
  - `test_F002_R012_informe_repetido_no_cambia_nada`.

  Además, la prueba de importaciones de la feature 001 (`test_health.py`) también recorre `app/sessions/domain`, y sigue sin FastAPI ni SQLAlchemy (S1).

### T003 — Publicación de eventos por Redis

- **Estado:** `[x]`
- **Requisitos:** R008, R014
- **Depende de:** T002
- **Archivos:** `src/backend/app/sessions/infrastructure/{__init__.py,redis_publisher.py,memory_publisher.py}`, `src/backend/app/shared/config.py` (`REDIS_URL`), `src/backend/pyproject.toml`, `src/backend/uv.lock`, `src/backend/tests/integration/test_event_publisher.py`, `.github/workflows/ci.yml` (Redis en `backend-integration`)
- **Hecho cuando:** pasan, contra el Redis de docker-compose:
  - `test_F002_R014_publica_en_el_canal_del_establecimiento` (canal `est:{id}`, con `type`, `session_id` y `version`);
  - `test_F002_R008_evento_sin_datos_de_la_cuenta` (el cuerpo solo lleva los campos de los contratos del plan).

  El publicador en memoria sirve a las pruebas de los casos de uso. `redis` queda en `uv.lock` (D10).

### T004 — Unidad de trabajo y casos de uso de la sesión de música

- **Estado:** `[x]`
- **Requisitos:** R001, R003, R011
- **Depende de:** T001, T002, T003
- **Archivos:** `src/backend/app/sessions/infrastructure/repositories.py`, `src/backend/app/sessions/application/{__init__.py,open_session.py,close_session.py,get_session.py}`, `src/backend/tests/integration/test_music_session_use_cases.py`, `src/backend/app/sessions/application/publishing.py`, `src/backend/app/sessions/domain/ports.py`
- **Hecho cuando:** pasan:
  - `test_F002_R001_abrir_deja_la_sesion_abierta_con_la_cola_vacia`;
  - `test_F002_R003_dos_aperturas_concurrentes_dejan_una_sola_sesion` (con la cola intacta);
  - `test_F002_R011_cerrar_descarta_pendientes_y_publica_session_closed`;
  - `test_F002_R011_cerrar_con_una_sonando_la_deja_en_played`.

  Cada transición bloquea la fila de la sesión (`SELECT … FOR UPDATE`), y los eventos se publican después del commit (D2, D6).

### T005 — Rutas de la sesión de música

- **Estado:** `[x]`
- **Requisitos:** R001, R002, R003, R011, R013
- **Depende de:** T004
- **Archivos:** `src/backend/app/sessions/api/{__init__.py,music_session.py}`, `src/backend/app/main.py`, `src/backend/tests/integration/test_music_session.py`, `src/backend/app/sessions/application/open_session.py`, `src/backend/app/sessions/infrastructure/redis_publisher.py`, `src/backend/tests/integration/api.py`
- **Hecho cuando:** pasan:
  - `test_F002_R001_post_abre_la_sesion_201`;
  - `test_F002_R002_correo_sin_verificar_da_403_y_sigue_cerrada`;
  - `test_F002_R003_post_con_sesion_abierta_da_200_sin_vaciar_la_cola`;
  - `test_F002_R011_delete_cierra_y_es_idempotente`;
  - `test_F002_R013_sin_sesion_iniciada_da_401`.

  `GET /api/owner/music-session` devuelve la forma de los contratos del plan.

### T006 — Puesta en marcha del reproductor y latido

- **Estado:** `[x]`
- **Requisitos:** R004, R008, R009, R010, R014
- **Depende de:** T005
- **Archivos:** `src/backend/app/sessions/application/{claim_player.py,heartbeat.py}`, `src/backend/app/sessions/api/player.py`, `src/backend/tests/integration/test_player.py`, `src/backend/app/main.py`
- **Hecho cuando:** pasan:
  - `test_F002_R004_poner_en_marcha_devuelve_la_primera_pendiente`;
  - `test_F002_R009_sin_sesion_abierta_da_409_no_open_session`;
  - `test_F002_R010_segunda_puesta_en_marcha_supera_a_la_primera` (la primera recibe `409 player_superseded` en su latido; se publica `player.claimed`);
  - `test_F002_R010_nuevo_reproductor_recibe_la_cancion_que_sonaba`;
  - `test_F002_R014_player_active_segun_el_latido` (activo con un latido de menos de 45 s);
  - `test_F002_R014_latido_mantiene_viva_la_sesion_iniciada`;
  - `test_F002_R008_latido_devuelve_la_version_de_la_sesion` (crece tras un `EnqueueTrack`).

### T007 — Informes del reproductor y avance de la cola

- **Estado:** `[x]`
- **Requisitos:** R005, R006, R007, R010, R011, R012
- **Depende de:** T006
- **Archivos:** `src/backend/app/sessions/application/report_player_event.py`, `src/backend/app/sessions/api/player.py`, `src/backend/tests/integration/test_player.py`, `src/backend/app/main.py`
- **Hecho cuando:** pasan:
  - `test_F002_R005_ended_devuelve_la_siguiente_en_orden`;
  - `test_F002_R006_poner_en_marcha_otra_vez_no_repite_sonadas_ni_saltadas`;
  - `test_F002_R007_failed_salta_y_publica_track_failed`;
  - `test_F002_R007_get_music_session_devuelve_el_fallo` (el aviso sobrevive a recargar el panel, D7);
  - `test_F002_R010_informe_de_epoca_vieja_da_409_player_superseded`;
  - `test_F002_R011_informe_con_la_sesion_cerrada_da_409_no_open_session`;
  - `test_F002_R012_informe_reenviado_tras_un_corte_es_idempotente`.

### T008 — Agregar canciones a la cola: interfaz de C2 y herramienta de desarrollo

- **Estado:** `[x]`
- **Requisitos:** R008
- **Depende de:** T004
- **Archivos:** `src/backend/app/sessions/application/enqueue_track.py`, `src/backend/app/sessions/interface.py`, `src/backend/app/sessions/devtools.py`, `src/backend/tests/integration/test_enqueue_track.py`, `src/backend/app/sessions/domain/music_session.py`, `src/backend/tests/unit/test_music_session_rules.py`, `src/backend/tests/integration/test_player.py`
- **Hecho cuando:** pasan:
  - `test_F002_R008_enqueue_agrega_al_final_y_publica_queue_changed`;
  - `test_F002_R008_enqueue_sin_sesion_abierta_lanza_no_open_session`;
  - una prueba de que `devtools enqueue` se niega a correr con `ENV=production`.

  `docker compose exec api python -m app.sessions.devtools enqueue --email … --title … --ref fake:3s` agrega una canción a la sesión abierta de ese propietario.

### T009 — Ticket de tiempo real en el monolito `P`

- **Estado:** `[x]`
- **Requisitos:** R013, R014
- **Depende de:** T005
- **Archivos:** `src/backend/app/shared/realtime_ticket.py`, `src/backend/app/sessions/api/realtime.py`, `src/backend/app/shared/config.py` (`REALTIME_TICKET_SECRET`), `src/backend/tests/unit/test_realtime_ticket.py`, `src/backend/tests/integration/test_realtime_ticket_api.py`, `src/realtime/test/fixtures/ticket-vectors.json`, `src/backend/app/main.py`, `src/backend/tests/unit/test_email.py`, `src/backend/tests/integration/test_enqueue_track.py`
- **Hecho cuando:** pasan:
  - `test_F002_R013_ticket_lleva_el_establecimiento_de_la_sesion` (y no el del cuerpo);
  - `test_F002_R013_ticket_caduca_a_los_60_s` (con reloj falso);
  - `test_F002_R014_post_realtime_ticket_200_con_rol_owner_o_player`;
  - una prueba de que `ENV=production` no arranca sin `REALTIME_TICKET_SECRET`.

  Los vectores de prueba (secreto, entrada y ticket esperado) quedan en `ticket-vectors.json`, para que C6 compruebe que valida exactamente lo que firma el monolito (ADR-0014).

### T010 — Batería de aislamiento de la sesión de música

- **Estado:** `[x]`
- **Requisitos:** R013
- **Depende de:** T006, T007, T008
- **Archivos:** `src/backend/tests/integration/test_isolation.py`
- **Hecho cuando:** con los establecimientos A y B, pasan:
  - `test_F002_R013_sesion_de_a_no_abre_ni_cierra_la_de_b`;
  - `test_F002_R013_reproductor_de_a_no_reclama_ni_informa_en_b` (los `item_id` de B dan 404 con la sesión de A, y la cola de B no cambia);
  - `test_F002_R013_get_music_session_de_a_no_muestra_lo_que_suena_en_b`.

### T011 — Servicio de tiempo real: proyecto, tickets y salas

- **Estado:** `[x]`
- **Requisitos:** R013
- **Depende de:** T009
- **Archivos:** `src/realtime/{package.json,package-lock.json,tsconfig.json,tsconfig.test.json,eslint.config.js,.nvmrc,vitest.config.ts}`, `src/realtime/src/{server.ts,ticket.ts,rooms.ts}`, `src/realtime/test/{ticket.test.ts,rooms.test.ts}`, `.gitignore` (salida del build de `src/realtime/`)
- **Hecho cuando:**
  - `npm run lint` (eslint y tsc) y `npm test` pasan en `src/realtime`.
  - Pasan:
    - `F002_R013 valida los vectores de ticket del monolito`;
    - `F002_R013 rechaza ticket caducado, mal firmado o alterado`;
    - `F002_R013 une el socket solo a la sala est:{id} de su ticket`;
    - `F002_R013 un socket no puede unirse a la sala de otro establecimiento`;
    - `F002_R013 en producción no arranca sin REALTIME_TICKET_SECRET`.
  - Va en paralelo con T006–T008 y T010, porque solo depende del ticket (T009).

### T012 — Servicio de tiempo real: reenvío de Redis a las salas

- **Estado:** `[x]`
- **Requisitos:** R008, R010, R011, R014
- **Depende de:** T011
- **Archivos:** `src/realtime/src/relay.ts`, `src/realtime/src/server.ts`, `src/realtime/test/{relay.test.ts,rooms.test.ts}`, `src/realtime/package.json` (script de pruebas contra Redis)
- **Hecho cuando:** contra el Redis de docker-compose, pasan:
  - `F002_R014 un mensaje de est:{id} llega a su sala en menos de 1 s`;
  - `F002_R014 un mensaje de est:{a} no llega a la sala de b`;
  - `F002_R011 reenvía session.closed tal cual`;
  - `F002_R010 reenvía player.claimed tal cual`;
  - `F002_R008 reenvía queue.changed tal cual`.

### T013 — Entorno local y CI para el tiempo real

- **Estado:** `[x]`
- **Requisitos:** R014
- **Depende de:** T003, T012
- **Archivos:** `src/realtime/Dockerfile`, `src/realtime/.dockerignore`, `src/realtime/README.md`, `src/docker-compose.yml` (servicio `realtime`, y `REDIS_URL` y el mismo `REALTIME_TICKET_SECRET` en `realtime`, `api` y `worker`), `src/.env.example`, `src/web/vite.config.ts` (proxy `/socket.io`), `.github/workflows/ci.yml` (trabajo `realtime`)
- **Hecho cuando:**
  - `docker compose up -d --build` deja `realtime` en `healthy`, junto con el resto.
  - Desde el navegador, `http://localhost:5173/socket.io/?EIO=4&transport=polling` responde a través del proxy de Vite.
  - El CI tiene el trabajo `realtime` (lint, tipos y Vitest contra un Redis de servicio), filtrado por `src/realtime/**`.

### T014 — Cliente de tiempo real y tipos de la API en la web

- **Estado:** `[x]`
- **Requisitos:** R008, R010, R011, R014
- **Depende de:** T007, T009, T012
- **Archivos:** `src/web/src/api/schema.d.ts` (regenerado), `src/web/src/realtime/{client.ts,useRoomEvents.ts}`, `src/web/src/realtime/client.test.ts`, `src/web/package.json`, `src/web/package-lock.json`
- **Hecho cuando:**
  - `npm run gen:api` deja `schema.d.ts` con las rutas nuevas, sin diferencias en el CI.
  - Pasan, con un socket falso:
    - `F002_R014 pide un ticket antes de conectar y de cada reconexión`;
    - `F002_R014 ante un salto de versión pide el estado completo a la API`;
    - `F002_R008 entrega queue.changed a los suscriptores`.
  - `socket.io-client` queda en `package-lock.json` (D10).

### T015 — Adaptadores de proveedor de reproducción `P`

- **Estado:** `[x]`
- **Requisitos:** R005, R007
- **Depende de:** —
- **Archivos:** `src/web/src/features/player/provider/{types.ts,fake.ts,youtube.ts,index.ts}`, `src/web/src/features/player/provider/{fake.test.ts,youtube.test.ts}`
- **Hecho cuando:** pasan:
  - `F002_R005 el proveedor falso termina tras la duración de su referencia`;
  - `F002_R007 el proveedor falso emite error con fake:error`;
  - `F002_R005 youtube precarga la siguiente en la instancia libre y alterna`, con la API del IFrame simulada;
  - `F002_R007 youtube traduce los errores del IFrame en error`;
  - una prueba de que el build de producción no incluye el proveedor falso (`VITE_PLAYBACK_PROVIDER` ignorado en `MODE=production`).

### T016 — Reproductor del local

- **Estado:** `[x]`
- **Requisitos:** R004, R005, R006, R007, R008, R009, R010, R011, R012
- **Depende de:** T014, T015, T021
- **Archivos:** `src/web/src/features/player/{PlayerController.ts,pendingReports.ts,Player.tsx,Player.test.tsx}`, `src/web/src/routes/player.tsx`, `src/web/src/router.tsx` (ruta `/panel/reproductor`)
- **Hecho cuando:** pasan, con el proveedor falso, la API falsa y el tiempo real falso:
  - `F002_R004 poner en marcha reproduce la primera pendiente`;
  - `F002_R005 al terminar informa ended y reproduce la siguiente`;
  - `F002_R006 no reproduce una canción que el servidor ya dio por sonada`;
  - `F002_R007 sin sonar en 10 s informa failed y sigue`;
  - `F002_R008 en espera no suena y reproduce al llegar queue.changed` (pide `POST …/player/advance`, D4);
  - `F002_R008 un salto de versión en el latido hace pedir el estado`;
  - `F002_R009 sin sesión abierta lo indica y no reproduce`;
  - `F002_R010 ante player_superseded o player.claimed se detiene y lo indica`;
  - `F002_R011 ante session.closed se detiene`;
  - `F002_R012 sin conexión guarda los informes en sessionStorage y los reenvía en orden`;
  - `F002_R012 al reconectar con player_superseded se detiene y descarta los informes`.

  `router.test.tsx` incluye la ruta nueva.

### T017 — Tarjeta de sesión de música en el panel

- **Estado:** `[x]`
- **Requisitos:** R001, R002, R007, R011, R014
- **Depende de:** T014
- **Archivos:** `src/web/src/features/music-session/{MusicSessionCard.tsx,MusicSessionCard.test.tsx,useMusicSession.ts}`, `src/web/src/features/owner-panel/Panel.tsx`
- **Hecho cuando:** pasan:
  - `F002_R001 abrir muestra la sesión abierta`;
  - `F002_R002 sin verificar muestra el aviso con reenvío y sigue cerrada`;
  - `F002_R007 muestra el aviso de la canción que falló, también tras recargar`;
  - `F002_R011 cerrar muestra la sesión cerrada`;
  - `F002_R014 muestra lo que suena y si hay reproductor activo, y se actualiza con track.started`.

### T018 — Pruebas e2e del reproductor

- **Estado:** `[x]`
- **Requisitos:** R005, R007, R008, R010, R011, R012, R014, R015
- **Depende de:** T008, T013, T016, T017, T020
- **Archivos:** `src/web/e2e/player.spec.ts`, `src/web/e2e/helpers/queue.ts`
- **Hecho cuando:** `npx playwright test` pasa contra el entorno de docker-compose con `VITE_PLAYBACK_PROVIDER=fake`, y las canciones se agregan con `devtools enqueue`. Los tests son:
  - `F002_R005 A, B y C suenan en orden con huecos de menos de 3 s`;
  - `F002_R007 una canción que falla se salta en menos de 3 s y el panel avisa en menos de 1 s`;
  - `F002_R008 en espera, la canción que entra suena en menos de 3 s`;
  - `F002_R010 dos contextos: el primero se detiene en menos de 3 s y lo indica`;
  - `F002_R011 cerrar la sesión detiene la música en menos de 3 s`;
  - `F002_R011 cerrar durante un corte detiene al reconectar`;
  - `F002_R012 un corte durante A sigue con B al terminar A`;
  - `F002_R012 un corte al terminar A sigue con B al reconectar`;
  - `F002_R012 cambio a otro reproductor durante un corte: el primero se detiene al reconectar`;
  - `F002_R015 restablecer la contraseña: A termina, pide entrar y tras entrar suena B y no A`;
  - `F002_R014 el panel muestra lo que suena en menos de 1 s`.

### T019 — Prueba manual con YouTube real

- **Estado:** `[ ]`
- **Requisitos:** R005, R007
- **Depende de:** T018
- **Archivos:** `docs/qa/reproductor-youtube.md`
- **Hecho cuando:** `docs/qa/reproductor-youtube.md` recoge, con navegador, versión, fecha y resultado, la prueba en Chrome, Edge, Firefox y Safari de escritorio:
  - puesta en marcha;
  - tres canciones seguidas, con un hueco de menos de 3 s fuera de la publicidad;
  - un video que no se puede insertar, que se salta y se avisa en el panel;
  - una hora de reproducción en una pestaña en segundo plano, sin cortes.

### T020 — Reproductor ante el cierre de la sesión iniciada

- **Estado:** `[x]`
- **Requisitos:** R015
- **Depende de:** T016
- **Archivos:** `src/web/src/features/player/{PlayerController.ts,Player.tsx,Player.test.tsx}`
- **Hecho cuando:** pasan, con el proveedor falso y la API falsa:
  - `F002_R015 ante un 401 termina la canción sin redirigir y no empieza la siguiente`;
  - `F002_R015 al terminar guarda el ended y muestra el aviso con el enlace a entrar`;
  - `F002_R015 al poner en marcha entrega primero los informes guardados y suena la siguiente`;
  - `F002_R015 si los informes guardados reciben player_superseded se descartan y pone en marcha como en R010`.

  El reproductor usa su propia instancia del cliente de la API, con una `navigate` que no redirige (D11).

### T021 — Avanzar en espera

- **Estado:** `[x]`
- **Requisitos:** R008, R010, R013
- **Depende de:** T007
- **Archivos:** `src/backend/app/sessions/domain/music_session.py`, `src/backend/app/sessions/application/advance_player.py`, `src/backend/app/sessions/api/player.py`, `src/backend/app/main.py`, `src/backend/tests/unit/test_music_session_rules.py`, `src/backend/tests/integration/{test_player.py,test_isolation.py}`, `src/web/src/api/schema.d.ts` (tipos regenerados)
- **Hecho cuando:** pasan:
  - `test_F002_R008_avanzar_en_espera_empieza_la_primera_pendiente` (unitaria);
  - `test_F002_R008_avanzar_con_una_cancion_sonando_no_cambia_nada` (unitaria; tampoco sin pendientes, y la versión no crece);
  - `test_F002_R008_avanzar_en_espera_empieza_la_que_entro_y_publica_queue_changed` (integración);
  - `test_F002_R010_avanzar_con_epoca_vieja_da_409_player_superseded`;
  - `test_F002_R011_avanzar_con_la_sesion_cerrada_da_409_no_open_session`;
  - la batería de aislamiento incluye la ruta nueva (R013).

  `schema.d.ts` tiene la ruta nueva.

## Cobertura

| Requisito | Tareas |
| --------- | ------ |
| R001 | T004, T005, T017 |
| R002 | T005, T017 |
| R003 | T001, T002, T004, T005 |
| R004 | T006, T016 |
| R005 | T002, T007, T015, T016, T018, T019 |
| R006 | T001, T002, T007, T016 |
| R007 | T002, T007, T015, T016, T017, T018, T019 |
| R008 | T003, T006, T008, T012, T014, T016, T018, T021 |
| R009 | T006, T016 |
| R010 | T002, T006, T007, T012, T014, T016, T018, T021 |
| R011 | T002, T004, T005, T007, T012, T014, T016, T017, T018, T021 |
| R012 | T002, T007, T016, T018 |
| R013 | T001, T005, T009, T010, T011, T021 |
| R014 | T003, T006, T009, T012, T013, T014, T017, T018 |
| R015 | T018, T020 |

> Todo requisito MUST debe tener al menos una tarea. Los catorce MUST (R001–R013 y R015) y el SHOULD R014 tienen tareas y pruebas previstas.
