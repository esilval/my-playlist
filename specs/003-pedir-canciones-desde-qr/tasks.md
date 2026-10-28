# Tasks: Pedir canciones desde el QR

| Campo  | Valor       |
| ------ | ----------- |
| Spec   | `spec.md`   |
| Plan   | `plan.md`   |
| Fecha  | 2026-10-27  |
| Estado | Approved · 65677228e18f       |

> Cada tarea debe ser verificable por sí sola y caber en una sola sesión de
> trabajo. Si una tarea necesita una decisión que no está en `plan.md`, la tarea
> está mal descompuesta.
>
> Solo el usuario cambia el Estado, con `/sdd:approve`. Las pruebas citan el
> requisito con el prefijo de la feature: `test_F003_R001_…` en Python y
> `F003_R001 …` en el título de las pruebas web y del servicio de tiempo real.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecha
- `P` marca tareas paralelizables (sin dependencias entre sí)

## Tareas

### T001 — Migración: quién pidió cada canción `P`

- **Estado:** `[x]`
- **Requisitos:** R002, R006
- **Depende de:** —
- **Archivos:** `src/backend/migrations/versions/0003_queue_requests.py`, `src/backend/tests/integration/test_sessions_schema.py`
- **Hecho cuando:**
  - `alembic upgrade head` y `alembic downgrade -1` funcionan contra el PostgreSQL del compose.
  - Pasan:
    - `test_F003_R002_queue_item_solo_guarda_el_dispositivo_del_cliente`: la columna nueva es `requested_by uuid NULL` y no hay ninguna otra columna del cliente;
    - `test_F003_R006_indice_parcial_de_pendientes_por_dispositivo`.
  - La prueba de RLS de `test_schema.py` sigue en verde.

### T002 — Dominio: el pedido del cliente, con cupo y sin duplicadas `P`

- **Estado:** `[x]`
- **Requisitos:** R005, R006, R007, R008, R009
- **Depende de:** —
- **Archivos:** `src/backend/app/sessions/domain/{music_session.py,queue.py}`, `src/backend/tests/unit/test_music_session_rules.py`
- **Hecho cuando:** pasan:
  - `test_F003_R005_pedir_pone_la_cancion_al_final_con_su_dispositivo`;
  - `test_F003_R006_con_5_pendientes_lanza_quota_exceeded`;
  - `test_F003_R006_el_cupo_es_de_cada_dispositivo`;
  - `test_F003_R007_la_que_suena_se_salta_o_se_descarta_no_cuenta`;
  - `test_F003_R008_pedir_con_la_sesion_cerrada_lanza_no_open_session`;
  - `test_F003_R009_una_pendiente_no_se_puede_volver_a_pedir`;
  - `test_F003_R009_una_que_ya_sono_si_se_puede_pedir`.

  `MusicSession.enqueue` sigue sirviendo a la herramienta de desarrollo, con `requested_by=None`.

### T003 — Token del dispositivo `P`

- **Estado:** `[x]`
- **Requisitos:** R002, R011
- **Depende de:** —
- **Archivos:** `src/backend/app/shared/device_token.py`, `src/backend/tests/unit/test_device_token.py`
- **Hecho cuando:** pasan:
  - `test_F003_R002_el_token_del_dispositivo_se_verifica_con_su_establecimiento`;
  - `test_F003_R002_dos_tokens_tienen_dispositivos_distintos`;
  - `test_F003_R011_token_de_otro_establecimiento_no_vale`;
  - `test_F003_R011_token_alterado_o_de_otro_secreto_no_vale`.

### T004 — Catálogo: puerto y adaptadores de YouTube y falso `P`

- **Estado:** `[x]`
- **Requisitos:** R003, R004, R012, R014
- **Depende de:** —
- **Archivos:** `src/backend/app/catalog/{__init__.py,domain/,infrastructure/youtube.py,infrastructure/fake.py}`, `src/backend/tests/unit/test_youtube_catalog.py`, `src/backend/tests/unit/test_fake_catalog.py`, `src/backend/pyproject.toml` y `src/backend/uv.lock` (`httpx2` a dependencias de ejecución, D9)
- **Hecho cuando:** pasan, con `httpx2.MockTransport` y sin red:
  - `test_F003_R003_youtube_normaliza_titulo_y_canal_y_forma_yt_id` (incluidas las entidades HTML);
  - `test_F003_R004_la_busqueda_pide_solo_videos_que_se_pueden_insertar`;
  - `test_F003_R004_lookup_de_un_video_que_no_se_puede_insertar_da_none`;
  - `test_F003_R012_youtube_lanza_catalog_unavailable_ante_5xx_cuota_o_espera`;
  - `test_F003_R014_lookup_de_un_video_que_ya_no_existe_da_none`;
  - `test_F003_R003_el_catalogo_falso_es_determinista_con_sus_textos_especiales`.

  La clave de YouTube y el texto de la búsqueda no aparecen en ningún mensaje de error ni en el log (`test_F003_R012_ni_la_clave_ni_el_texto_buscado_van_al_log`).

