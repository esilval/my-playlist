import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { ownerMe } from "../owner-panel/fixtures";
import { renderRoute } from "../../test/render-route";

async function login(email: string, password: string) {
  await screen.findByRole("heading", { name: "Entrar" });
  fireEvent.change(screen.getByLabelText("Correo"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("inicio de sesión", () => {
  it("F001_R005 credenciales correctas llevan al panel", async () => {
    const { client } = fakeApi({
      "POST /api/auth/login": { status: 200, body: { status: "authenticated" } },
      "GET /api/owner/me": { status: 200, body: ownerMe() },
    });
    const router = renderRoute("/entrar", client);

    await login("dueno@ejemplo.com", "contraseña-segura");

    await screen.findByRole("heading", { name: "Bar La Esquina" });
    expect(router.state.location.pathname).toBe("/panel");
  });

  it("F001_R006 muestra el mensaje genérico", async () => {
    const { client } = fakeApi({
      "POST /api/auth/login": { status: 401, body: { error: "invalid_credentials" } },
    });
    const router = renderRoute("/entrar", client);

    await login("nadie@ejemplo.com", "no-es-esta");

    expect(await screen.findByRole("alert")).toHaveTextContent("Correo o contraseña incorrectos.");
    expect(router.state.location.pathname).toBe("/entrar");
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
  });

  it("F001_R007 muestra el aviso de espera ante 429", async () => {
    const { client } = fakeApi({
      "POST /api/auth/login": { status: 429, body: { error: "too_many_attempts" } },
    });
    renderRoute("/entrar", client);

    await login("dueno@ejemplo.com", "contraseña-segura");

    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 15 minutos");
  });
});
