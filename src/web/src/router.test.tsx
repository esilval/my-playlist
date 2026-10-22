import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./api/client";
import { renderRoute } from "./test/render-route";

import { routes } from "./router";

const EXPECTED_PATHS = [
  "/registro",
  "/registro/revisa-tu-correo",
  "/entrar",
  "/recuperar",
  "/restablecer",
  "/verificar",
  "/politica-de-datos",
  "/panel",
  "/panel/qr/imprimir",
  "/panel/reproductor",
  "/l/:code",
];

describe("rutas de la SPA (plan D9)", () => {
  it("declara exactamente las rutas del plan", () => {
    expect(routes.map((route) => route.path).sort()).toEqual([...EXPECTED_PATHS].sort());
  });

  it("carga cada ruta bajo demanda", () => {
    const eager = routes.filter((route) => typeof route.lazy !== "function" || route.Component);
    expect(eager.map((route) => route.path)).toEqual([]);
  });

  it.each(EXPECTED_PATHS)("carga el módulo de %s y renderiza su pantalla", async (path) => {
    // Ninguna ruta debe llegar a la red de verdad durante la prueba.
    const fetch = vi.fn<typeof globalThis.fetch>(
      async () => new Response(JSON.stringify({}), { status: 404 }),
    );
    const url = path.replace(":code", "AAAAAAAAAA");
    renderRoute(url, createApiClient({ fetch, navigate: vi.fn() }));

    expect(await screen.findByRole("main")).not.toBeEmptyDOMElement();
  });
});