### T005 — Catálogo: caché, límite por dispositivo e interfaz

- **Estado:** `[x]`
- **Requisitos:** R003, R012, R013, R014
- **Depende de:** T004
- **Archivos:** `src/backend/app/catalog/{application/,infrastructure/cache.py,interface.py}`, `src/backend/tests/integration/test_catalog_cache.py`
- **Hecho cuando:** contra el Redis del compose, pasan:
  - `test_F003_R003_una_busqueda_repetida_sale_de_la_cache`;
  - `test_F003_R014_lookup_siempre_pregunta_al_proveedor_aunque_se_haya_buscado`;
  - `test_F003_R013_la_busqueda_11_en_un_minuto_lanza_search_rate_exceeded`;
  - `test_F003_R013_sin_redis_la_busqueda_sigue`;
  - `test_F003_R012_catalog_unavailable_llega_sin_cachear_nada`.

  Todas las claves llevan el prefijo `est:{id}` (S8).

### T006 — Casos de uso del cliente en C2

- **Estado:** `[x]`
- **Requisitos:** R005, R006, R007, R008, R009, R010, R014
- **Depende de:** T001, T002, T005
- **Archivos:** `src/backend/app/sessions/application/{request_track.py,client_view.py}`, `src/backend/app/sessions/infrastructure/repositories.py`, `src/backend/app/sessions/interface.py`, `src/backend/tests/integration/test_request_track.py`
- **Hecho cuando:** contra PostgreSQL con el rol `app_api` y el catálogo falso, pasan:
  - `test_F003_R005_request_track_agrega_al_final_y_publica_queue_changed`;
  - `test_F003_R005_el_titulo_lo_pone_el_catalogo_no_el_cliente`;
  - `test_F003_R006_dos_pedidos_concurrentes_no_superan_el_cupo`;
  - `test_F003_R007_tras_started_failed_o_cerrar_el_cupo_vuelve`;
  - `test_F003_R009_dos_pedidos_concurrentes_de_la_misma_cancion_dejan_una`;
  - `test_F003_R010_client_view_da_lo_que_suena_las_pendientes_propias_y_el_cupo`;
  - `test_F003_R014_una_cancion_que_el_catalogo_ya_no_reconoce_lanza_unknown_track`.

### T007 — Configuración y composición

- **Estado:** `[x]`
- **Requisitos:** R002, R003
- **Depende de:** T003, T005
- **Archivos:** `src/backend/app/shared/config.py`, `src/backend/app/main.py`, `src/docker-compose.yml`, `src/.env.example`, `src/backend/tests/unit/test_catalog_config.py`; y las pruebas que construyen una configuración de producción o comprueban las capas: `src/backend/tests/unit/{test_health.py,test_email.py,test_realtime_ticket.py}`, `src/backend/tests/integration/test_enqueue_track.py`
- **Hecho cuando:**
  - Pasan:
    - `test_F003_R003_en_local_el_catalogo_es_el_falso`;
    - `test_F003_R003_produccion_no_arranca_sin_clave_de_youtube_o_con_el_catalogo_falso`;
    - `test_F003_R002_produccion_no_arranca_con_el_secreto_de_dispositivo_de_desarrollo`.
  - `docker compose up -d --build` deja `api` en `healthy` con `CATALOG_PROVIDER=fake`.

### T008 — Rutas públicas del cliente

