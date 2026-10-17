# Plan: Alta del establecimiento y su QR

| Campo  | Valor              |
| ------ | ------------------ |
| Spec   | `spec.md`          |
| Fecha  | 2026-10-17         |
| Estado | Approved · c7b0d18eb849              |

> Este documento describe **cómo**. Si aquí aparece un requisito nuevo que no
> está en `spec.md`, el sitio correcto es `spec.md`, no aquí.
>
> Sustituye todo texto en cursiva; si una sección no aplica, escribe
> «No aplica.». Solo el usuario cambia el Estado, con `/sdd:approve`.

## Resumen

Primera feature con código: monta el monorepo (ADR-0012) y construye en el monolito FastAPI el módulo de cuentas y establecimientos (C1), junto con las pantallas de registro, acceso, panel y QR de la SPA (C7) y la página pública mínima que abre el QR. Hay tres decisiones clave:

- **Sesión opaca en servidor:** el propietario se identifica con una sesión opaca guardada en PostgreSQL, sin JWT. Así se pueden cerrar sesiones de verdad (R008, R020).
- **Aislamiento desde el primer día:** cada tabla aplica Row-Level Security (ADR-0009). Las pocas búsquedas que ocurren antes de saber el establecimiento (inicio de sesión, tokens, página pública) van por funciones `SECURITY DEFINER` muy acotadas.
- **QR fijo y opaco:** el QR codifica un código público aleatorio e inmutable, nunca el nombre del local. Así sobrevive a los cambios de datos (R009, R014).
- **Registro que no revela cuentas:** el registro responde igual exista o no el correo, y la sesión se abre al verificar el correo (R023–R025). Cuando el correo ya existe, se avisa a su titular en lugar de crear nada (D11).

## Comprobación de constitución

No aplica: el proyecto no tiene `specs/constitution.md`. Los invariantes propuestos en el brief (aislamiento, datos mínimos, sin instalación) se cubren en la comprobación de arquitectura (ADR-0009, S8, S9, ADR-0003).

## Comprobación de arquitectura

| Decisión o estándar | Cómo lo cumple este plan |
| ------------------- | ------------------------ |
| ADR-0001 — Monolito modular | C1 es un módulo del monolito (`backend/app/accounts/`) con su interfaz pública; no se crea ningún servicio nuevo. |
| ADR-0002 — Python/FastAPI, TypeScript | Backend en FastAPI con Pydantic; la SPA consume un cliente TypeScript generado desde el OpenAPI (D9). |
| ADR-0003 — Una SPA React + Vite | Registro, acceso, panel, QR imprimible y página pública son rutas de la misma SPA (D9). |
| ADR-0004 — PostgreSQL + Redis | Todo el estado de la feature (cuentas, sesiones, intentos, tokens, correos pendientes) vive en PostgreSQL; esta feature no usa Redis. |
| ADR-0006 — AWS us-east-1 | El tráfico entra por CloudFront (SPA) y ALB (`/api`) con TLS. Esta feature no despliega: deja la aplicación lista (cookie `Secure`, cabecera HSTS) y el despliegue lo cierra una feature de infraestructura (D10, Riesgos). |
| ADR-0007 — Autenticación propia | Correo y contraseña con Argon2id y sesión en cookie HttpOnly + Secure (D2, D3); sin proveedores externos. El token anónimo del cliente no aplica todavía: llega con B03. |
| ADR-0009 — Columna + RLS | Toda tabla lleva `establishment_id` y una política RLS; el rol de la API no tiene BYPASSRLS; las búsquedas previas al establecimiento van por funciones `SECURITY DEFINER` (D4). |
| ADR-0011 — Correo con Amazon SES | Los correos de verificación, recuperación y aviso de intento de registro salen por un puerto de correo, con un adaptador SES y otro local (D7). La gestión de rebotes y quejas por SNS que pide el ADR queda para cuando se despliegue (ver Riesgos). |
| ADR-0012 — Monorepo y herramientas base | El plan crea `backend/`, `web/` e `infra/` (vacía) con las herramientas de ese ADR. |
| S1 — Capas del monolito | `accounts/` se divide en `api/`, `application/`, `domain/` e `infrastructure/`; el dominio no importa FastAPI ni SQLAlchemy. Hashing, correo y reloj son puertos. |
| S6 — Los frontales no acceden a los almacenes | La SPA solo llama a `/api/*`; el PNG del QR lo genera el backend (D6). |
| S8 — `establishment_id` y RLS | Lo cumplen todas las tablas salvo `login_attempt`, que se indexa por correo antes de existir sesión. Es una tabla de seguridad, no de negocio, sin acceso desde la API pública (D5). |
| S9 — Sin datos personales de clientes | La página pública y la página de la política no guardan ni piden nada al visitante. Del propietario solo se guardan correo, contraseña (hash) y la autorización con su versión y fecha (R022). |
| S10 — Redis nunca es la única copia | No aplica en la práctica: la feature no escribe en Redis. Los intentos de inicio de sesión (R007) van a PostgreSQL. |

## Decisiones

### D1 — Código público del QR aleatorio e inmutable

