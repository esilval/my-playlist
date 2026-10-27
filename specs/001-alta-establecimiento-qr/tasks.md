# Tasks: Alta del establecimiento y su QR

| Campo  | Valor       |
| ------ | ----------- |
| Spec   | `spec.md`   |
| Plan   | `plan.md`   |
| Fecha  | 2026-10-19  |
| Estado | Approved · 6bf49cff6c13       |

> Cada tarea debe ser verificable por sí sola y caber en una sola sesión de
> trabajo. Si una tarea necesita una decisión que no está en `plan.md`, la tarea
> está mal descompuesta.
>
> Sustituye todo texto en cursiva. Solo el usuario cambia el Estado, con
> `/sdd:approve`. Las pruebas citan el requisito con el prefijo de la
> feature: `test_F001_R001_rechaza_token_expirado`.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecha
- `P` marca tareas paralelizables (sin dependencias entre sí)

## Tareas

### T001 — Esqueleto del backend FastAPI

- **Estado:** `[x]`
- **Requisitos:** R023
- **Depende de:** —
- **Archivos:** `src/backend/pyproject.toml`, `src/backend/uv.lock`, `src/backend/app/main.py`, `src/backend/app/shared/config.py`, `src/backend/app/accounts/{api,application,domain,infrastructure}/__init__.py`, `src/backend/tests/conftest.py`, `src/backend/tests/unit/test_health.py`, `src/backend/.python-version`, `src/backend/app/__init__.py`, `src/backend/app/accounts/__init__.py`, `src/backend/app/shared/__init__.py`, `src/backend/tests/__init__.py`, `src/backend/tests/unit/__init__.py`
- **Hecho cuando:** `uv run pytest` pasa con `test_app_arranca_y_responde_health` (`GET /api/health` → 200); `uv run ruff check` y `uv run mypy app` salen sin errores; una prueba de importación verifica que `app/accounts/domain` no importa `fastapi` ni `sqlalchemy` (S1).

### T002 — Entorno local con docker-compose y CI `P`

- **Estado:** `[x]`
- **Requisitos:** R015, R017
- **Depende de:** —
- **Archivos:** `src/docker-compose.yml`, `.github/workflows/ci.yml`, `src/.env.example`
- **Hecho cuando:** `docker compose up -d` levanta PostgreSQL 16, Redis y Mailpit y sus healthchecks quedan en `healthy`; el workflow de CI tiene trabajos `backend` y `web` filtrados por carpeta y uno de integración que usa el servicio Postgres.

### T003 — Esqueleto de la SPA con rutas `P`

- **Estado:** `[x]`
- **Requisitos:** R012
- **Depende de:** —
- **Archivos:** `src/web/package.json`, `src/web/vite.config.ts`, `src/web/src/main.tsx`, `src/web/src/router.tsx`, `src/web/playwright.config.ts`, `src/web/src/router.test.tsx`, `src/web/index.html`, `src/web/tsconfig.json`, `src/web/eslint.config.js`, `src/web/.nvmrc`, `src/web/package-lock.json`, `src/web/src/test/setup.ts`, `src/web/src/routes/*.tsx` (marcadores)
- **Hecho cuando:** `npm run build`, `npm run lint` y `npm test` pasan; `router.test.tsx` comprueba que existen las rutas `/registro`, `/registro/revisa-tu-correo`, `/entrar`, `/recuperar`, `/restablecer`, `/verificar`, `/politica-de-datos`, `/panel`, `/panel/qr/imprimir` y `/l/:code`, con lazy loading por ruta.

### T004 — Migración inicial: roles, tablas, RLS y trigger de `public_code`