- **Estado:** `[x]`
- **Requisitos:** R001, R002, R003, R005, R006, R008, R009, R010, R012, R013, R014
- **Depende de:** T006, T007, T016
- **Archivos:** `src/backend/app/sessions/api/client.py`, `src/backend/app/main.py`, `src/backend/tests/integration/test_client_music.py`
- **Hecho cuando:** contra PostgreSQL, Redis y el catálogo falso, pasan:
  - `test_F003_R001_get_music_con_la_sesion_abierta_sin_sesion_iniciada`;
  - `test_F003_R002_get_music_emite_la_cookie_con_path_httponly_y_secure`;
  - `test_F003_R002_con_la_misma_cookie_se_ven_las_mismas_pendientes`;
  - `test_F003_R003_search_devuelve_titulo_autor_y_ref`;
  - `test_F003_R005_post_requests_da_201_con_el_cupo`;
  - `test_F003_R006_post_requests_con_el_cupo_lleno_da_409_quota_exceeded`;
  - `test_F003_R008_con_la_sesion_cerrada_music_da_closed_y_search_y_requests_409`;
  - `test_F003_R009_post_requests_de_una_pendiente_da_409_already_queued`;
  - `test_F003_R014_post_requests_de_una_cancion_no_disponible_da_422_sin_gastar_cupo`;
  - `test_F003_R014_una_referencia_de_mas_de_64_caracteres_da_422_sin_consultar_al_catalogo`;
  - `test_F003_R010_music_refleja_la_cancion_que_empieza_a_sonar`;
  - `test_F003_R012_search_con_el_proveedor_caido_da_503`;
  - `test_F003_R013_search_11_en_un_minuto_da_429_con_retry_after`;
  - `test_F003_R001_codigo_inexistente_da_404_en_todas_las_rutas`;
  - `test_F003_R002_sin_cookie_search_y_requests_dan_401_device_required`.

### T009 — Ticket de tiempo real del cliente

- **Estado:** `[x]`
- **Requisitos:** R010, R011
- **Depende de:** T008
- **Archivos:** `src/backend/app/shared/realtime_ticket.py`, `src/backend/app/sessions/api/client.py`, `src/backend/tests/integration/test_client_music.py`, `src/realtime/src/ticket.ts`, `src/realtime/test/{ticket.test.ts,rooms.test.ts}`, `src/realtime/test/fixtures/ticket-vectors.json`
- **Hecho cuando:** pasan:
  - `test_F003_R010_post_realtime_ticket_da_un_ticket_client_del_establecimiento` (backend);
  - `F003_R010 acepta el ticket client y lo une a la sala de su establecimiento` (C6);
  - `F003_R011 un ticket client de un establecimiento no entra en la sala de otro` (C6).

  Los vectores compartidos incluyen un ticket `client`.

### T010 — Batería de aislamiento del cliente

- **Estado:** `[ ]`
- **Requisitos:** R011
- **Depende de:** T008, T009
- **Archivos:** `src/backend/tests/integration/test_isolation.py`
- **Hecho cuando:** pasan:
  - `test_F003_R011_con_la_cookie_de_a_en_b_es_un_dispositivo_nuevo_con_cupo_completo`;
  - `test_F003_R011_un_pedido_en_b_con_la_cookie_de_a_da_401_y_no_cambia_ninguna_cola`;
  - `test_F003_R011_nadie_ve_los_pedidos_de_otro_dispositivo_ni_de_otro_establecimiento`.

  Comprueban que en las respuestas no aparece ningún pedido de otro dispositivo ni de otro establecimiento: ni títulos, ni identificadores, ni dispositivos.

### T011 — Web: tipos de la API y cliente de tiempo real generalizado

- **Estado:** `[ ]`
- **Requisitos:** R010
- **Depende de:** T009
- **Archivos:** `src/web/src/api/schema.d.ts` (regenerado), `src/web/src/realtime/{client.ts,useRoomEvents.ts,client.test.ts}`, `src/web/src/features/player/Player.tsx`, `src/web/src/features/music-session/MusicSessionCard.tsx`
- **Hecho cuando:**
  - Pasa `F003_R010 el cliente de tiempo real usa el ticket y el estado que recibe`.
  - Las pruebas del panel y del reproductor siguen en verde.
  - El trabajo `api-types` del CI no ve diferencias.

### T012 — Web: la página del cliente

- **Estado:** `[ ]`
- **Requisitos:** R001, R003, R005, R006, R008, R009, R010, R012, R013, R014
- **Depende de:** T011
- **Archivos:** `src/web/src/features/public-establishment/{PublicEstablishment.tsx,useClientMusic.ts,SongSearch.tsx,MyRequests.tsx,PublicEstablishment.test.tsx}`
- **Hecho cuando:** con la API falsa y el tiempo real falso, pasan:
  - `F003_R001 con la sesión abierta muestra el nombre y el buscador`;
  - `F003_R003 muestra los resultados con título y autor, o que no hay`;
  - `F003_R003 solo busca al pulsar Buscar, no mientras se escribe`;
  - `F003_R005 pedir muestra la canción entre las mías y el cupo actualizado`;
  - `F003_R006 con el cupo lleno avisa de cuándo lo recupera`;
  - `F003_R008 con la sesión cerrada avisa y no muestra el buscador`;
  - `F003_R009 avisa de que la canción ya está en la cola`;
  - `F003_R010 al llegar queue.changed pide el estado y lo muestra`;
  - `F003_R012 avisa de que la búsqueda no está disponible`;
  - `F003_R013 avisa de que espere tras demasiadas búsquedas`;
  - `F003_R014 avisa de que la canción no está disponible y que elija otra`.

  Las pruebas de la feature 001 sobre esta página siguen en verde.

