# Constitución del proyecto

| Campo | Valor      |
| ----- | ---------- |
| Fecha | 2026-10-27 |

> Reglas que ninguna spec, plan o tarea puede violar. Si una regla aquí impide
> algo que hace falta, se cambia la regla explícitamente, no se ignora.
>
> Las decisiones técnicas concretas (stack, persistencia, despliegue) viven en
> `architecture/` (ADR y estándares S1–S10). Esta constitución no las repite:
> fija cómo se trabaja y qué invariantes no se negocian.

## Principios

1. **La spec es la fuente de verdad.** No se escribe código de una feature sin `spec.md`, `plan.md` y `tasks.md` aprobados por una persona. Si un requisito cambia, se cambia primero la spec (`/sdd:amend`), después el plan y después las tareas. Nunca se cambia el código en silencio.
2. **Todo requisito MUST tiene tarea, prueba y criterios de aceptación.** Cada prueba cita el requisito que verifica, con el prefijo de su feature: `test_F001_R014_…` en Python y `F001_R014 …` en el título de las pruebas web.
3. **Aislamiento por establecimiento.** Ningún dato de un establecimiento (cuenta, cola, pedidos, QR) es visible ni modificable desde otro. Toda tabla de negocio lleva `establishment_id` con una política RLS (ADR-0009, S8), y el identificador del establecimiento sale siempre de la sesión, nunca de la entrada del cliente.
4. **Datos mínimos.**
   - Los clientes del local son anónimos: no se guarda su nombre, correo, teléfono ni ubicación (S9).
   - Del propietario solo se guardan los datos que pide la spec.
   - El tratamiento cumple la Ley 1581 de 2012, con la autorización registrada con su versión y su fecha.
5. **Sin instalación.** Ninguna funcionalidad exige instalar software en los dispositivos del local ni de los clientes: todo es web (ADR-0003).
6. **Solo el propietario controla su cola.** El orden y el contenido de la cola de un establecimiento solo los cambia su propietario, a través de Sesión y cola (C2, S2).
7. **Las decisiones transversales son ADR.** Una decisión que afecta a más de una feature o es cara de revertir no se toma en un plan ni en el código: se propone como ADR en `architecture/adr/` y la acepta una persona.
8. **El código vive bajo `src/`.** Las definiciones de negocio, arquitectura y specs viven en la raíz del repositorio (ADR-0013).

## Estándares de código

- **Lenguajes y versiones:**
  - Python 3.13 (`src/backend/.python-version`), con dependencias gestionadas por uv y bloqueadas en `uv.lock`.
  - TypeScript 6 sobre Node 22 (`src/web/.nvmrc`), con npm y `package-lock.json`.
- **Formato y linting en Python** (`src/backend`):
  - `uv run ruff format --check` y `uv run ruff check`, con longitud de línea 100 y las reglas `E, F, W, I, B, UP, SIM, RUF`;
  - `uv run mypy app tests migrations` en modo `strict`.
- **Formato y linting en web** (`src/web`): `npm run lint`, que ejecuta eslint con `typescript-eslint` estricto y las reglas de `react-hooks`, seguido de `tsc` con `strict` y `noUncheckedIndexedAccess`.
- **Capas del backend:** API → aplicación → dominio. La infraestructura implementa los puertos del dominio, y el dominio no importa FastAPI, Starlette, SQLAlchemy ni clientes HTTP (S1).
- **Estructura de directorios:**
  - `src/backend/app/<módulo>/{api,application,domain,infrastructure}`;
  - `src/web/src/{api,features,routes,ui,test}`;
  - pruebas de carga en `src/perf/` y e2e en `src/web/e2e/` (ADR-0013).
- **Cliente de la API:** los tipos que usa la web se generan desde el OpenAPI del backend (`npm run gen:api`) y se versionan. No se escriben a mano.
- **Idioma:**
  - Los identificadores de código van en inglés.
  - Los comentarios, los textos de la interfaz, los mensajes de commit y los artefactos (`product/`, `architecture/`, `specs/`) van en español.

## Pruebas

- Una tarea solo se da por hecha cuando:
  - pasan las pruebas que nombra su «hecho cuando», con el ID del requisito en el nombre;
  - lint y tipos quedan limpios;
  - el revisor de implementación (`sdd:implementation-reviewer`) la da por cumplida.