- **Estado:** `[x]`
- **Requisitos:** R009, R015, R024
- **Depende de:** T001, T002
- **Archivos:** `src/backend/alembic.ini`, `src/backend/migrations/env.py`, `src/backend/migrations/versions/0001_accounts.py`, `src/backend/tests/integration/conftest.py`, `src/backend/tests/integration/test_schema.py`, `src/backend/migrations/script.py.mako`, `src/backend/tests/integration/__init__.py`
- **Hecho cuando:** `alembic upgrade head` y `downgrade base` funcionan contra el Postgres local; pasan `test_F001_R015_rls_oculta_filas_de_otro_establecimiento` (con el rol `app_api` y otro `app.establishment_id`, 0 filas), `test_F001_R009_public_code_no_se_puede_actualizar` y `test_F001_R024_email_normalized_es_unico`; existen `data_authorization`, `email_token.superseded_at` y `email_outbox.to_address_normalized` con el índice del límite de R027; ninguna tabla salvo `login_attempt` carece de política RLS (la prueba recorre `pg_tables`).

### T005 — Funciones `SECURITY DEFINER` y sesión de base de datos con contexto RLS

- **Estado:** `[x]`
- **Requisitos:** R012, R013, R015
- **Depende de:** T004
- **Archivos:** `src/backend/migrations/versions/0001_accounts.py` (funciones), `src/backend/app/shared/db.py`, `src/backend/tests/integration/test_definer_functions.py`
- **Hecho cuando:** `app/shared/db.py` ofrece una unidad de trabajo que ejecuta `SET LOCAL app.establishment_id`; pasan `test_F001_R013_public_establishment_desconocido_devuelve_nada`, `test_F001_R012_public_establishment_devuelve_solo_nombre` (sin dirección, teléfono ni ids) y `test_F001_R015_auth_account_by_email_no_expone_otros_campos`.

### T006 — Dominio: registro, correo normalizado y código público `P`

- **Estado:** `[x]`
- **Requisitos:** R003, R004, R009, R024
- **Depende de:** T001
- **Archivos:** `src/backend/app/accounts/domain/registration.py`, `src/backend/app/accounts/domain/public_code.py`, `src/backend/tests/unit/test_registration_rules.py`, `src/backend/tests/unit/test_public_code.py`
- **Hecho cuando:** pasan `test_F001_R003_rechaza_cada_campo_invalido` (nombre vacío, correo sin arroba, contraseña de 7 caracteres, con un error por campo), `test_F001_R004_exige_autorizacion`, `test_F001_R024_normaliza_mayusculas_y_espacios` y `test_F001_R009_public_code_10_caracteres_crockford`.

### T007 — Dominio: caducidad de sesión y bloqueo por intentos `P`

- **Estado:** `[x]`
- **Requisitos:** R007, R020
- **Depende de:** T001
- **Archivos:** `src/backend/app/accounts/domain/session_policy.py`, `src/backend/app/accounts/domain/login_throttle.py`, `src/backend/app/accounts/domain/ports.py` (Clock), `src/backend/tests/unit/test_session_expiry.py`, `src/backend/tests/unit/test_login_throttle.py`
- **Hecho cuando:** con un reloj falso pasan `test_F001_R020_caduca_tras_12h_sin_actividad`, `test_F001_R020_actividad_cada_pocas_horas_mantiene_14h`, `test_F001_R007_bloquea_tras_5_fallos_en_15_min` y `test_F001_R007_desbloquea_pasados_15_min`.

### T008 — Adaptador Argon2id con hash ficticio `P`

- **Estado:** `[x]`
- **Requisitos:** R006
- **Depende de:** T001
- **Archivos:** `src/backend/app/accounts/infrastructure/argon2_hasher.py`, `src/backend/app/accounts/domain/ports.py` (PasswordHasher), `src/backend/tests/unit/test_argon2_hasher.py`
- **Hecho cuando:** pasan `test_F001_R006_verificar_contra_hash_ficticio_devuelve_falso` y una prueba de que el hash guardado empieza por `$argon2id$` y no contiene la contraseña.

### T009 — Bandeja de salida de correo, trabajador y adaptadores

