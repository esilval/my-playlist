# MyPlaylist

Encolador de canciones para establecimientos (bares, restaurantes…) como SaaS por suscripción. Los clientes del local escanean un QR, buscan canciones y las ponen en la cola desde el móvil, sin instalar nada ni registrarse. El propietario controla lo que suena desde su panel. El lanzamiento inicial es en Bogotá.

## Objetivos del producto

| ID | Objetivo |
| -- | -------- |
| G1 | Los clientes ponen su música en el local desde el móvil, con un reparto justo (cupo de 5 canciones pendientes por cliente en el Plan Básico). |
| G2 | El propietario controla la música de su local: abre y cierra la sesión, ve, reordena y limpia la cola, y agrega sus canciones. |
| G3 | La música no se detiene: si la cola se vacía o una canción falla, entra relleno automático. |
| G4 | MyPlaylist se sostiene como SaaS: alta autónoma por la web, prueba gratuita de 30 días y planes Básico y Premium cobrados en COP. |

**Usuarios:**
- **Cliente:** anónimo, identificado solo por su dispositivo.
- **Propietario:** una cuenta por establecimiento, sin empleados.

**Restricciones clave:**
- Solo YouTube en el piloto. Spotify no permite su uso comercial en locales; al crecer, se pasará a un proveedor B2B con licencia.
- Tratamiento de datos conforme a la Ley 1581 de 2012.
- Objetivos de calidad del piloto: 50 locales y 100 clientes por local, búsqueda en menos de 2 s y disponibilidad del 99,5 %.

El detalle está en [`product/brief.md`](product/brief.md), y el documento de origen en [`documentation/overview.md`](documentation/overview.md).

## Estado

| Candidata | Funcionalidad | Estado |
| --------- | ------------- | ------ |
| B01 | Alta del establecimiento y su QR | **Implementada** ([feature 001](specs/001-alta-establecimiento-qr/)). Falta la prueba manual de escaneo del QR impreso. |
| B02 | Sesión de música y reproductor del local | **En curso** ([feature 002](specs/002-sesion-musica-reproductor-local/)): hechos el backend y el servicio de tiempo real; faltan el reproductor y la tarjeta del panel en la web. |
| B03 | Pedir canciones desde el QR | Pendiente |
| B04 | Ventana anti-repetición | Pendiente |
| B05 | Administrar la cola de la sesión | Pendiente |
| B06 | Pantalla pública de la cola | Pendiente |
| B07 | Relleno automático cuando la cola se vacía | Pendiente |
| B08 | Canciones de Spotify en la cola | Descartada (ADR-0010) |
| B09 | Prueba gratuita y suscripción | Pendiente |
| B10 | Límites ampliados del Plan Premium | Pendiente |

Backlog completo: [`product/backlog.md`](product/backlog.md).

## Estructura del repositorio

Las definiciones de negocio y arquitectura viven en la raíz, y el código que se entrega bajo `src/` (ADR-0013).

```
product/          Brief, backlog y documentos de origen (qué y por qué)
architecture/     Componentes, atributos de calidad, estándares y decisiones (ADR)
specs/            Una carpeta por feature: spec.md, plan.md y tasks.md
docs/qa/          Pruebas manuales documentadas
documentation/    Descripción original del producto
.github/          CI (GitHub Actions)
src/
├── backend/      Monolito modular en Python/FastAPI → src/backend/README.md
├── web/          SPA React + Vite para todos los frontales → src/web/README.md
├── realtime/     Servicio de tiempo real (Node + Socket.IO) → src/realtime/README.md
├── perf/         Pruebas de carga con k6 → src/perf/README.md
├── docker-compose.yml
└── .env.example
```

`src/infra/` (infraestructura como código) está reservado por ADR-0013. Se crea con la primera feature que despliegue.

## Arquitectura

Monolito modular en FastAPI más un servicio de tiempo real en Node con Socket.IO. Hay una sola SPA en React para todos los frontales, con PostgreSQL como fuente de verdad y Redis para el estado vivo. El despliegue es en AWS us-east-1, con contenedores en ECS Fargate.

**Componentes** ([`architecture/components.md`](architecture/components.md)):

| ID | Componente | Candidatas |
| -- | ---------- | ---------- |
| C1 | Cuentas y establecimientos | B01 |
| C2 | Sesión y cola | B02, B03, B04, B05, B07, B10 |
| C3 | Catálogo de plataformas (adaptador de YouTube) | B03, B05, B07 |
| C4 | Reproductor del local | B02 |
| C5 | Aplicación del cliente | B03, B04 |
| C6 | Difusión en tiempo real | B02, B06 |
| C7 | Panel del propietario | B01, B02, B04, B05, B07, B09, B10 |
| C8 | Suscripciones y cobro | B09, B10 |
| C9 | Pantalla de cola | B06 |

**Decisiones vigentes** ([`architecture/adr/`](architecture/adr/)):