- **Contexto:** el QR no puede cambiar en la vida del establecimiento (R009) ni al editar sus datos (R014), y un enlace alterado no debe revelar otro local (R013).
- **Decisión:** cada establecimiento recibe al crearse un `public_code` de 10 caracteres en Crockford base32 (unos 50 bits aleatorios), único. El QR codifica `{PUBLIC_BASE_URL}/l/{public_code}`. Un trigger impide hacer `UPDATE` de `public_code`.
- **Alternativas descartadas:** un slug derivado del nombre, que cambiaría con R014 o habría que congelarlo con el nombre viejo; y el UUID interno en la URL, que expone el identificador de base de datos y resulta más largo, con un QR más denso y peor de escanear.
- **Consecuencias:** cambiar el dominio público (`PUBLIC_BASE_URL`) invalidaría los QR impresos, así que el dominio es parte del contrato. El código no se puede adivinar, pero tampoco es secreto: la página pública solo muestra el nombre.

### D2 — Sesión opaca en PostgreSQL con caducidad por inactividad

- **Contexto:** cerrar sesión debe invalidarla de verdad (R008), y caduca tras 12 horas sin actividad pero no por uso continuado (R020).
- **Decisión:** se genera un token aleatorio de 32 bytes que viaja en la cookie `mp_session` (HttpOnly, Secure, SameSite=Lax, `Path=/api`). En `owner_session` se guarda su hash SHA-256 con `last_seen_at`. Cada petición autenticada rechaza la sesión si `now - last_seen_at > 12 h` y, si no, actualiza `last_seen_at` a `now` **en cada petición**, para que la caducidad mida exactamente 12 h desde la última actividad (R020). Al cerrar sesión se marca `revoked_at` y se borra la cookie.
- **Alternativas descartadas:** un JWT sin estado, que no se puede revocar en R008 sin añadir una lista negra (es decir, estado igualmente); sesiones en Redis, que S10 no permite como única copia y que no hacen falta con este volumen; y actualizar `last_seen_at` como mucho cada 5 minutos, que ahorra escrituras pero cerraría la sesión hasta 5 minutos antes de las 12 h que exige R020.
- **Consecuencias:** cada petición autenticada hace una lectura y una escritura indexadas más; con 50 propietarios es despreciable, y si creciera se puede cambiar la regla con una enmienda de la spec que admita tolerancia. Las sesiones también se crean al verificar el correo (R025, D11). No hay caducidad absoluta: la spec solo pide inactividad. Al confirmar un restablecimiento de contraseña, la misma transacción que guarda el nuevo hash marca `revoked_at` en todas las filas de `owner_session` de la cuenta (R021). Como el estado está en servidor, la revocación es inmediata; con JWT no lo sería.

### D3 — Argon2id y respuesta uniforme en el inicio de sesión

- **Contexto:** las contraseñas no pueden leerse en claro (RNF Seguridad), y un correo inexistente no debe distinguirse de una contraseña errónea (R006).
- **Decisión:**
  - Se usa Argon2id con `argon2-cffi` y la configuración mínima que recomienda OWASP: 19 MiB de memoria, 2 pasadas y 1 hilo, unos 20 ms por hash. Los parámetros salen de configuración y se fijaron con la prueba de carga `perf/accounts.js` (T023). Con 50 establecimientos a la vez, en local, el p95 queda en 0,89 s para el registro, 0,24 s para el inicio de sesión y 0,35 s para el QR.
  - El hash corre fuera del bucle de eventos, en hilos, con un tope de uno por núcleo (`app/shared/cpu.py`).
  - Si el correo no existe, se verifica contra un hash ficticio para igualar el tiempo. Los dos fallos devuelven el mismo `401` con el mismo cuerpo.
- **Alternativas descartadas:**
  - bcrypt, más débil frente a GPU y limitado a 72 bytes.
  - Responder antes cuando el correo no existe, porque el tiempo revelaría que el correo no está registrado.
  - Ajustar el hash a unos 150 ms (64 MiB y 3 pasadas): con 50 registros a la vez, el p95 del registro llega a 4,9 s.
  - Calcular el hash en el bucle de eventos: los hashes simultáneos van en fila (p95 de 4 s).
  - Hilos sin tope: los hashes compiten por la memoria y las peticiones llegan a 60 s.
- **Consecuencias:**
  - El coste del hash limita cuántos inicios de sesión por segundo admite cada tarea. Subirlo exige más vCPU o más tareas, y se vuelve a medir con `perf/accounts.js`.
  - El inicio de sesión espera su turno de CPU dentro de la transacción que bloquea el correo (D5), así que retiene una conexión del pool mientras tanto. Con 50 locales no se nota.
  - El tope se calcula con `os.cpu_count()`, que ve los núcleos de la máquina y no la cuota de CPU del contenedor. Se revisa en la feature de infraestructura, con la vCPU de las tareas Fargate.

### D4 — Funciones `SECURITY DEFINER` para lo que ocurre antes de conocer el establecimiento

