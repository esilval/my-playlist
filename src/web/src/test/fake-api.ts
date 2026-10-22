// API falsa para pruebas de componentes: responde por «MÉTODO /ruta» y registra las
// peticiones (con su cuerpo) para comprobar qué envió la pantalla.
import { vi } from "vitest";

import { createApiClient, type ApiClient } from "../api/client";

export interface FakeResponse {
  status: number;
  body?: unknown;
}

export interface SentRequest {
  method: string;
  path: string;
  body: unknown;
}

type Handler = FakeResponse | ((body: unknown) => FakeResponse);

export function fakeApi(handlers: Record<string, Handler>) {
  const sent: SentRequest[] = [];
  const navigate = vi.fn();
  const fetch = vi.fn<typeof globalThis.fetch>(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    // Se anota en el orden en que se hicieron las peticiones, antes de leer el cuerpo.
    const entry: SentRequest = { method: request.method, path, body: undefined };
    sent.push(entry);
    const text = await request.text();
    const body: unknown = text ? JSON.parse(text) : undefined;
    entry.body = body;
    const handler = handlers[`${request.method} ${path}`];
    const response = typeof handler === "function" ? handler(body) : handler;
    if (!response) {
      throw new Error(`Sin respuesta preparada para ${request.method} ${path}`);
    }
    if (response.body instanceof Uint8Array) {
      // ArrayBuffer y no Blob: el Response de Node no acepta el Blob de jsdom.
      return new Response(response.body.slice().buffer, {
        status: response.status,
        headers: { "content-type": "image/png" },
      });
    }
    return new Response(response.body === undefined ? null : JSON.stringify(response.body), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  });
  const client: ApiClient = createApiClient({ fetch, navigate });
  return { client, sent, navigate, fetch };
}