- Las pruebas de integración del backend corren contra PostgreSQL real, con el rol de la aplicación (`app_api` o `app_worker`). Nunca con SQLite, para que RLS se pruebe de verdad.
- Toda función `SECURITY DEFINER` nueva tiene una prueba que demuestra que solo devuelve las columnas previstas.
- Los flujos de usuario de una feature tienen pruebas e2e con Playwright contra el entorno de docker-compose. Cuando hay correo de por medio, se leen en Mailpit.
- Un requisito no funcional de rendimiento se verifica con una prueba de carga en `src/perf/`, cuyo resultado queda anotado en el propio script.
- Una prueba manual (impresión, dispositivos reales) se documenta en `docs/qa/`, con dispositivos y resultado. Una tarea que depende de ella no se cierra sin ese resultado.
- **Cobertura:** el CI mide la cobertura de líneas y falla si baja del suelo:
  - backend: 91 %, con unitarias e integración juntas (`uv run pytest --cov`, suelo en `pyproject.toml`);
  - web: 89 % (`npm run test:coverage`, suelo en `vite.config.ts`);
  - tiempo real: 85 % (`npm run test:coverage`, suelo en `vitest.config.ts`).

  El suelo es el valor del primer registro en el CI (2026-10-26), redondeado hacia abajo, y solo puede subir: cuando la cobertura suba, se sube el suelo en el mismo PR. Cuenta la medida del CI, no la local, porque las pruebas que dependen de tiempos recorren ramas un poco distintas en cada ejecución: la web dio 90,02 % en local y 89,91 % en el CI.

## Seguridad y datos

- **Secretos:**
  - Ningún secreto se versiona. `.env` está en `.gitignore`.
  - El CI pasa gitleaks sobre todo el historial en cada PR. Sus excepciones están en `.gitleaks.toml`, por valor exacto y con su motivo; añadir una exige revisarla en el PR.
  - GitHub tiene activados el escaneo de secretos y la protección al hacer push.
  - `src/.env.example` solo lleva valores locales de desarrollo.
  - En producción, los secretos llegan por el entorno de AWS (ADR-0006).
- **Contraseñas:** se guardan solo como hash Argon2id, con los parámetros que fija la configuración (plan D3 de la feature 001).
- **Tokens de sesión y de enlaces de correo:** se guardan solo como hash SHA-256.
- **Lo que nunca se escribe en logs ni en respuestas:** contraseñas, hashes, tokens ni cookies. Los errores de validación no reenvían el valor de la contraseña.
- **Sesión del propietario:**
  - cookie `HttpOnly`, `Secure` y `SameSite=Lax`;
  - las peticiones que modifican algo exigen la cabecera `X-MyPlaylist-Client`, y si llega `Origin`, tiene que ser el de la SPA.
- **Base de datos:** la API y el trabajador nunca se conectan con un rol con `BYPASSRLS` ni con permisos de migración (S8).
- **Respuestas que no revelan cuentas:** una respuesta pública no revela si un correo tiene cuenta. El registro y la recuperación responden igual en los dos casos.
- **Producción:** `ENV=production` no arranca sin SES ni con la política de tratamiento en borrador.

## Límites

- **Dependencias nuevas:** no se añade ninguna sin justificarla en el plan de la feature, con las alternativas que se descartaron.
- **Dependencias prohibidas:**
  - bibliotecas no oficiales de plataformas, como yt-dlp, youtube-dl, ytmusicapi o pytube, y scraping de YouTube;
  - reproducir Spotify en el local;
  - claves de API embebidas en el frontal (S7);
  - SDK de proveedores externos de identidad (S9).
- **Cambios que siempre requieren aprobación humana explícita:**
  - aprobar `spec.md`, `plan.md` y `tasks.md` (`/sdd:approve`);
  - aceptar o rechazar un ADR (`/architecture:review`) y aprobar la arquitectura (`/architecture:approve`);
  - cambiar esta constitución;
  - fusionar en `main`: todo cambio llega por PR con el check `ci` en verde, y el merge lo hace una persona. La protección de la rama lo impone también a los administradores, y prohíbe el force-push y el borrado;
  - desplegar a producción.

## Comprobación

Cómo se hace cumplir cada regla de arriba. Una regla sin fila aquí depende de
que alguien se acuerde, y eso hay que saberlo.