- **Contexto:** RLS exige fijar el establecimiento en cada transacción (ADR-0009). Pero el inicio de sesión, la resolución de sesiones y de tokens de correo, y la página pública ocurren antes de saber a qué establecimiento pertenece la petición.
- **Decisión:** el rol de la API, `app_api`, no tiene BYPASSRLS y en cada transacción autenticada ejecuta `SET LOCAL app.establishment_id`. Para los casos previos hay cuatro funciones `SECURITY DEFINER` con `search_path` fijo, propiedad del rol de migraciones, que devuelven solo lo imprescindible:
  - `auth_account_by_email(email)` devuelve el id, el establecimiento, el hash y si el correo está verificado;
  - `auth_session(token_hash)` resuelve una sesión;
  - `auth_email_token(token_hash, purpose)` resuelve un token de correo y su estado (vigente, usado o reemplazado);
  - `public_establishment(code)` devuelve solo el nombre.

  Una vez resuelto el establecimiento en el servidor (nunca desde la entrada del cliente), la transacción ejecuta `SET LOCAL app.establishment_id` y sigue con RLS normal. Así el aviso de R024 o el enlace de recuperación de R016 se encolan sin más funciones especiales. El registro de una cuenta nueva genera el UUID del establecimiento en la aplicación y fija `app.establishment_id` antes de insertar.

  El trabajador de correo usa su propio rol, `app_worker`, y tres funciones `SECURITY DEFINER`:
  - `outbox_claim(batch, lease = 5 min)` reclama mensajes vencidos de todos los establecimientos con `FOR UPDATE SKIP LOCKED` y, en la misma sentencia, suma un intento y mueve `next_attempt_at` a `now() + lease`. Ese movimiento funciona como arrendamiento: sin él, en cuanto se confirma la reclamación otro trabajador podría tomar el mismo mensaje; con él, un mensaje de un trabajador que muere vuelve a salir al vencer el plazo. Devuelve `id`, destinatario, plantilla, datos y número de intentos (para la espera exponencial de D7). Un lote no positivo no reclama nada.
  - `outbox_mark(id, status, retry_at)` marca el resultado: `sent`, `failed` (definitivo) o `pending` con la hora del siguiente intento, que es obligatoria. Solo cambia mensajes aún pendientes: uno enviado o fallado no se reabre. La entrega es «al menos una vez»: si un arrendamiento vence durante un envío lento, otro trabajador puede repetirlo.
  - `login_attempt_purge(older_than = 1 día)` purga los intentos de inicio de sesión antiguos (D5).
- **Alternativas descartadas:** un segundo pool de conexiones con un rol con BYPASSRLS, que amplía demasiado lo que puede hacer ese código; y no aplicar RLS a las tablas de cuenta, que contradice S8.
- **Consecuencias:** cada función nueva de este tipo es una puerta en el aislamiento: se revisa en código y tiene su prueba en `tests/integration/test_definer_functions.py`. Las features siguientes reutilizan el mismo mecanismo.

### D5 — Bloqueo por intentos fallidos con una tabla en PostgreSQL

- **Contexto:** R007 pide rechazar los intentos de inicio de sesión tras 5 fallos sobre un correo en 15 minutos.
- **Decisión:** se usa la tabla `login_attempt(email_normalized, attempted_at, succeeded)`. Antes de verificar la contraseña se leen los fallos de ese correo de los últimos 30 minutos: si en algún tramo hay 5 fallos dentro de 15 minutos, el correo queda bloqueado **15 minutos completos desde el quinto fallo**, como pide R007 («rechazar nuevos intentos durante 15 minutos»). Mientras dure, se responde `429` con un mensaje de espera, sin verificar la contraseña. Solo cuentan como fallos las contraseñas incorrectas: un intento rechazado por el bloqueo no se registra como fallo, porque si contara alargaría el bloqueo sin fin. El trabajador purga cada hora las filas de más de 1 día.
- **Alternativas descartadas:** un contador en Redis, que es más rápido pero S10 lo desaconseja y aquí no hace falta; un bloqueo por IP, que no es lo que pide la spec y castiga a varios locales detrás de la misma NAT; y una ventana deslizante de 15 minutos («5 fallos en los últimos 15 minutos»), que levanta el bloqueo antes de 15 minutos si los fallos llegaron seguidos (11 minutos con fallos en los minutos 0–4).
- **Consecuencias:** `login_attempt` no lleva `establishment_id` porque se consulta por correo, antes de que exista una sesión. Es la excepción documentada a S8, y la API pública no tiene ningún endpoint que la lea.

### D6 — El backend genera el PNG del QR con el nombre

- **Contexto:** el QR debe descargarse como imagen con el nombre visible (R010), imprimirse (R011), escanearse en carta con la cámara nativa (RNF Compatibilidad) y bloquearse si el correo no está verificado (R018).
- **Decisión:** el endpoint `GET /api/owner/establishment/qr.png` genera la imagen con `segno` (corrección de errores M) y Pillow: unos 1200 × 1450 px, con el QR, un margen blanco de 4 módulos y el nombre debajo. Si el correo no está verificado responde `403 email_not_verified`. La vista de impresión es una ruta de la SPA que muestra esa misma imagen con CSS de impresión y llama a `window.print()`.
- **Alternativas descartadas:** generar el QR en el navegador, porque la comprobación del correo verificado quedaría solo en el cliente y la descarga sería distinta en cada navegador; y un PDF, más pesado y no pedido.
- **Consecuencias:** Pillow necesita fuentes en la imagen de contenedor, así que se empaqueta una fuente libre (p. ej. Inter) con soporte de tildes y ñ. Los nombres largos se reparten en dos líneas.

### D7 — Correos con una bandeja de salida en PostgreSQL

- **Contexto:** el registro envía el correo de verificación (R017) o el aviso de intento (R024), y la recuperación envía su enlace (R016). Un fallo de SES no debe romper el registro (ADR-0011), y no se pueden enviar más de 3 correos de un tipo por correo y hora (R027).
- **Decisión:** la transacción del caso de uso inserta el mensaje en `email_outbox`. Un proceso trabajador (el mismo código del monolito, lanzado como `python -m app.worker` en su propia tarea) lo envía por el puerto `EmailSender`, con reintentos y espera exponencial. Los tokens se guardan solo como hash SHA-256: los de verificación caducan a los 7 días (`expires_at = created_at + 7 días`, R028) y antes dejan de valer si se usan o si un reenvío los marca como reemplazados (`superseded_at`, R026); los de recuperación valen 60 minutos y un solo uso.

  **Límite de R027:** antes de encolar un correo de recuperación, de reenvío o de aviso, el caso de uso cuenta en `email_outbox` los mensajes de esa plantilla al mismo `to_address_normalized` en los últimos 60 minutos (en el contexto RLS del establecimiento ya resuelto). Con 3 o más no encola: la recuperación y el aviso devuelven la misma respuesta de siempre, y el reenvío responde `429 resend_rate_limited`. La verificación inicial del registro no cuenta para el límite, porque solo ocurre una vez por cuenta.
