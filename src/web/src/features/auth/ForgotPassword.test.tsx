import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";
import { RESET_REQUESTED } from "./ForgotPassword";

describe("recuperar contraseña", () => {
  it.each([
    [202, { status: "check_email" }],
    [422, { errors: { email: "invalid" } }],
    [429, { error: "too_many_requests" }],
  ])("F001_R016 mismo mensaje tras pedir recuperación (respuesta %i)", async (status, body) => {
    const { client, sent } = fakeApi({ "POST /api/auth/password-reset": { status, body } });
    renderRoute("/recuperar", client);
    await screen.findByRole("heading", { name: "Recuperar contraseña" });
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "nadie@ejemplo.com" } });

    fireEvent.click(screen.getByRole("button", { name: "Enviar enlace" }));

    expect(await screen.findByRole("status")).toHaveTextContent(RESET_REQUESTED);
    expect(sent).toEqual([
      { method: "POST", path: "/api/auth/password-reset", body: { email: "nadie@ejemplo.com" } },
    ]);
  });
});