- **Estado:** `[x]`
- **Requisitos:** R016, R017
- **Depende de:** T025
- **Archivos:** `src/backend/app/shared/outbox.py`, `src/backend/app/worker.py`, `src/backend/app/accounts/domain/ports.py` (EmailSender), `src/backend/app/shared/email/{ses.py,smtp_mailpit.py,memory.py}`, `src/backend/app/shared/email/templates/`, `src/backend/tests/integration/test_outbox.py`, `src/backend/app/shared/email/{__init__.py,factory.py,templates.py}`, `src/backend/tests/unit/test_email.py`
- **Hecho cuando:** pasan `test_F001_R017_mensaje_en_outbox_se_envia_a_mailpit` y una prueba de reintento con espera exponencial tras un fallo simulado del adaptador; `python -m app.worker` despacha un mensaje pendiente con el rol `app_worker` (vía `outbox_claim` y `outbox_mark`) y lo marca `sent`; su tarea periódica purga las filas de `login_attempt` de más de 1 día (prueba `test_purga_login_attempt_antiguos`).

### T010 — Caso de uso y endpoint de registro (correo nuevo)

- **Estado:** `[x]`
- **Requisitos:** R003, R004, R009, R017, R022, R023
- **Depende de:** T005, T006, T008, T009, T029
- **Archivos:** `src/backend/app/accounts/application/register.py`, `src/backend/app/accounts/infrastructure/repositories.py`, `src/backend/app/accounts/api/auth.py`, `src/backend/tests/integration/test_register.py`, `src/backend/app/shared/clock.py`
- **Hecho cuando:** pasan:
  - `test_F001_R023_registro_crea_cuenta_y_establecimiento_sin_sesion` (`202 check_email`, sin cookie, un único establecimiento);
  - `test_F001_R023_credenciales_guardadas_permiten_autenticarse` (el camino que usará el inicio de sesión: `auth_account_by_email` y Argon2; la entrada al panel se prueba en T011);
  - `test_F001_R023_direccion_y_telefono_opcionales`;
  - `test_F001_R003_422_con_errores_por_campo_sin_devolver_password`;
  - `test_F001_R004_sin_autorizacion_no_crea_cuenta`;
  - `test_F001_R022_guarda_version_y_fecha_de_la_autorizacion`;
  - `test_F001_R022_version_desfasada_da_422`;
  - `test_F001_R017_registro_encola_correo_de_verificacion`;
  - una prueba de privacidad de que la cuenta solo guarda correo y hash.

### T011 — Inicio y cierre de sesión, resolución de sesión y CSRF

- **Estado:** `[x]`
- **Requisitos:** R005, R006, R007, R008, R020, R023
- **Depende de:** T007, T010
- **Archivos:** `src/backend/app/accounts/application/{login.py,logout.py,resolve_session.py}`, `src/backend/app/accounts/api/{auth.py,deps.py}`, `src/backend/app/shared/csrf.py`, `src/backend/tests/integration/test_login.py`, `src/backend/tests/integration/test_session.py`, `src/backend/app/accounts/interface.py`, `src/backend/tests/integration/api.py`
- **Hecho cuando:** pasan:
  - `test_F001_R005_login_correcto_da_acceso_al_panel`;
  - `test_F001_R023_registro_y_login_posterior_entra_al_panel` (registrarse y después entrar con ese correo y contraseña lleva al panel de su único establecimiento);
  - `test_F001_R006_mismo_401_para_password_erronea_y_correo_inexistente` (mismo código y mismo cuerpo);
  - `test_F001_R007_sexto_intento_da_429_aun_con_password_correcta`;
  - `test_F001_R008_logout_revoca_la_sesion`;
  - `test_F001_R020_sesion_inactiva_12h_da_401`, y `test_F001_R020_cada_peticion_actualiza_last_seen`;
  - una prueba de que un `POST` sin `X-MyPlaylist-Client` o con un `Origin` ajeno da 403;
  - una prueba de que la cookie lleva `Secure` y `HttpOnly` y la respuesta incluye `Strict-Transport-Security`.