- **Alternativas descartadas:** `BackgroundTasks` de FastAPI, que pierde el correo si la tarea se reinicia; enviar dentro de la petición, que sube la latencia (RNF Rendimiento) y acopla el registro a SES; y una tabla aparte de cuotas para R027, que duplica lo que ya registra la bandeja de salida.
- **Consecuencias:** hay un segundo proceso que desplegar y vigilar. En local, `EmailSender` apunta a Mailpit (docker-compose) y las pruebas e2e leen los enlaces de su API.

### D8 — Correo normalizado en minúsculas como clave de cuenta

- **Contexto:** un correo repetido con otras mayúsculas también cuenta como existente (R024).
- **Decisión:** se guarda `email` sin los espacios de los extremos y `email_normalized = lower(trim(email))` con índice único. La validación de formato usa `email-validator`, vía `EmailStr` de Pydantic. Si el `INSERT` choca con ese índice por una carrera entre dos registros simultáneos, se trata como correo existente (D11).
- **Alternativas descartadas:** la extensión `citext`, que funciona pero oculta la normalización y complica las funciones `SECURITY DEFINER`.
- **Consecuencias:** toda búsqueda por correo pasa por la misma función de normalización del dominio.

### D9 — Rutas de la SPA y protección contra CSRF

- **Contexto:** el panel vive en la SPA (ADR-0003), la cookie es de primera parte, y R015 exige que nadie vea un panel ajeno.
- **Decisión:**
  - **Rutas de la SPA:** `/registro`, `/registro/revisa-tu-correo`, `/entrar`, `/recuperar`, `/restablecer`, `/verificar`, `/politica-de-datos`, `/panel`, `/panel/qr/imprimir` y `/l/:code`.
  - **Contexto de la API:** ningún endpoint del propietario recibe el identificador del establecimiento: lo toma de la sesión.
  - **CSRF:** cookie SameSite=Lax, y en cada petición que modifica algo se exige la cabecera `X-MyPlaylist-Client`. Si llega `Origin`, tiene que ser el de la SPA. Sin `Origin`, el caso de los clientes que no son navegador, basta la cabecera: un navegador no puede mandarla a otro origen sin una petición previa de CORS, y la API no responde a esas peticiones.
  - **Formularios:** se conservan los datos escritos tras un error, salvo la contraseña (R003). El backend devuelve los errores por campo y no reenvía la contraseña.
  - **Impresión sin verificar:** `/panel/qr/imprimir` pide el PNG y, ante `403 email_not_verified`, muestra el mismo aviso y botón de reenvío que el panel, sin abrir el diálogo de impresión (R018).
  - **Transporte:** la cookie lleva `Secure` y la API envía `Strict-Transport-Security` en todas las respuestas; el TLS lo terminan CloudFront y ALB cuando se despliegue (ADR-0006).
- **Alternativas descartadas:** el identificador del establecimiento en la URL del panel, que invita a ataques de tipo IDOR y obliga a comprobarlo en cada endpoint; y tokens CSRF con doble cookie, innecesarios con SameSite y una cabecera propia sobre el mismo origen.
- **Consecuencias:** la SPA y la API deben compartir dominio, con CloudFront enrutando `/api/*` al ALB. La página `/l/:code` es la entrada de C5, que B03 ampliará con el buscador.

### D10 — Entorno local completo bajo el mismo origen

- **Contexto:** la cookie de sesión y la protección CSRF (D9) exigen que la SPA y la API compartan origen, y las pruebas e2e necesitan API, trabajador, web y buzón de correo funcionando a la vez.
- **Decisión:** `docker-compose.yml` levanta PostgreSQL, Redis, Mailpit, `api` (uvicorn), `worker` (`python -m app.worker`) y `web` (Vite). El servidor de Vite hace de proxy de `/api/*` hacia `api`, así que el navegador solo ve `http://localhost:5173`. Playwright apunta a ese origen y lee los correos de la API de Mailpit.
- **Alternativas descartadas:** CORS con credenciales entre `localhost:5173` y `localhost:8000`, que no reproduce el despliegue real (mismo dominio tras CloudFront) y obliga a relajar `SameSite`; y un nginx local como proxy, que añade otra pieza sin ventaja frente al proxy de Vite.
- **Consecuencias:** el proxy de Vite solo se usa en local; en AWS el enrutado lo hace CloudFront (`/api/*` al ALB y el resto a S3 con vuelta a `index.html` para las rutas de la SPA, incluida `/l/:code`). Esa configuración entra con la feature de infraestructura.

### D11 — Registro con respuesta uniforme y sesión al verificar