| ADR | Decisión |
| --- | -------- |
| 0001 | Monolito modular más un servicio de tiempo real |
| 0002 | Python/FastAPI en el backend; TypeScript en frontales y tiempo real |
| 0003 | Una sola SPA React con Vite para todos los frontales |
| 0004 | PostgreSQL como fuente de verdad y Redis para estado vivo |
| 0005 | WebSocket propio con Socket.IO y pub/sub en Redis |
| 0006 | AWS con contenedores en us-east-1 |
| 0007 | Autenticación propia del propietario y token anónimo del cliente |
| 0009 | Aislamiento por establecimiento con columna y Row-Level Security |
| 0010 | YouTube como única plataforma del piloto, con salida a un proveedor B2B (sustituye a 0008) |
| 0011 | Correo transaccional con Amazon SES |
| 0013 | Monorepo con el código bajo `src/` (sustituye a 0012) |
| 0014 | Acceso al tiempo real con un ticket de corta duración firmado por el monolito |

Los estándares transversales (capas del monolito, `establishment_id` y RLS en toda tabla, nada de datos personales de clientes…) están en [`architecture/standards.md`](architecture/standards.md).

## Cómo se trabaja

El proyecto sigue un flujo orientado a especificaciones con los plugins `discovery`, `architecture` y `sdd` de Claude Code:

1. **Discovery:** `product/brief.md` y `product/backlog.md`, con las candidatas B01…B10.
2. **Arquitectura:** componentes y ADR en `architecture/`. Una decisión nueva se propone como ADR y la aprueba una persona.
3. **Por feature** (`specs/NNN-slug/`):
   - `spec.md`: requisitos en notación EARS (R001…) con criterios de aceptación;
   - `plan.md`: cómo se construye, con sus decisiones y las alternativas descartadas;
   - `tasks.md`: tareas atómicas y trazables.

   Cada artefacto se aprueba antes de escribir código.
4. **Trazabilidad:** cada prueba lleva el ID del requisito que verifica (`test_F001_R014_…` o `F001_R014 …`). `sdd trace` comprueba que todo requisito MUST tenga tarea, prueba y criterios.

Si un requisito cambia, se cambia primero la spec (`/sdd:amend`) y después el plan y las tareas.

## Puesta en marcha

Requisitos: Docker, [uv](https://docs.astral.sh/uv/) y Node 22 (`src/web/.nvmrc`).

```bash
cd src
docker compose up -d --build
```

| Servicio | URL |
| -------- | --- |
| SPA (con `/api` reenviado a la API y `/socket.io` al tiempo real) | http://localhost:5173 |
| API (directa) | http://localhost:8000/api/health |
| Mailpit (correos de prueba) | http://localhost:8025 |
| PostgreSQL / Redis | `localhost:5432` / `localhost:6379` |

La API aplica las migraciones al arrancar, y el servicio `worker` envía los correos a Mailpit. Para probar el alta completa:
1. Regístrate en http://localhost:5173/registro.
2. Abre el enlace de verificación en Mailpit.
3. Descarga o imprime el QR desde el panel.

## Pruebas

| Qué | Dónde | Comando |
| --- | ----- | ------- |
| Backend: unitarias e integración contra PostgreSQL y Redis reales | `src/backend` | `uv run pytest` |
| Tiempo real: tickets, salas y reenvío contra Redis real | `src/realtime` | `npm test` |
| Web: componentes | `src/web` | `npm test` |
| e2e con Playwright y Mailpit | `src/web` | `npx playwright test` (con el compose levantado) |
| Carga con k6 | `src/perf` | ver [`src/perf/README.md`](src/perf/README.md) |
| Escaneo del QR impreso (manual) | `docs/qa` | [`docs/qa/qr-escaneo.md`](docs/qa/qr-escaneo.md) |
| Reproductor con YouTube real (manual) | `docs/qa` | [`docs/qa/reproductor-youtube.md`](docs/qa/reproductor-youtube.md) |

El CI (`.github/workflows/ci.yml`) corre lint, tipos y pruebas del backend, de la web y del tiempo real solo si cambia su carpeta. Las pruebas de integración corren contra PostgreSQL y Redis de servicio, y el CI comprueba que los tipos de la API generados para la web estén al día. Además:
- mide la cobertura de líneas y falla si baja del suelo: backend 91 %, web 90 % y tiempo real 85 %;
- ejecuta `sdd trace --check` en cada feature de `specs/`;
- pasa gitleaks sobre todo el historial, con las excepciones de `.gitleaks.toml`.

El trabajo `ci` agrupa a todos y es el check obligatorio para fusionar en `main`. Las reglas y sus suelos están en la tabla «Comprobación» de [`specs/constitution.md`](specs/constitution.md).

## Pendiente

- **Feature 001:** la prueba manual de escaneo del QR impreso con iOS y Android (T023).
- **Feature 002:** la web (T014–T020): cliente de tiempo real, reproductor con YouTube, tarjeta de la sesión en el panel, e2e y la prueba manual con YouTube real.
- **Feature de infraestructura**, antes del piloto:
  - CloudFront, ALB, RDS, ECS Fargate;
  - SES fuera del sandbox, con SPF, DKIM y DMARC;
  - verificar la disponibilidad y el cifrado de extremo a extremo.
- **Política de tratamiento de datos:** falta el texto definitivo del negocio. Hasta entonces, la aplicación no arranca con `ENV=production`.
