# Web

SPA única de MyPlaylist (ADR-0003), hecha con React 19, React Router, Vite y TypeScript. Por ahora contiene las pantallas del propietario y la página pública que abre el QR (feature 001). Las siguientes features añaden aquí la aplicación del cliente, el reproductor del local y la pantalla de cola.

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
| `/l/:code` | Página pública del establecimiento (a donde lleva el QR) |
| `/politica-de-datos` | Política de tratamiento de datos |

Cada ruta se carga bajo demanda (`src/routes/*.tsx`).

## Estructura

```
src/
├── api/          cliente de la API: schema.d.ts (generado), client.ts, contexto y errores
├── features/     auth, owner-panel, public-establishment, legal y shared
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

Cada prueba lleva en el título el ID del requisito que verifica: `F001_R014 …`.