- **Contexto:** el registro no puede revelar si un correo tiene cuenta (R024): crea la cuenta sin iniciar sesión (R023), y la sesión se abre al usar el enlace de verificación por primera vez (R025). Un enlace inválido o reemplazado no hace nada (R026).
- **Decisión:**
  - **Registro:** `POST /api/auth/register` valida el formulario (R003, R004 y la versión de la política, R022) y, si es válido, responde siempre `202 {status: "check_email"}`.
    - Si el correo no existe, crea establecimiento, cuenta, autorización y token de verificación, y encola el correo de verificación.
    - Si existe, `auth_account_by_email` resuelve su establecimiento, la transacción fija ese contexto y encola el aviso `registration_attempt` con los enlaces a `/entrar` y `/recuperar`, respetando el límite de R027.
    - Las dos ramas calculan un hash Argon2 y escriben en la bandeja de salida, para que el tiempo de respuesta no las distinga.
  - **Verificación:** `POST /api/auth/verify-email {token}` resuelve el token con `auth_email_token`.
    - Si está vigente: marca `used_at` y `email_verified_at`, crea una sesión (D2), responde `200 {status: "verified"}` con la cookie y la SPA lleva al panel.
    - Si está usado y el correo verificado: `200 {status: "already_verified"}`, sin cookie.
    - Si no está usado pero `now > expires_at`: `400 expired_token`, sin verificar ni crear sesión (R028). El orden de comprobación es: usado, caducado, reemplazado o vigente.
    - Si no existe, está alterado o reemplazado: `400 invalid_token`. En ambos casos de error la SPA lo indica («el enlace caducó» o «el enlace no es válido») y ofrece pedir uno nuevo: con sesión, reenvía; sin sesión, lleva a `/entrar` para reenviar desde el panel.
  - **Reenvío:** marca `superseded_at` en los tokens de verificación anteriores.
- **Alternativas descartadas:** responder `409` al correo existente (es lo que hacía R002, que ahora está obsoleto), porque revela la cuenta; mantener el inicio de sesión tras el registro, porque la diferencia con el duplicado delataría el correo; y verificar con un código de 6 dígitos en lugar de un enlace, que no es lo que piden los criterios.
- **Consecuencias:** un propietario que se registra tiene que abrir su correo antes de ver el panel, o entrar con su contraseña (R019 lo permite). El enlace de verificación vale como credencial de un solo uso durante 7 días: quien tenga acceso al buzón en ese plazo puede entrar al panel una vez, lo mismo que con la recuperación de contraseña. La caducidad (R028) limita el riesgo de correos antiguos filtrados.

### D12 — Política de tratamiento versionada desde el backend

- **Contexto:** R022 exige publicar la política sin sesión, enlazarla junto a la autorización y guardar qué versión se aceptó y cuándo. El texto lo aporta el negocio (supuesto de la spec).
- **Decisión:** la política vive en el backend como archivos Markdown versionados (`backend/app/accounts/policy/<versión>.md`), con la versión vigente en configuración (`DATA_POLICY_VERSION`). `GET /api/public/data-policy` devuelve `{version, content}` y la SPA lo muestra en `/politica-de-datos`. El formulario de registro envía la `policy_version` que mostró el enlace; si no coincide con la vigente, el backend responde `422 {policy_version: "outdated"}` y la SPA recarga la política. Así, la versión guardada en `data_authorization` es la que el propietario tuvo delante.
- **Alternativas descartadas:** el texto como página estática de la SPA, porque la versión aceptada podría no coincidir con la que registra el backend; y guardar el texto en base de datos, que no tiene sentido mientras lo publique el equipo y no el propietario.
- **Consecuencias:** cambiar la política es publicar un archivo nuevo y subir `DATA_POLICY_VERSION`. Mientras no llegue el texto del negocio, el repositorio lleva un marcador `0000-borrador.md` que impide pasar a producción (ver Riesgos). Se renombra `data_consent` a `data_authorization` para usar el término de la spec.

## Componentes afectados

| Componente | Cambio | Requisitos que cubre |
| ---------- | ------ | -------------------- |
| `backend/app/accounts/domain/` | Entidades Account, Establishment, Session, EmailToken, DataAuthorization; reglas de registro, normalización de correo, caducidad de sesión, bloqueo por intentos, estado de los tokens (vigente, usado, caducado, reemplazado) y límite de correos; puertos PasswordHasher, EmailSender, Clock | R003, R004, R006, R007, R009, R014, R020, R022, R023, R024, R026, R027, R028 |
| `backend/app/accounts/application/` | Casos de uso: registrar (rama nueva y rama de correo existente), iniciar y cerrar sesión, resolver sesión, verificar correo con creación de sesión, reenviar verificación, pedir y confirmar recuperación (la confirmación revoca todas las sesiones), editar establecimiento, generar QR, obtener la política | R004, R005, R006, R007, R008, R010, R014, R016, R017, R018, R019, R020, R021, R022, R023, R024, R025, R026, R027, R028 |
| `backend/app/accounts/api/` | Routers `/api/auth/*`, `/api/owner/*` y `/api/public/*`; dependencia `current_owner` que fija el contexto RLS; errores por campo; CSRF y HSTS | R003, R005, R006, R008, R010, R012, R013, R015, R016, R018, R019, R022, R023, R024, R025, R026 |
| `backend/app/accounts/infrastructure/` | Repositorios SQLAlchemy, adaptador Argon2, generador del QR con segno + Pillow | R009, R010, R023 |
| `backend/app/accounts/policy/` | Archivos de la política de tratamiento por versión | R022 |
| `backend/app/shared/` | Unidad de trabajo con `SET LOCAL app.establishment_id`, bandeja de salida, trabajador `app.worker` (envío, reintentos, purga de `login_attempt`), adaptadores SES, Mailpit y en memoria, configuración, ejecución de CPU fuera del bucle de eventos con un hilo por núcleo (D3) | R015, R016, R017, R024, R027 |
| `backend/migrations/` | Migración Alembic inicial: tablas, índices, políticas RLS, trigger de `public_code`, funciones `SECURITY DEFINER`, roles `app_migrator`, `app_api` y `app_worker` | R009, R013, R015, R024 |
| `web/src/features/auth/` | Pantallas de registro (con enlace a la política), «revisa tu correo», inicio de sesión, recuperación, restablecimiento y verificación (verificado, ya verificado, inválido y caducado) | R003, R004, R005, R006, R007, R016, R017, R022, R023, R025, R026, R028 |
| `web/src/features/legal/` | Página `/politica-de-datos` | R022 |
| `web/src/features/owner-panel/` | Panel: datos del establecimiento, descarga e impresión del QR con bloqueo si no está verificado, aviso de verificación con reenvío y aviso de espera, cierre de sesión | R008, R010, R011, R014, R018, R019, R020, R027 |
| `web/src/features/public-establishment/` | Página `/l/:code` con el nombre o «establecimiento no encontrado» | R012, R013 |
| Raíz del repo | `docker-compose.yml` con Postgres 16, Redis, Mailpit, `api`, `worker` y `web`; proxy `/api` de Vite; `backend/pyproject.toml` con uv; `web/package.json`; CI (D10) | — |

