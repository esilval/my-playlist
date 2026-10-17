import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi, type FakeResponse } from "../../test/fake-api";
import { ownerMe } from "../owner-panel/fixtures";
import { renderRoute } from "../../test/render-route";

function verifyWith(response: FakeResponse) {
  const api = fakeApi({
    "POST /api/auth/verify-email": response,
    "GET /api/owner/me": { status: 200, body: ownerMe() },
  });
  const router = renderRoute("/verificar?token=abc123", api.client);
  return { ...api, router };
}

describe("verificación del correo", () => {
  it("F001_R025 verificado lleva al panel", async () => {
    const { router, sent } = verifyWith({ status: 200, body: { status: "verified" } });

    await screen.findByRole("heading", { name: "Bar La Esquina" });
    expect(router.state.location.pathname).toBe("/panel");
    // Una sola llamada a verificar: el enlace es de un solo uso.
    expect(sent.filter((r) => r.path === "/api/auth/verify-email")).toEqual([
      { method: "POST", path: "/api/auth/verify-email", body: { token: "abc123" } },
    ]);
  });

  it("F001_R017 ya verificado lo indica", async () => {
    verifyWith({ status: 200, body: { status: "already_verified" } });

    expect(await screen.findByRole("heading", { name: "Tu correo ya está verificado" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Entrar" })).toHaveAttribute("href", "/entrar");
  });

  it("F001_R026 enlace inválido ofrece pedir uno nuevo", async () => {
    const api = fakeApi({
      "POST /api/auth/verify-email": { status: 400, body: { error: "invalid_token" } },
      "POST /api/owner/email-verification/resend": { status: 202, body: { status: "check_email" } },
    });
    const router = renderRoute("/verificar?token=abc123", api.client);

    expect(await screen.findByRole("heading", { name: "El enlace no es válido" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/verificar");

    // Con sesión, el botón reenvía el enlace.
    fireEvent.click(screen.getByRole("button", { name: "Pedir un enlace nuevo" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Te enviamos un enlace nuevo");
    expect(api.sent.at(-1)).toMatchObject({ method: "POST", path: "/api/owner/email-verification/resend" });
    expect(api.navigate).not.toHaveBeenCalled();
  });

  it("F001_R028 enlace caducado lo indica y ofrece uno nuevo", async () => {
    const api = fakeApi({
      "POST /api/auth/verify-email": { status: 400, body: { error: "expired_token" } },
      "POST /api/owner/email-verification/resend": { status: 401, body: { detail: "unauthenticated" } },
    });
    const router = renderRoute("/verificar?token=abc123", api.client);

    expect(await screen.findByRole("heading", { name: "El enlace caducó" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("caducan a los 7 días");
    expect(router.state.location.pathname).toBe("/verificar");

    // Sin sesión, pedir uno nuevo lleva a entrar primero.
    fireEvent.click(screen.getByRole("button", { name: "Pedir un enlace nuevo" }));
    await waitFor(() => expect(api.navigate).toHaveBeenCalledWith("/entrar"));
  });

  it("F001_R027 pedir uno nuevo con el límite alcanzado pide esperar", async () => {
    const api = fakeApi({
      "POST /api/auth/verify-email": { status: 400, body: { error: "invalid_token" } },
      "POST /api/owner/email-verification/resend": {
        status: 429,
        body: { error: "resend_rate_limited" },
      },
    });
    renderRoute("/verificar?token=abc123", api.client);
    await screen.findByRole("heading", { name: "El enlace no es válido" });

    fireEvent.click(screen.getByRole("button", { name: "Pedir un enlace nuevo" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Espera una hora");
  });
});
