// Cliente de la API del monolito, con los tipos generados desde su OpenAPI (ADR-0002).
// La SPA y la API comparten origen (plan D9, D10): la cookie de sesión viaja sola.
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

// Cabecera propia que exige la protección CSRF en toda petición que modifica algo (D9).
export const CLIENT_HEADER = { "X-MyPlaylist-Client": "web" } as const;

const OWNER_PREFIX = "/api/owner/";
// A dónde lleva un 401 del panel: la pantalla de inicio de sesión (plan D9).
export const LOGIN_PATH = "/entrar";

export type ApiClient = ReturnType<typeof createClient<paths>>;

export interface ApiClientOptions {
  // Cómo navegar ante un 401 del panel (sin sesión o caducada, R015, R020); por
  // defecto, una navegación completa del navegador.
  navigate?: (path: string) => void;
  fetch?: typeof globalThis.fetch;
  // El origen de la página: la API vive en el mismo (D10). Rutas absolutas, porque
  // fuera del navegador `Request` no resuelve rutas relativas.
  baseUrl?: string;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? window.location.origin,
    credentials: "same-origin",
    headers: CLIENT_HEADER,
    fetch: options.fetch,
  });

  const navigate = options.navigate ?? ((path: string) => window.location.assign(path));
  const sessionGuard: Middleware = {
    onResponse({ request, response }) {
      // Solo el panel: un 401 al iniciar sesión es «credenciales incorrectas» (R006).
      if (response.status === 401 && new URL(request.url).pathname.startsWith(OWNER_PREFIX)) {
        navigate(LOGIN_PATH);
      }
      return response;
    },
  };
  client.use(sessionGuard);
  return client;
}

export const api = createApiClient();