## Modelo de datos

Todas las tablas, salvo `login_attempt`, llevan `establishment_id` y la política `USING (establishment_id = current_setting('app.establishment_id')::uuid)`, con la misma condición en `WITH CHECK`.

- **`establishment`**: `id uuid PK`, `establishment_id uuid` (igual a `id`, por uniformidad con RLS), `public_code char(10) UNIQUE NOT NULL` (inmutable por trigger), `name text NOT NULL`, `address text NULL`, `phone text NULL`, `created_at`, `updated_at`.
- **`owner_account`**: `id uuid PK`, `establishment_id uuid UNIQUE FK` (una cuenta, un establecimiento), `email text`, `email_normalized text UNIQUE`, `password_hash text`, `email_verified_at timestamptz NULL`, `created_at`.
- **`data_authorization`**: `id`, `establishment_id`, `account_id FK`, `policy_version text`, `granted_at timestamptz`. Registra la autorización de la Ley 1581 con la versión de la política aceptada y su fecha (R022).
- **`owner_session`**: `id`, `establishment_id`, `account_id FK`, `token_hash bytea UNIQUE`, `created_at`, `last_seen_at`, `revoked_at NULL`.
- **`email_token`**: `id`, `establishment_id`, `account_id FK`, `purpose enum(verify, reset)`, `token_hash bytea UNIQUE`, `expires_at NULL`, `used_at NULL`, `superseded_at NULL`, `created_at`. `expires_at` vale `created_at + 60 min` en `reset` y `created_at + 7 días` en `verify`.
- **`email_outbox`**: `id`, `establishment_id`, `to_address`, `to_address_normalized`, `template enum(verify_email, password_reset, registration_attempt)`, `payload jsonb`, `created_at`, `status enum(pending, sent, failed)`, `attempts`, `next_attempt_at`, `sent_at NULL`.
- **`login_attempt`** (sin RLS, ver D5): `email_normalized`, `attempted_at`, `succeeded`; índice `(email_normalized, attempted_at)`.
- Índice `email_outbox(establishment_id, to_address_normalized, template, created_at)` para el límite de R027.

**Roles:**
- `app_migrator`: dueño de las tablas, los tipos y las funciones `SECURITY DEFINER`, con permiso `CREATE` sobre el esquema `public`.
- `app_api`: sin BYPASSRLS, con DML solo sobre las tablas anteriores.
- `app_worker`: sin acceso directo a las tablas; solo ejecuta `outbox_claim`, `outbox_mark` y `login_attempt_purge` (D4).
- Los tres roles son `NOLOGIN`. Cada transacción ejecuta `SET LOCAL ROLE app_api` (o `app_worker` en el trabajador), así que RLS se aplica aunque el usuario de conexión sea un superusuario. **Consecuencia para el despliegue:** el usuario de conexión de cada entorno tiene que ser miembro de `app_api` o `app_worker`.

**Migración:** una única migración Alembic inicial, `0001_accounts`.

## Contratos

Todos los cuerpos van en JSON salvo el PNG. Los errores de validación devuelven `422` con `{"errors": {"<campo>": "<código>"}}`.

| Método y ruta | Entrada | Respuestas |
| ------------- | ------- | ---------- |
| `POST /api/auth/register` | `email`, `password`, `establishment_name`, `address?`, `phone?`, `data_authorization: true`, `policy_version` | `202 {status: "check_email"}`, idéntico exista o no el correo, sin cookie · `422` (incluido `policy_version: outdated`) |
| `POST /api/auth/login` | `email`, `password` | `200 {status: "authenticated"}` con cookie · `401 invalid_credentials` (igual en ambos casos) · `429 too_many_attempts` |
| `POST /api/auth/logout` | — | `204` y la cookie borrada |
| `POST /api/auth/verify-email` | `token` | `200 {status: "verified"}` con cookie de sesión · `200 {status: "already_verified"}` sin cookie · `400 invalid_token` (inexistente, alterado o reemplazado) · `400 expired_token` (sin usar y con más de 7 días, R028) |
| `POST /api/auth/password-reset` | `email` | `202 {status: "check_email"}`, siempre el mismo, incluso si se superó el límite de R027 |
| `POST /api/auth/password-reset/confirm` | `token`, `password` | `204` (revoca todas las sesiones de la cuenta) · `400 invalid_or_expired_token` · `422 {errors: {password: "password_too_short"}}` con menos de 8 caracteres (la misma regla que el registro): no consume el enlace ni cambia la contraseña (R016) |
| `GET /api/owner/me` | — | `200 {account: {email, email_verified}, establishment: {name, address, phone, public_url}}` · `401` |
| `PATCH /api/owner/establishment` | `name?`, `address?`, `phone?`: solo cambian los campos enviados; una dirección o un teléfono vacíos se guardan como `NULL` (R014) | `200 {establishment}` · `401` · `422 {errors: {name: "required"}}` si el nombre llega vacío, sin cambiar nada; la clave es `name`, no `establishment_name` como en el registro |
| `POST /api/owner/email-verification/resend` | — | `202 {status: "check_email"}` · `401` · `409 already_verified` · `429 resend_rate_limited` |
| `GET /api/owner/establishment/qr.png` | — | `200 image/png` (con `Content-Disposition: attachment` si llega `?download=1`) · `401` · `403 email_not_verified` |
| `GET /api/public/establishments/{code}` | — | `200 {name}` · `404 not_found` (el mismo cuerpo para un código mal formado) |
| `GET /api/public/data-policy` | — | `200 {version, content}` |

