import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./client";

function fakeFetch(status: number, body: unknown = {}) {
  return vi.fn<typeof fetch>(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  );
}

function sentRequest(fetch: ReturnType<typeof fakeFetch>): Request {
  const [input] = fetch.mock.calls[0] ?? [];
  expect(input).toBeInstanceOf(Request);
  return input as Request;
}

describe("cliente de la API", () => {
  it("F001_R015 cliente envía X-MyPlaylist-Client y credenciales same-origin, y redirige a /entrar ante 401", async () => {
    const fetch = fakeFetch(401, { detail: "unauthenticated" });
    const navigate = vi.fn();
    const api = createApiClient({ fetch, navigate });

    await api.GET("/api/owner/me");

    const request = sentRequest(fetch);
    expect(request.headers.get("X-MyPlaylist-Client")).toBe("web");
    expect(request.credentials).toBe("same-origin");
    expect(new URL(request.url).origin).toBe(window.location.origin);
    expect(new URL(request.url).pathname).toBe("/api/owner/me");
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/entrar");
  });

  it("un 401 al iniciar sesión no redirige: son credenciales incorrectas", async () => {
    const navigate = vi.fn();
    const api = createApiClient({
      fetch: fakeFetch(401, { error: "invalid_credentials" }),
      navigate,
    });

    const { error, response } = await api.POST("/api/auth/login", {
      body: { email: "dueno@ejemplo.com", password: "no-es-esta" },
    });

    expect(response.status).toBe(401);
    expect(error).toEqual({ error: "invalid_credentials" });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("devuelve los datos tipados del panel", async () => {
    const me = {
      account: { email: "dueno@ejemplo.com", email_verified: true },
      establishment: {
        name: "Bar La Esquina",
        address: null,
        phone: null,
        public_url: "http://localhost:5173/l/ABCDEFGHJK",
      },
    };
    const api = createApiClient({ fetch: fakeFetch(200, me) });

    const { data } = await api.GET("/api/owner/me");

    expect(data?.establishment.public_url).toBe(me.establishment.public_url);
  });
});
