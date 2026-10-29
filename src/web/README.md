# Web

SPA única de MyPlaylist (ADR-0003), hecha con React 19, React Router, Vite y TypeScript. Contiene las pantallas del propietario (feature 001), el reproductor del local y la tarjeta de la sesión de música (feature 002), y la página del QR, donde el cliente busca y pide canciones (feature 003). La pantalla de cola llegará con B06.

## Rutas

| Ruta | Pantalla |
| ---- | -------- |
| `/registro` | Crear cuenta y establecimiento, con la autorización de tratamiento de datos |
| `/registro/revisa-tu-correo` | Aviso tras registrarse (el mismo exista o no el correo) |
| `/verificar?token=` | Verificación del correo; la primera vez inicia sesión |
| `/entrar` | Inicio de sesión |
| `/recuperar` · `/restablecer?token=` | Recuperación de contraseña |
| `/panel` | Datos del establecimiento, QR y cierre de sesión |
| `/panel/qr/imprimir` | Vista de impresión del QR |
| `/panel/reproductor` | Reproductor del local |
| `/l/:code` | Página del QR: el cliente busca y pide canciones, sin registrarse |
| `/politica-de-datos` | Política de tratamiento de datos |

Cada ruta se carga bajo demanda (`src/routes/*.tsx`).

## Estructura

```
src/
├── api/          cliente de la API: schema.d.ts (generado), client.ts, contexto y errores
├── features/     auth, owner-panel, music-session, player, public-establishment, legal y shared
├── realtime/     cliente de tiempo real (Socket.IO) y useRoomEvents / useClientRoomEvents
├── routes/       un módulo por ruta, con carga diferida
├── ui/           componentes comunes (Field)
├── test/         setup de Vitest, API falsa y renderRoute
└── router.tsx    tabla de rutas
e2e/              Playwright contra el entorno de docker-compose
scripts/gen-api.sh  regenera src/api/schema.d.ts desde el OpenAPI del backend
```

**Cliente de la API:**
- Se genera con `openapi-typescript` y se usa con `openapi-fetch`, siempre sobre el mismo origen y con `credentials: "same-origin"`.
- Añade la cabecera `X-MyPlaylist-Client`, que la API exige contra CSRF.
- Si `/api/owner/*` responde 401, lleva a `/entrar`.

**La página del cliente (`/l/:code`, feature 003):**
- Con la sesión de música abierta, muestra un buscador, lo que suena, las canciones pendientes del cliente y «Te quedan N de 5». Con la sesión cerrada, solo un aviso.
- Solo busca al pulsar «Buscar», no mientras se escribe: cada búsqueda cuenta para el límite de 10 por minuto.
- Cada rechazo de la API tiene su aviso: cupo lleno, canción ya en la cola, canción no disponible, búsqueda no disponible y demasiadas búsquedas.
- La primera carga trae la cookie del dispositivo, `mp_device`. Después se abre la sala de tiempo real del establecimiento, y tras cada cambio de la cola la página vuelve a pedir el estado del cliente, sin recargar.
- La búsqueda va siempre por la API del monolito, nunca a YouTube. En local, la API usa el catálogo falso: busca cualquier texto y pide «Canción n de …», que en el reproductor falso suena 3 s (ver `src/backend/README.md`).

## Desarrollo

Requiere Node 22 (`.nvmrc`; con nvm, `nvm use`).

```bash
cd src/web
npm install
npm run dev          # http://localhost:5173; reenvía /api a http://localhost:8000
```

El proxy de Vite apunta a `API_PROXY_TARGET`, que por defecto es `http://localhost:8000`. En docker-compose vale `http://api:8000`. La SPA y la API comparten origen para que la cookie de sesión sea de primera parte. También se puede levantar todo desde `src/` con `docker compose up -d --build`.

| Script | Qué hace |
| ------ | -------- |
| `npm run dev` | Servidor de desarrollo |
| `npm run build` | Comprueba tipos y genera `dist/` |
| `npm run lint` | eslint y tsc |
| `npm test` | Pruebas de componente con Vitest y Testing Library (jsdom) |
| `npm run test:e2e` | Playwright (necesita el compose levantado) |
| `npm run gen:api` | Regenera los tipos de la API (necesita uv y `../backend`) |

Si cambia la API, hay que ejecutar `npm run gen:api` y hacer commit de `src/api/schema.d.ts`: el CI falla si los tipos no están al día.

## Pruebas

- **Componente (`*.test.tsx`):** usan una API falsa (`src/test/fake-api.ts`) y `renderRoute`.
- **e2e (`e2e/*.spec.ts`):**
  - Corren contra `http://localhost:5173`; otra dirección se indica con `E2E_BASE_URL`.
  - Leen los correos en Mailpit (`MAILPIT_URL`, por defecto `http://localhost:8025`).
  - Solo usan Chromium, que acepta la cookie `Secure` sobre http en localhost.
  - Instala el navegador una vez con `npx playwright install chromium`.

Las del cliente que pide desde el QR (feature 003) son `src/features/public-establishment/PublicEstablishment.test.tsx`, `src/realtime/client.test.ts` y `e2e/client.spec.ts`. Las e2e abren un móvil simulado (Pixel 7) sin cuenta, buscan en el catálogo falso y piden. Dos de ellas también usan el reproductor del local. Con el compose levantado:

```bash
npx playwright test e2e/client.spec.ts
```

Cada prueba lleva en el título el ID del requisito que verifica: `F001_R014 …`.