### T012 — Verificación de correo con inicio de sesión y reenvío

- **Estado:** `[x]`
- **Requisitos:** R017, R018, R025, R026
- **Depende de:** T011
- **Archivos:** `src/backend/app/accounts/application/{verify_email.py,resend_verification.py}`, `src/backend/app/accounts/api/{auth.py,owner.py}`, `src/backend/tests/integration/test_verify_email.py`, `src/backend/app/accounts/application/verification_link.py`
- **Hecho cuando:** pasan:
  - `test_F001_R025_primer_uso_verifica_y_crea_sesion` (`200 verified` con una cookie que da acceso a `/api/owner/me`);
  - `test_F001_R017_segundo_uso_devuelve_already_verified_sin_cookie`;
  - `test_F001_R026_token_alterado_da_400_sin_verificar_ni_cookie`;
  - `test_F001_R026_token_reemplazado_por_reenvio_da_400`;
  - `test_F001_R018_reenvio_encola_un_nuevo_enlace_y_marca_superseded_el_anterior`.

### T013 — Recuperación de contraseña con revocación de sesiones

- **Estado:** `[x]`
- **Requisitos:** R016, R021
- **Depende de:** T009, T011
- **Archivos:** `src/backend/app/accounts/application/{request_password_reset.py,confirm_password_reset.py}`, `src/backend/app/accounts/api/auth.py`, `src/backend/tests/unit/test_email_token.py`, `src/backend/tests/integration/test_password_reset.py`
- **Hecho cuando:** pasan:
  - `test_F001_R016_mismo_202_exista_o_no_la_cuenta`;
  - `test_F001_R016_enlace_de_un_solo_uso`;
  - `test_F001_R016_enlace_caducado_a_los_60_min` (con reloj falso);
  - `test_F001_R016_contrasena_nueva_corta_da_422` (el enlace sigue sirviendo después);
  - `test_F001_R021_confirmar_revoca_todas_las_sesiones` (dos sesiones previas → 401);
  - `test_F001_R021_password_anterior_da_invalid_credentials`.

### T014 — Panel: datos del propietario y edición del establecimiento

- **Estado:** `[x]`
- **Requisitos:** R014, R015, R019
- **Depende de:** T011, T016
- **Archivos:** `src/backend/app/accounts/application/{get_owner.py,update_establishment.py}`, `src/backend/app/accounts/api/owner.py`, `src/backend/tests/integration/test_establishment.py`, `src/backend/app/accounts/domain/establishment.py`, `src/backend/tests/unit/test_establishment_changes.py`
- **Hecho cuando:** pasan:
  - `test_F001_R014_editar_nombre_mantiene_public_code`;
  - `test_F001_R014_pagina_publica_muestra_el_nombre_nuevo` (`GET /api/public/establishments/{code}`);
  - `test_F001_R014_solo_cambian_los_campos_enviados` (un opcional vacío pasa a `NULL`);
  - `test_F001_R014_sin_campos_no_cambia_nada`;
  - `test_F001_R014_nombre_vacio_se_rechaza`;
  - `test_F001_R014_nombre_vacio_da_422_y_no_cambia`;
  - `test_F001_R019_sin_verificar_puede_editar_telefono`;
  - `test_F001_R015_owner_me_sin_sesion_da_401`;
  - `test_F001_R015_patch_ignora_establishment_id_en_el_cuerpo`.

### T015 — Generación y descarga del QR