### T013 — Pruebas e2e del cliente

- **Estado:** `[ ]`
- **Requisitos:** R001, R005, R006, R010
- **Depende de:** T012
- **Archivos:** `src/web/e2e/client.spec.ts`, `src/web/e2e/helpers/queue.ts`
- **Hecho cuando:** `npx playwright test e2e/client.spec.ts` pasa contra el compose, con el catálogo falso y el proveedor de reproducción falso. Los tests son:
  - `F003_R001 desde la URL del QR se busca y se pide sin registrarse`;
  - `F003_R005 la canción pedida suena en el reproductor que estaba en espera`;
  - `F003_R006 dos móviles: cada uno tiene su cupo`;
  - `F003_R010 al empezar a sonar su canción, el cliente recupera el cupo sin recargar, en menos de 1 s`.

### T014 — Prueba de carga del cliente `P`

- **Estado:** `[ ]`
- **Requisitos:** R003, R005
- **Depende de:** T008
- **Archivos:** `src/perf/client.js`, `src/perf/README.md`
- **Hecho cuando:**
  - `k6 run src/perf/client.js` contra el compose, con el catálogo falso, cumple con 50 establecimientos y 5000 usuarios virtuales: p95 de la búsqueda por debajo de 2 s y 0 respuestas 5xx (Q1, Q2).
  - El resultado queda anotado en el propio script.

### T015 — Documentación del catálogo y del cliente

- **Estado:** `[ ]`
- **Requisitos:** R003, R012
- **Depende de:** T007, T013
- **Archivos:** `README.md`, `src/backend/README.md`, `src/web/README.md`
- **Hecho cuando:** los README explican:
  - el catálogo, con su adaptador falso y cómo usar YouTube real en local con `CATALOG_PROVIDER=youtube` y `YOUTUBE_API_KEY`;
  - las variables nuevas;
  - la página del cliente;
  - cómo correr las pruebas nuevas.

### T016 — C1: resolver el establecimiento de un código público

- **Estado:** `[x]`
- **Requisitos:** R001, R011
- **Depende de:** —
- **Archivos:** `src/backend/migrations/versions/0004_public_establishment_id.py`, `src/backend/app/accounts/{domain/ports.py,infrastructure/repositories.py,application/get_public_establishment.py,interface.py}`, `src/backend/tests/integration/test_definer_functions.py`
- **Hecho cuando:**
  - `alembic upgrade head` y `alembic downgrade -1` funcionan contra el PostgreSQL del compose.
  - Pasan:
    - `test_F003_R001_public_establishment_id_devuelve_solo_el_identificador`;
    - `test_F003_R011_public_establishment_id_de_un_codigo_desconocido_o_mal_formado_no_devuelve_nada`.
  - La batería de funciones `SECURITY DEFINER` incluye la nueva: solo `app_api` puede ejecutarla.
  - `public_establishment` sigue devolviendo solo el nombre.

## Cobertura

| Requisito | Tareas |
| --------- | ------ |
| R001 | T008, T012, T013, T016 |
| R002 | T001, T003, T007, T008 |
| R003 | T004, T005, T007, T008, T012, T014, T015 |
| R004 | T004 |
| R005 | T002, T006, T008, T012, T013, T014 |
| R006 | T001, T002, T006, T008, T012, T013 |
| R007 | T002, T006 |
| R008 | T002, T006, T008, T012 |
| R009 | T002, T006, T008, T012 |
| R010 | T006, T008, T009, T011, T012, T013 |
| R011 | T003, T009, T010, T016 |
| R012 | T004, T005, T008, T012, T015 |
| R013 | T005, T008, T012 |
| R014 | T004, T005, T006, T008, T012 |

> Todo requisito MUST debe tener al menos una tarea. Los doce MUST (R001–R003, R005–R012 y R014) y los SHOULD R004 y R013 tienen tareas y pruebas previstas.
