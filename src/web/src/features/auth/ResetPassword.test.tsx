import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi, type FakeResponse } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";

async function resetWith(response: FakeResponse, password = "contraseña-nueva") {
  const api = fakeApi({ "POST /api/auth/password-reset/confirm": response });
  renderRoute("/restablecer?token=tok123", api.client);
  await screen.findByRole("heading", { name: "Nueva contraseña" });
  fireEvent.change(screen.getByLabelText("Contraseña nueva"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar contraseña" }));
  return api;
}

describe("restablecer contraseña", () => {
  it("F001_R016 fija la contraseña nueva con el token del enlace", async () => {
    const { sent } = await resetWith({ status: 204 });

    expect(await screen.findByRole("heading", { name: "Contraseña cambiada" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("cerramos las sesiones");
    expect(sent[0]?.body).toEqual({ token: "tok123", password: "contraseña-nueva" });
  });

  it("F001_R016 enlace usado o caducado ofrece pedir uno nuevo", async () => {
    await resetWith({ status: 400, body: { error: "invalid_or_expired_token" } });

    expect(await screen.findByRole("heading", { name: "Enlace no válido" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pedir un enlace nuevo" })).toHaveAttribute("href", "/recuperar");
  });

  it("contraseña corta se señala en el campo y lo vacía", async () => {
    await resetWith({ status: 422, body: { errors: { password: "password_too_short" } } }, "1234567");

    expect(await screen.findByText("La contraseña debe tener al menos 8 caracteres.")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña nueva")).toHaveValue("");
  });
});
