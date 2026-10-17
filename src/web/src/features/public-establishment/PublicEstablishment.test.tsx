import { act, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";

describe("página pública del establecimiento", () => {
  it("F001_R012 muestra el nombre sin pedir registro", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/establishments/ABCDEFGHJK": { status: 200, body: { name: "Café Ñandú" } },
    });
    renderRoute("/l/ABCDEFGHJK", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Café Ñandú");
    // Nada que pida registrarse, entrar o instalar: ni formularios ni enlaces.
    expect(document.querySelector("form, input, button")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(sent).toEqual([
      { method: "GET", path: "/api/public/establishments/ABCDEFGHJK", body: undefined },
    ]);
  });

  it("F001_R013 muestra establecimiento no encontrado ante 404 sin otros datos", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/ZZZZZZZZZZ": { status: 404, body: { error: "not_found" } },
    });
    renderRoute("/l/ZZZZZZZZZZ", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Establecimiento no encontrado",
    );
    // Solo el aviso: ni el código pedido ni datos de ningún local.
    expect(screen.getByRole("main")).toHaveTextContent(
      "Establecimiento no encontradoRevisa que el enlace o el código QR estén completos.",
    );
  });

  it("F001_R013 un código con caracteres especiales se envía codificado", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/establishments/a%2Fb%20c": { status: 404, body: { error: "not_found" } },
    });
    renderRoute("/l/a%2Fb%20c", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Establecimiento no encontrado",
    );
    expect(sent[0]?.path).toBe("/api/public/establishments/a%2Fb%20c");
  });

  it("un fallo del servidor no se confunde con un establecimiento inexistente", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/ABCDEFGHJK": { status: 500 },
    });
    renderRoute("/l/ABCDEFGHJK", client);

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    expect(screen.queryByText("Establecimiento no encontrado")).not.toBeInTheDocument();
  });

  it("F001_R013 al cambiar de código no se ve el nombre del anterior", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/AAAAAAAAAA": { status: 200, body: { name: "Bar A" } },
      "GET /api/public/establishments/BBBBBBBBBB": { status: 200, body: { name: "Café B" } },
    });
    const router = renderRoute("/l/AAAAAAAAAA", client);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Bar A");

    await act(() => router.navigate("/l/BBBBBBBBBB"));

    expect(screen.queryByText("Bar A")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Café B");
  });
});