- **Estado:** `[x]`
- **Requisitos:** R009, R010, R018
- **Depende de:** T012, T014
- **Archivos:** `src/backend/app/accounts/infrastructure/qr_image.py`, `src/backend/app/accounts/application/get_qr.py`, `src/backend/app/accounts/api/owner.py`, `src/backend/app/assets/fonts/Inter-*.ttf`, `src/backend/tests/integration/test_qr.py`, `src/backend/app/assets/fonts/OFL.txt`, `src/backend/tests/unit/test_qr_layout.py`, `src/backend/tests/fixtures/qr_cafe_nandu.png`
- **Hecho cuando:** pasan:
  - `test_F001_R010_png_decodifica_a_la_url_publica` (decodificado con `zxing-cpp`);
  - `test_F001_R010_composicion_incluye_nombre_con_tildes` (la función de composición, con «Café Ñandú», coincide con `tests/fixtures/qr_cafe_nandu.png`: contando como distintos los píxeles que difieren en más de 32 niveles de gris, como mucho 20 en la franja del nombre —quitar una sola tilde cambia unos 75— y como mucho el 0,1 % en el resto; y las variantes sin tilde o sin eñe no coinciden);
  - `test_F001_R010_download_envia_content_disposition`;
  - `test_F001_R018_correo_sin_verificar_da_403_email_not_verified`;
  - `test_F001_R009_qr_igual_tras_cambiar_nombre` (misma URL decodificada).

### T016 — Endpoint público del establecimiento `P`

- **Estado:** `[x]`
- **Requisitos:** R012, R013
- **Depende de:** T005
- **Archivos:** `src/backend/app/accounts/api/public.py`, `src/backend/app/accounts/application/get_public_establishment.py`, `src/backend/tests/integration/test_public_page.py`
- **Hecho cuando:** pasan `test_F001_R012_codigo_existente_devuelve_nombre_sin_sesion`, `test_F001_R013_codigo_inexistente_da_404` y `test_F001_R013_codigo_mal_formado_da_el_mismo_404`.

### T017 — Batería de aislamiento entre establecimientos

- **Estado:** `[x]`
- **Requisitos:** R015
- **Depende de:** T013, T014, T015, T016, T026
- **Archivos:** `src/backend/tests/integration/test_isolation.py`
- **Hecho cuando:** con dos establecimientos A y B pasan:
  - `test_F001_R015_sesion_de_a_no_lee_ni_modifica_b` en `/api/owner/*`: los datos de B no cambian;
  - `test_F001_R015_qr_de_a_nunca_codifica_b`;
  - `test_F001_R015_consulta_directa_con_rol_app_api_no_ve_b`;
  - `test_F001_R015_aviso_de_registro_duplicado_solo_se_encola_en_el_establecimiento_del_titular`.

### T018 — Cliente de API TypeScript generado

- **Estado:** `[x]`
- **Requisitos:** R015
- **Depende de:** T003, T013, T014, T015, T016, T026, T027, T028, T029
- **Archivos:** `src/web/scripts/gen-api.sh`, `src/web/src/api/schema.d.ts` (generado), `src/web/src/api/client.ts`, `src/web/src/api/client.test.ts`
- **Hecho cuando:** `npm run gen:api` regenera los tipos desde el OpenAPI del backend sin diferencias en CI; pasa `F001_R015 cliente envía X-MyPlaylist-Client y credenciales same-origin, y redirige a /entrar ante 401`.

### T019 — Pantallas de autenticación `P`

- **Estado:** `[x]`
- **Requisitos:** R003, R004, R005, R006, R007, R016, R017, R022, R023, R025, R026, R028
- **Depende de:** T018
- **Archivos:** `src/web/src/features/auth/{Register,CheckEmail,Login,ForgotPassword,ResetPassword,VerifyEmail}.tsx`, `src/web/src/features/auth/*.test.tsx`, `src/web/src/api/{context.tsx,errors.ts}`, `src/web/src/ui/Field.tsx`, `src/web/src/styles.css`, `src/web/src/test/{fake-api.ts,render-route.tsx}`, `src/web/src/routes/{register,check-email,login,forgot-password,reset-password,verify-email}.tsx`
- **Hecho cuando:** pasan las pruebas de componente:
  - `F001_R003 conserva lo escrito salvo la contraseña y señala cada campo`;
  - `F001_R004 casilla de autorización obligatoria`;
  - `F001_R022 enlace a la política junto a la casilla y envío de policy_version`;
  - `F001_R023 tras registrar lleva a revisa-tu-correo sin sesión`;
  - `F001_R006 muestra el mensaje genérico`;
  - `F001_R007 muestra el aviso de espera ante 429`;
  - `F001_R016 mismo mensaje tras pedir recuperación`;
  - `F001_R025 verificado lleva al panel`;
  - `F001_R017 ya verificado lo indica`;
  - `F001_R026 enlace inválido ofrece pedir uno nuevo`;
  - `F001_R028 enlace caducado lo indica y ofrece uno nuevo`.

