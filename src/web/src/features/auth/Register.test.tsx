import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";

const POLICY = { status: 200, body: { version: "2026-10", content: "# Política" } };

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function fillValidForm({ waitForPolicy = true } = {}) {
  await screen.findByRole("heading", { name: "Crea tu cuenta" });
  // El botón se activa al llegar la política vigente (D12).
  if (waitForPolicy) await policyLoaded();
  fill("Correo", "dueno@ejemplo.com");
  fill("Contraseña", "contraseña-segura");
  fill("Nombre del establecimiento", "Bar La Esquina");
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
}

async function policyLoaded() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeEnabled());
}

describe("registro", () => {
  it("F001_R003 conserva lo escrito salvo la contraseña y señala cada campo", async () => {
    const { client } = fakeApi({
      "GET /api/public/data-policy": POLICY,
      "POST /api/auth/register": {
        status: 422,
        body: { errors: { email: "invalid_email", password: "password_too_short", establishment_name: "required" } },
      },
    });
    renderRoute("/registro", client);
    await screen.findByRole("heading", { name: "Crea tu cuenta" });
    await policyLoaded();
    fill("Correo", "sin-arroba");
    fill("Contraseña", "1234567");

    submit();

    expect(await screen.findByText("Ese correo no tiene un formato válido.")).toBeInTheDocument();
    expect(screen.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeInTheDocument();
    expect(screen.getByText("Escribe el nombre de tu establecimiento.")).toBeInTheDocument();
    expect(screen.getByLabelText("Correo")).toHaveValue("sin-arroba");
    expect(screen.getByLabelText("Correo")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
  });

  it("F001_R004 casilla de autorización obligatoria", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": POLICY,
      "POST /api/auth/register": { status: 422, body: { errors: { data_authorization: "authorization_required" } } },
    });
    renderRoute("/registro", client);
    await fillValidForm();
    expect(screen.getByRole("checkbox")).not.toBeChecked();

    submit();

    expect(
      await screen.findByText(
        "Para crear la cuenta tienes que aceptar la política de tratamiento de datos.",
      ),
    ).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({ data_authorization: false });
  });

  it("F001_R022 enlace a la política junto a la casilla y envío de policy_version", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": POLICY,
      "POST /api/auth/register": { status: 202, body: { status: "check_email" } },
    });
    renderRoute("/registro", client);
    await fillValidForm();

    const link = screen.getByRole("link", { name: "política de tratamiento de datos" });
    expect(link).toHaveAttribute("href", "/politica-de-datos");
    expect(screen.getByLabelText(/Autorizo el tratamiento de mis datos/)).toBe(screen.getByRole("checkbox"));

    await waitFor(() => expect(sent.some((r) => r.path === "/api/public/data-policy")).toBe(true));
    fireEvent.click(screen.getByRole("checkbox"));
    submit();

    await waitFor(() => expect(sent.some((r) => r.method === "POST")).toBe(true));
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
      data_authorization: true,
      policy_version: "2026-10",
    });
  });

  it("F001_R022 política desfasada pide revisarla y recarga la versión", async () => {
    let version = "2026-10";
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": () => ({ status: 200, body: { version, content: "" } }),
      "POST /api/auth/register": () => {
        version = "2026-11";
        return { status: 422, body: { errors: { policy_version: "outdated" } } };
      },
    });
    renderRoute("/registro", client);
    await fillValidForm();
    fireEvent.click(screen.getByRole("checkbox"));

    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("La política de tratamiento de datos se actualizó");
    expect(screen.getByRole("checkbox")).not.toBeChecked();

    // Se recargó la versión: el siguiente envío lleva la nueva.
    await waitFor(() =>
      expect(sent.filter((r) => r.path === "/api/public/data-policy")).toHaveLength(2),
    );
    fill("Contraseña", "contraseña-segura");
    fireEvent.click(screen.getByRole("checkbox"));
    submit();
    await waitFor(() => expect(sent.filter((r) => r.method === "POST")).toHaveLength(2));
    expect(sent.filter((r) => r.method === "POST").at(-1)?.body).toMatchObject({
      policy_version: "2026-11",
    });
  });

  it("F001_R022 sin la política cargada no se puede enviar", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": { status: 500 },
    });
    renderRoute("/registro", client);
    await fillValidForm({ waitForPolicy: false });

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeDisabled();
  });

  it("un fallo del servidor no se presenta como error del formulario", async () => {
    const { client } = fakeApi({
      "GET /api/public/data-policy": POLICY,
      "POST /api/auth/register": { status: 500 },
    });
    renderRoute("/registro", client);
    await fillValidForm();
    fireEvent.click(screen.getByRole("checkbox"));

    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeEnabled();
  });

  it("F001_R023 tras registrar lleva a revisa-tu-correo sin sesión", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/data-policy": POLICY,
      "POST /api/auth/register": { status: 202, body: { status: "check_email" } },
    });
    const router = renderRoute("/registro", client);
    await fillValidForm();
    fill("Dirección (opcional)", "Calle 1 # 2-3");
    fireEvent.click(screen.getByRole("checkbox"));

    submit();

    expect(await screen.findByRole("heading", { name: "Revisa tu correo" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/registro/revisa-tu-correo");
    expect(sent.find((r) => r.method === "POST")?.body).toMatchObject({
      email: "dueno@ejemplo.com",
      establishment_name: "Bar La Esquina",
      address: "Calle 1 # 2-3",
      phone: null,
    });
  });
});