**Interfaz pública del módulo C1 para otros módulos:** `resolve_owner(session_token) -> OwnerContext(account_id, establishment_id, email_verified)` y `establishment_by_public_code(code) -> PublicEstablishment | None`. B02 y B03 los usarán sin tocar las tablas de C1.

## Estrategia de pruebas

| Requisito | Tipo de prueba | Dónde vive |
| --------- | -------------- | ---------- |
| R003 | unitaria (dominio), integración y componente | `backend/tests/unit/test_registration_rules.py`, `web/src/features/auth/Register.test.tsx` |
| R004 | integración (sin autorización: 422 y nada creado) y componente | `backend/tests/integration/test_register.py`, `web/src/features/auth/Register.test.tsx` |
| R005 | integración y e2e | `backend/tests/integration/test_login.py`, `web/e2e/login.spec.ts` |
| R006 | integración (mismo cuerpo y código en ambos casos) | `backend/tests/integration/test_login.py` |
| R007 | unitaria (regla con reloj falso) e integración | `backend/tests/unit/test_login_throttle.py`, `backend/tests/integration/test_login.py` |
| R008 | integración y e2e | `backend/tests/integration/test_session.py`, `web/e2e/login.spec.ts` |
| R009 | unitaria (generador de código) e integración (unicidad, trigger de inmutabilidad, el registro asigna el código y editar no lo cambia) | `backend/tests/unit/test_public_code.py`, `backend/tests/integration/test_schema.py`, `backend/tests/integration/test_register.py`, `backend/tests/integration/test_establishment.py` |
| R010 | integración: decodificar el PNG con `zxing-cpp` y comprobar la URL y el nombre | `backend/tests/integration/test_qr.py` |
| R011 | e2e (la vista de impresión contiene solo el QR y el nombre) | `web/e2e/qr.spec.ts` |
| R012 | integración y e2e | `backend/tests/integration/test_public_page.py`, `web/e2e/public-page.spec.ts` |
| R013 | integración (código inexistente y mal formado) y e2e | `backend/tests/integration/test_public_page.py`, `web/e2e/public-page.spec.ts` |
| R014 | unitaria (solo cambian los campos enviados, un opcional vacío pasa a `NULL`, el nombre vacío se rechaza), integración (el `public_code` no cambia, `GET /api/public/establishments/{code}` devuelve el nombre nuevo y el nombre vacío da `422` sin cambiar nada) y componente (el error se muestra en el campo) | `backend/tests/unit/test_establishment_changes.py`, `backend/tests/integration/test_establishment.py`, `web/src/features/owner-panel/Panel.test.tsx` |
| R015 | integración: sin sesión, sesión de otro propietario y consulta directa con RLS | `backend/tests/integration/test_isolation.py` |
| R016 | unitaria (caducidad y un solo uso), integración (además, una contraseña nueva de 7 caracteres da `422` y el mismo enlace sirve después) y e2e con Mailpit | `backend/tests/unit/test_email_token.py`, `backend/tests/integration/test_password_reset.py`, `web/e2e/password-reset.spec.ts` |
| R017 | integración (el registro encola el correo de verificación) y e2e con Mailpit | `backend/tests/integration/test_verify_email.py`, `web/e2e/register.spec.ts` |
| R018 | integración y componente (QrCard y PrintQr ante `403`, sin abrir la impresión) | `backend/tests/integration/test_qr.py`, `web/src/features/owner-panel/QrCard.test.tsx`, `web/src/features/owner-panel/PrintQr.test.tsx` |
| R019 | integración | `backend/tests/integration/test_establishment.py` |
| R020 | unitaria (regla de inactividad con reloj falso) e integración | `backend/tests/unit/test_session_expiry.py`, `backend/tests/integration/test_session.py` |
| R022 | integración (la política se sirve sin sesión; `data_authorization` guarda versión y fecha; una versión desfasada da 422) y componente (enlace junto a la casilla) | `backend/tests/integration/test_data_policy.py`, `backend/tests/integration/test_register.py`, `web/src/features/auth/Register.test.tsx`, `web/src/features/legal/DataPolicy.test.tsx` |
| R023 | integración (202 sin cookie, cuenta y establecimiento únicos creados, dirección y teléfono opcionales; después el inicio de sesión entra) y e2e | `backend/tests/integration/test_register.py`, `web/e2e/register.spec.ts` |
| R024 | integración (correo existente con otras mayúsculas: respuesta byte a byte idéntica a la de un registro nuevo, nada creado, aviso `registration_attempt` encolado al titular) | `backend/tests/integration/test_register.py` |
| R025 | integración (el primer uso verifica y devuelve cookie válida; el segundo devuelve `already_verified` sin cookie) y e2e (registro, enlace de Mailpit, dentro del panel) | `backend/tests/integration/test_verify_email.py`, `web/e2e/register.spec.ts` |
| R026 | integración (token alterado y token reemplazado por un reenvío: 400, el correo sigue sin verificar, sin cookie) y componente (mensaje y oferta de un enlace nuevo) | `backend/tests/integration/test_verify_email.py`, `web/src/features/auth/VerifyEmail.test.tsx` |
| R028 | unitaria (estado del token con reloj falso: 6 días vigente, 8 días caducado, usado y caducado sigue «ya verificado») e integración (un token de 8 días da `400 expired_token`, sin cookie y el correo sigue sin verificar; uno de 6 días verifica e inicia sesión) y componente (mensaje «el enlace caducó» con la oferta de uno nuevo) | `backend/tests/unit/test_email_token.py`, `backend/tests/integration/test_verify_email.py`, `web/src/features/auth/VerifyEmail.test.tsx` |
| R027 | unitaria (regla de 3 por hora con reloj falso) e integración (el cuarto correo de recuperación no se encola y la respuesta es igual; el cuarto reenvío da 429; pasada la hora vuelve a enviar) | `backend/tests/unit/test_email_quota.py`, `backend/tests/integration/test_email_quota.py` |
| R021 | integración (dos sesiones abiertas, confirmar el restablecimiento: ambas dan `401` y la contraseña anterior da `401 invalid_credentials`) y e2e con dos contextos de navegador | `backend/tests/integration/test_password_reset.py`, `web/e2e/password-reset.spec.ts` |