### T020 — Panel del propietario y QR imprimible `P`

- **Estado:** `[x]`
- **Requisitos:** R008, R010, R011, R014, R018, R019, R020, R027
- **Depende de:** T018
- **Archivos:** `src/web/src/features/owner-panel/{Panel,EstablishmentForm,QrCard,PrintQr,LogoutButton}.tsx`, `src/web/src/features/owner-panel/print.css`, `src/web/src/features/owner-panel/*.test.tsx`, `src/web/src/features/owner-panel/{types.ts,useOwnerMe.ts,fixtures.ts}`, `src/web/src/features/shared/ResendVerification.tsx`, `src/web/src/routes/{panel,print-qr}.tsx`
- **Hecho cuando:** pasan:
  - `F001_R018 QrCard sin verificar muestra aviso y botón de reenvío`;
  - `F001_R018 PrintQr ante 403 muestra el aviso y no llama a window.print`;
  - `F001_R027 reenvío limitado muestra que hay que esperar`;
  - `F001_R010 QrCard descarga con download=1`;
  - `F001_R011 PrintQr renderiza solo imagen y nombre y llama a window.print`;
  - `F001_R014 guardar datos muestra el nombre nuevo`;
  - `F001_R014 nombre vacío se señala en el campo`;
  - `F001_R008 cerrar sesión lleva a /entrar`;
  - `F001_R020 sin sesión o con la sesión caducada el cliente lleva a entrar`.

### T021 — Página pública del establecimiento `P`

- **Estado:** `[x]`
- **Requisitos:** R012, R013
- **Depende de:** T018
- **Archivos:** `src/web/src/features/public-establishment/PublicEstablishment.tsx`, `src/web/src/features/public-establishment/PublicEstablishment.test.tsx`, `src/web/src/routes/public-establishment.tsx`
- **Hecho cuando:** pasan `F001_R012 muestra el nombre sin pedir registro` y `F001_R013 muestra establecimiento no encontrado ante 404 sin otros datos`.

### T022 — Pruebas e2e con Playwright y Mailpit

- **Estado:** `[x]`
- **Requisitos:** R005, R006, R008, R011, R012, R013, R016, R017, R018, R021, R022, R023, R025
- **Depende de:** T017, T019, T020, T021, T024, T030
- **Archivos:** `src/web/e2e/{register,login,password-reset,qr,public-page}.spec.ts`, `src/web/e2e/helpers/mailpit.ts`, `src/web/e2e/helpers/owners.ts`, `src/web/playwright.config.ts`
- **Hecho cuando:** `npx playwright test` pasa contra `http://localhost:5173` del entorno de docker-compose (T024) con estos tests:
  - `F001_R023 registro muestra revisa tu correo sin sesión`;
  - `F001_R025 enlace del correo verifica y deja en el panel`;
  - `F001_R022 la política se abre desde el registro`;
  - `F001_R005 entrar con contraseña`;
  - `F001_R006 credenciales erróneas dan el mensaje genérico`;
  - `F001_R008 cerrar sesión pide entrar`;
  - `F001_R011 vista de impresión`;
  - `F001_R018 sin verificar no se puede imprimir el QR`;
  - `F001_R012 abrir /l/:code muestra el nombre`;
  - `F001_R013 código inexistente`;
  - `F001_R016 recuperar y entrar con la nueva`;
  - `F001_R021 dos contextos, ambos expulsados tras restablecer`.