| Regla | Nivel | Mecanismo | Suelo actual |
| ----- | ----- | --------- | ------------ |
| Sin código sin spec, plan y tareas aprobados (principio 1) | mecánica | compuerta del plugin `sdd` (hook `guard` y `audit`) | — |
| Todo MUST con tarea, prueba y criterios; pruebas con `F00N_R0xx` (principio 2) | mecánica | `sdd trace`, en local y en el CI (`trace`, en cada feature, con el plugin en un commit fijo). En una feature con tareas abiertas, un MUST sin prueba todavía no bloquea; cualquier otro error sí, también una tarea cerrada sin su prueba | 0 errores en cada feature cerrada |
| Formato y lint de Python | mecánica | hook de calidad del plugin y CI (`backend`) | 0 avisos |
| Tipos de Python (`mypy --strict`) | mecánica | CI (`backend`) | 0 errores |
| Lint y tipos de web | mecánica | hook de calidad del plugin y CI (`web`) | 0 avisos |
| Tipos de la API generados al día | mecánica | CI (`api-types`) | — |
| El dominio no importa FastAPI, SQLAlchemy ni HTTP (S1) | mecánica | prueba `test_health.py` | — |
| Toda tabla, salvo `login_attempt`, tiene política RLS (principio 3, S8) | mecánica | prueba de `test_schema.py`, que recorre `pg_tables` | — |
| Aislamiento entre establecimientos en la API (principio 3) | mecánica | batería `test_isolation.py`, que se amplía con cada feature | — |
| Integración contra PostgreSQL real, nunca SQLite | mecánica | CI (`backend-integration` con PostgreSQL de servicio) | — |
| Ningún secreto versionado | mecánica | `.gitignore`; CI (`secrets`, gitleaks con `.gitleaks.toml`); escaneo de secretos y protección al hacer push de GitHub | 0 hallazgos |
| Nada sensible en logs ni respuestas | revisable | revisión del diff; pruebas puntuales (422 sin la contraseña) | — |
| Datos mínimos y Ley 1581 (principio 4) | revisable | revisión del diff y de la spec; prueba de privacidad del registro | — |
| Dependencias nuevas justificadas, y las prohibidas (S7, S9) | revisable | revisión del plan y del diff; **candidata a automatizar** (lista de prohibidas contra `uv.lock` y `package-lock.json`) | — |
| Solo C2 modifica la cola (principio 6, S2) | revisable | revisión del diff | — |
| Sin instalación (principio 5) | juicio | criterio humano al aprobar la spec | — |
| Decisiones transversales como ADR (principio 7) | juicio | criterio humano en `/sdd:plan` y `/architecture:review` | — |
| Merge a `main` por PR con CI en verde | mecánica | protección de rama en GitHub: PR obligatorio y el check `ci` en verde, también para administradores | — |
| Cobertura de pruebas | mecánica | CI (`backend-integration`, `web`, `realtime`), que falla por debajo del suelo | líneas: backend 91 %, web 89 %, tiempo real 85 % |

Niveles: **mecánica** (un script la comprueba), **revisable** (requiere leer el
diff y juzgar), **juicio** (la decide una persona caso por caso).

La columna de suelo existe para el ratchet: si el repositorio hoy no cumple un
umbral, se registra lo que hay y solo se permite que suba. Un umbral inalcanzable
termina desactivado, y eso desacredita a todas las demás comprobaciones.

## Preguntas abiertas

Ninguna.

## Historial de cambios

- **2026-10-26 — Cierre de las cuatro preguntas abiertas.** Las decidió el usuario:
  - **Cobertura:** se mide en el CI con suelo, por el ratchet. Dependencias nuevas, solo de desarrollo:
    - `pytest-cov`: integra la cobertura en pytest y respeta `fail_under`. Se descartó `coverage run` a mano, que obliga a repetir la configuración de pytest.
    - `@vitest/coverage-v8`: es el proveedor oficial de Vitest. Se descartó `@vitest/coverage-istanbul`, más lento porque instrumenta el código.
  - **`sdd trace --check` en el CI, bloqueante:** el script del plugin no tiene dependencias, y se descarga de su repositorio en un commit fijo. Se descartó copiarlo al repositorio, porque se desfasaría del plugin sin que nadie lo viera.
  - **Protección de `main`:** PR obligatorio y el check `ci` en verde, también para los administradores, sin force-push ni borrado. No se exige la aprobación de otra persona, porque hoy hay un solo desarrollador y no podría aprobar sus propios PR. `ci` es un trabajo que agrupa a los demás: los trabajos que se saltan por no cambiar su carpeta cuentan como buenos.
  - **Escáner de secretos:** gitleaks en el CI, desde su imagen oficial de Docker, fijada a una versión, sin añadir dependencias a los proyectos. Se descartó confiar solo en el escaneo de GitHub, que no reconoce secretos genéricos. Las cuatro coincidencias que encontró en el historial eran valores de prueba versionados a propósito, y quedan como excepciones por su valor exacto.
- **2026-10-27 — Trazabilidad de las features en curso.**
  - **El problema:** con `sdd trace --check` estricto, la spec de una feature no se podía fusionar antes de implementarla, porque sus requisitos MUST aún no tienen prueba.
  - **La regla nueva, que decidió el usuario:** mientras una feature tenga alguna tarea sin cerrar, `E-REQ-NO-TEST` no bloquea. Los demás errores sí, incluido `E-DONE-NO-TEST`: una tarea cerrada sin su prueba. Con todas sus tareas cerradas, cualquier error bloquea. La aplica `.github/scripts/trace_check.py`.
  - **Alternativas descartadas:**
    - Saltar las features en curso: no detectaría una tarea cerrada sin prueba hasta el final.
    - Fusionar la spec junto con el código: deja las decisiones sin revisar en `main` hasta que la feature termina.
