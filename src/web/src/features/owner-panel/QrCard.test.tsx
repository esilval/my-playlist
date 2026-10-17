import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";
import { ownerMe } from "./fixtures";

describe("tarjeta del QR", () => {
  it("F001_R010 QrCard descarga con download=1", async () => {
    const { client } = fakeApi({ "GET /api/owner/me": { status: 200, body: ownerMe() } });
    renderRoute("/panel", client);

    const download = await screen.findByRole("link", { name: "Descargar el QR" });

    expect(download).toHaveAttribute("href", "/api/owner/establishment/qr.png?download=1");
    expect(download).toHaveAttribute("download");
    expect(screen.getByRole("img", { name: "Código QR del establecimiento" })).toHaveAttribute(
      "src",
      "/api/owner/establishment/qr.png?v=Bar%20La%20Esquina",
    );
    expect(screen.getByRole("link", { name: "Imprimir el QR" })).toHaveAttribute("href", "/panel/qr/imprimir");
  });

  it("F001_R018 QrCard sin verificar muestra aviso y botón de reenvío", async () => {
    const { client, sent } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe({ verified: false }) },
      "POST /api/owner/email-verification/resend": { status: 202, body: { status: "check_email" } },
    });
    renderRoute("/panel", client);

    expect(await screen.findByRole("alert")).toHaveTextContent("primero verifica tu correo");
    expect(screen.queryByRole("link", { name: "Descargar el QR" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Imprimir el QR" })).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reenviar el enlace" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Te enviamos un enlace nuevo");
    expect(sent.at(-1)).toMatchObject({ method: "POST", path: "/api/owner/email-verification/resend" });
  });

  it("F001_R027 reenvío limitado muestra que hay que esperar", async () => {
    const { client } = fakeApi({
      "GET /api/owner/me": { status: 200, body: ownerMe({ verified: false }) },
      "POST /api/owner/email-verification/resend": { status: 429, body: { error: "resend_rate_limited" } },
    });
    renderRoute("/panel", client);
    await screen.findByRole("alert");

    fireEvent.click(screen.getByRole("button", { name: "Reenviar el enlace" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Espera una hora");
  });
});