### T023 — Prueba de carga y guía de escaneo del QR

- **Estado:** `[x]`
- **Requisitos:** R005, R010, R023
- **Depende de:** T022
- **Archivos:** `src/perf/accounts.js`, `docs/qa/qr-escaneo.md`, `src/backend/app/shared/cpu.py`, `src/backend/app/shared/config.py`, `src/backend/app/accounts/application/{register.py,login.py,confirm_password_reset.py}`
- **Hecho cuando:** `k6 run src/perf/accounts.js` con 50 establecimientos concurrentes (registro, inicio de sesión y descarga del QR) informa p95 < 2 s en local; los parámetros de Argon2 (D3) quedan fijados en configuración según esa medida, y el resultado queda anotado en el archivo; `docs/qa/qr-escaneo.md` recoge la prueba manual de impresión en carta y escaneo con la cámara nativa de iOS y Android, con dispositivos y resultado.

### T024 — API, trabajador y web en docker-compose bajo el mismo origen

- **Estado:** `[x]`
- **Requisitos:** R017, R023
- **Depende de:** T001, T002, T003, T009
- **Archivos:** `src/backend/Dockerfile`, `src/web/Dockerfile.dev`, `src/docker-compose.yml` (servicios `api`, `worker`, `web`), `src/web/vite.config.ts` (proxy `/api`), `src/backend/.dockerignore`, `src/web/.dockerignore`
- **Hecho cuando:** `docker compose up -d` deja los servicios `api`, `worker` y `web` en `healthy`; `curl http://localhost:5173/api/health` responde 200 a través del proxy de Vite; un mensaje encolado a mano aparece en la API de Mailpit en menos de 10 s.

### T025 — Rol `app_worker` y funciones de la bandeja de salida

- **Estado:** `[x]`
- **Requisitos:** R015, R017
- **Depende de:** T004
- **Archivos:** `src/backend/migrations/versions/0001_accounts.py` (rol y funciones), `src/backend/tests/integration/test_worker_role.py`
- **Hecho cuando:** pasan `test_F001_R015_app_worker_no_lee_tablas_directamente`, `test_F001_R017_outbox_claim_reparte_sin_duplicar` (mensajes de dos establecimientos; dos llamadas concurrentes no reclaman el mismo mensaje) y `test_outbox_mark_actualiza_estado`.

### T026 — Registro con correo existente: respuesta idéntica y aviso al titular

- **Estado:** `[x]`
- **Requisitos:** R024
- **Depende de:** T010
- **Archivos:** `src/backend/app/accounts/application/register.py`, `src/backend/app/shared/email/templates/registration_attempt.*`, `src/backend/tests/integration/test_register.py`
- **Hecho cuando:** pasan:
  - `test_F001_R024_correo_existente_con_mayusculas_no_crea_nada`;
  - `test_F001_R024_respuesta_identica_a_registro_nuevo` (mismo código, cabeceras sin cookie y cuerpo byte a byte);
  - `test_F001_R024_encola_aviso_con_enlaces_a_entrar_y_recuperar` en el establecimiento del titular;
  - `test_F001_R024_carrera_por_indice_unico_se_trata_como_existente`.

### T027 — Caducidad del enlace de verificación

- **Estado:** `[x]`
- **Requisitos:** R028
- **Depende de:** T012
- **Archivos:** `src/backend/app/accounts/domain/email_token.py`, `src/backend/app/accounts/application/verify_email.py`, `src/backend/tests/unit/test_email_token.py`, `src/backend/tests/integration/test_verify_email.py`
- **Hecho cuando:** pasan, con reloj falso, `test_F001_R028_token_de_8_dias_caducado`, `test_F001_R028_token_de_6_dias_vigente`, `test_F001_R028_usado_y_caducado_sigue_already_verified`, y en integración `test_F001_R028_verify_caducado_da_400_expired_token_sin_cookie`.