**Requisitos no funcionales:**
- **Rendimiento:** prueba de carga con k6 en `perf/accounts.js`: 50 establecimientos concurrentes registrándose, entrando y descargando el QR, con p95 < 2 s; con ella se fijan los parámetros de Argon2 (D3).
- **Compatibilidad:** prueba manual documentada en `docs/qa/qr-escaneo.md`: impresión en carta y escaneo con la cámara nativa de iOS y Android.
- **Privacidad:** una prueba de integración comprueba que `data_authorization` registra versión y fecha y que no se guarda ningún otro dato personal.
- **Seguridad (transporte):** una prueba de integración comprueba que la cookie lleva `Secure` y `HttpOnly` y que la API envía `Strict-Transport-Security`. El cifrado de extremo a extremo se verifica al desplegar.

Las pruebas de integración corren contra el PostgreSQL de docker-compose con el rol `app_api`, nunca con SQLite.

## Riesgos técnicos

| Riesgo | Impacto | Mitigación |
| ------ | ------- | ---------- |
| SES en sandbox: los correos solo llegan a direcciones verificadas | El registro real no puede verificarse en el piloto | Pedir a AWS la salida del sandbox y configurar SPF, DKIM y DMARC antes del piloto (ADR-0011) |
| Una función `SECURITY DEFINER` devuelve más de lo debido | Se rompe el aislamiento (Q6) | Pocas funciones con columnas explícitas, revisión obligatoria y pruebas en `test_definer_functions.py` |
| El coste de Argon2 sube la latencia con carga | El RNF de p95 < 2 s no se cumple | Medido en T023: con el mínimo de OWASP y un hilo por núcleo se cumple en local (D3). Repetir `perf/accounts.js` si cambian los parámetros o la vCPU, y escalar las tareas Fargate |
| La infraestructura de AWS no existe todavía | Los RNF de disponibilidad (99,5 %) y de tráfico cifrado no se pueden verificar en esta feature | Se cierran en una feature de infraestructura aparte (CloudFront con vuelta a `index.html`, ALB, RDS, ECS, SES fuera del sandbox con rebotes por SNS), que conviene abrir antes del piloto; aquí la aplicación queda lista (D9, D10) |
| El texto de la política de tratamiento no ha llegado | No se puede abrir el registro real sin incumplir la Ley 1581 | Marcador `0000-borrador.md` con una comprobación de arranque que impide `ENV=production` mientras la versión vigente sea el borrador (D12) |
| Cambiar el dominio público invalida los QR impresos | Habría que reimprimir los QR de todos los locales | Fijar el dominio definitivo antes del primer QR real; `PUBLIC_BASE_URL` sale de configuración |

## Trazabilidad

Todos los requisitos MUST vigentes de `spec.md` (R003–R006, R008–R010, R012–R015, R017–R026, R028) aparecen en la tabla de componentes y en la de pruebas. Los SHOULD (R007, R011, R016, R027) también están cubiertos. R001 y R002 están obsoletos: sus comportamientos se retiran del plan y los cubren R023, R024 y R025.

R021 se añadió a la spec con `/sdd:amend` a partir de un riesgo de la primera versión de este plan. R022–R027 llegaron con la enmienda posterior a `/sdd:analyze`, y R028 con la enmienda que cerró el riesgo de un enlace de verificación sin caducidad. La enmienda del 2026-10-17 alinea el plan con la implementación: fija los parámetros de Argon2 medidos en T023 (D3) y corrige la redacción de D8, D9, los roles, los contratos y la referencia a las pruebas de las funciones `SECURITY DEFINER`. Recoge también las aclaraciones de R014 (campos parciales y nombre vacío) y de R016 (contraseña nueva de al menos 8 caracteres) en los contratos y en las pruebas, y corrige dónde viven las pruebas de R009. El plan no introduce ningún requisito.
