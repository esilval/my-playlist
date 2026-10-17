import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";

const CONTENT = `# Política de tratamiento — BORRADOR

> **Texto provisional.** Lo aportará el negocio.

MyPlaylist guarda del propietario solo
los datos de su cuenta.

- Correo
- Contraseña cifrada

<script>alert("x")</script>`;

describe("política de tratamiento de datos", () => {
  it("F001_R022 muestra la política y su versión sin sesión", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": { status: 200, body: { version: "0000-borrador", content: CONTENT } },
    });
    renderRoute("/politica-de-datos", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Política de tratamiento de datos",
    );
    expect(screen.getByText("0000-borrador")).toBeInTheDocument();
    const article = screen.getByRole("article");
    expect(within(article).getByRole("heading", { level: 2 })).toHaveTextContent("BORRADOR");
    expect(within(article).getByText("Texto provisional.").tagName).toBe("STRONG");
    expect(within(article).getByText(/guarda del propietario solo los datos de su cuenta/)).toBeInTheDocument();
    expect(within(article).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Correo",
      "Contraseña cifrada",
    ]);
    // Sin sesión: una sola petición, la pública.
    expect(sent.map((r) => r.path)).toEqual(["/api/public/data-policy"]);
  });

  it("el contenido nunca se interpreta como HTML", async () => {
    const { client } = fakeApi({
      "GET /api/public/data-policy": { status: 200, body: { version: "v", content: CONTENT } },
    });
    renderRoute("/politica-de-datos", client);
    await screen.findByRole("article");

    expect(document.querySelector("article script")).toBeNull();
    expect(screen.getByText('<script>alert("x")</script>')).toBeInTheDocument();
  });

  it("un fallo al cargarla muestra el error de conexión", async () => {
    const { client } = fakeApi({ "GET /api/public/data-policy": { status: 500 } });
    renderRoute("/politica-de-datos", client);

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
  });
});