### T028 — Límite de 3 correos por tipo y hora

- **Estado:** `[x]`
- **Requisitos:** R027
- **Depende de:** T012, T013, T026
- **Archivos:** `src/backend/app/accounts/domain/email_quota.py`, `src/backend/app/accounts/application/{request_password_reset.py,resend_verification.py,register.py}`, `src/backend/tests/unit/test_email_quota.py`, `src/backend/tests/integration/test_email_quota.py`
- **Hecho cuando:** pasan:
  - `test_F001_R027_cuarto_en_60_min_no_se_permite` y `test_F001_R027_pasada_la_hora_se_permite` (unitarias con reloj falso);
  - `test_F001_R027_cuarta_recuperacion_misma_respuesta_sin_encolar`;
  - `test_F001_R027_cuarto_reenvio_da_429`;
  - `test_F001_R027_cuarto_aviso_de_registro_no_se_encola`.

### T029 — Política de tratamiento versionada en el backend `P`

- **Estado:** `[x]`
- **Requisitos:** R022
- **Depende de:** T001
- **Archivos:** `src/backend/app/accounts/policy/0000-borrador.md`, `src/backend/app/accounts/api/public.py`, `src/backend/app/shared/config.py` (`DATA_POLICY_VERSION` y comprobación de arranque), `src/backend/tests/integration/test_data_policy.py`, `src/backend/app/accounts/domain/data_policy.py`, `src/backend/app/accounts/application/get_data_policy.py`, `src/backend/app/accounts/infrastructure/policy_files.py`
- **Hecho cuando:** pasan `test_F001_R022_politica_se_sirve_sin_sesion` (`{version, content}`) y `test_F001_R022_produccion_no_arranca_con_borrador` (con `ENV=production` y la versión `0000-borrador`, la aplicación falla al arrancar).

### T030 — Página de la política de tratamiento `P`

- **Estado:** `[x]`
- **Requisitos:** R022
- **Depende de:** T018
- **Archivos:** `src/web/src/features/legal/DataPolicy.tsx`, `src/web/src/features/legal/DataPolicy.test.tsx`, `src/web/src/features/legal/{markdown.tsx,markdown.test.tsx}`, `src/web/src/routes/data-policy.tsx`
- **Hecho cuando:** pasa `F001_R022 muestra la política y su versión sin sesión`.

## Cobertura

| Requisito | Tareas |
| --------- | ------ |
| R001 | Obsoleto (reemplazado por R023 y R025): ninguna tarea lo implementa |
| R002 | Obsoleto (reemplazado por R024): ninguna tarea lo implementa |
| R003 | T006, T010, T019 |
| R004 | T006, T010, T019 |
| R005 | T011, T019, T022, T023 |
| R006 | T008, T011, T019, T022 |
| R007 | T007, T011, T019 |
| R008 | T011, T020, T022 |
| R009 | T004, T006, T010, T015 |
| R010 | T015, T020, T023 |
| R011 | T020, T022 |
| R012 | T005, T016, T021, T022 |
| R013 | T005, T016, T021, T022 |
| R014 | T014, T020 |
| R015 | T004, T005, T014, T017, T018, T025 |
| R016 | T009, T013, T019, T022 |
| R017 | T009, T010, T012, T019, T022, T025 |
| R018 | T012, T015, T020, T022 |
| R019 | T014, T020 |
| R020 | T007, T011, T020 |
| R021 | T013, T022 |
| R022 | T010, T019, T022, T029, T030 |
| R023 | T010, T011, T019, T022, T023 |
| R024 | T004, T006, T026 |
| R025 | T012, T019, T022 |
| R026 | T012, T019 |
| R027 | T020, T028 |
| R028 | T019, T027 |

> Todo requisito MUST debe tener al menos una tarea. T001, T002, T003 y T024 son de infraestructura: citan R023, R015, R017 y R012 porque los habilitan, pero no los implementan, y por eso no figuran en esta tabla.
