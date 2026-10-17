import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";
import { ownerMe } from "./fixtures";

describe("panel del propietario", () => {
  it("F001_R014 guardar datos muestra el nombre nuevo", async () => {
    const { client, sent } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe() },
      "PATCH /api/owner/establishment": (body) => ({
        status: 200,
        body: { ...ownerMe().establishment, ...(body as object) },
      }),
    });
    renderRoute("/panel", client);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Bar La Esquina");

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "La Esquina Bar" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("La Esquina Bar");
    expect(screen.getByText("Datos guardados.")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "PATCH")?.body).toEqual({
      name: "La Esquina Bar",
      address: "",
      phone: "",
    });
    // El QR sigue siendo el mismo: la URL pública no cambia (R009, R014)…
    expect(screen.getByRole("link", { name: "http://localhost:5173/l/ABCDEFGHJK" })).toBeInTheDocument();
    // …y la vista previa se vuelve a pedir para mostrar el nombre nuevo impreso.
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/api/owner/establishment/qr.png?v=La%20Esquina%20Bar",
    );
  });

  it("F001_R014 nombre vacío se señala en el campo", async () => {
    const { client } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe() },
      "PATCH /api/owner/establishment": { status: 422, body: { errors: { name: "required" } } },
    });
    renderRoute("/panel", client);
    await screen.findByRole("heading", { level: 1 });

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: " " } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Escribe el nombre de tu establecimiento.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Bar La Esquina");
  });

  it("F001_R019 con el correo sin verificar puede editar el teléfono", async () => {
    const { client, sent } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe({ verified: false }) },
      "PATCH /api/owner/establishment": (body) => ({
        status: 200,
        body: { ...ownerMe().establishment, ...(body as object) },
      }),
    });
    renderRoute("/panel", client);
    await screen.findByRole("heading", { level: 1 });

    fireEvent.change(screen.getByLabelText("Teléfono (opcional)"), { target: { value: "3001234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(sent.some((r) => r.method === "PATCH")).toBe(true));
    expect(await screen.findByText("Datos guardados.")).toBeInTheDocument();
  });

  it("F001_R008 cerrar sesión lleva a /entrar", async () => {
    const { client, sent } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe() },
      "POST /api/auth/logout": { status: 204 },
    });
    const router = renderRoute("/panel", client);
    await screen.findByRole("heading", { level: 1 });

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/entrar");
    expect(sent.some((r) => r.method === "POST" && r.path === "/api/auth/logout")).toBe(true);
  });

  it("F001_R008 si el cierre de sesión falla, avisa y no sale del panel", async () => {
    const { client } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe() },
      "POST /api/auth/logout": { status: 500 },
    });
    const router = renderRoute("/panel", client);
    await screen.findByRole("heading", { level: 1 });

    fireEvent.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo cerrar la sesión");
    expect(router.state.location.pathname).toBe("/panel");
  });

  it("F001_R020 sin sesión o con la sesión caducada el cliente lleva a entrar", async () => {
    const { client, navigate } = fakeApi({
      "GET /api/owner/me": { status: 401, body: { detail: "unauthenticated" } },
    });
    renderRoute("/panel", client);

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/entrar"));
    expect(screen.queryByText("Bar La Esquina")).not.toBeInTheDocument();
    // Ni datos ni avisos engañosos mientras se va a /entrar.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
