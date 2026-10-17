import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";
import { ownerMe, PNG_BYTES } from "./fixtures";

describe("QR imprimible", () => {
  let print: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // jsdom no implementa la impresión ni las URL de objetos.
    print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    URL.createObjectURL = vi.fn(() => "blob:qr");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    print.mockRestore();
  });

  it("F001_R011 PrintQr renderiza solo imagen y nombre y llama a window.print", async () => {
    const { client } = fakeApi({
      "GET /api/owner/establishment/qr.png": { status: 200, body: PNG_BYTES },
      "GET /api/owner/me": { status: 200, body: ownerMe() },
    });
    renderRoute("/panel/qr/imprimir", client);

    const image = await screen.findByRole("img", { name: "Código QR de Bar La Esquina" });
    expect(image).toHaveAttribute("src", "blob:qr");
    expect(print).not.toHaveBeenCalled();

    fireEvent.load(image);

    expect(print).toHaveBeenCalledOnce();
    // En la hoja solo está el QR (el PNG lleva el nombre); el resto no se imprime.
    const sheet = screen.getByRole("main");
    expect(sheet).toHaveClass("print-sheet");
    const printable = [...sheet.children].filter((child) => !child.classList.contains("no-print"));
    expect(printable).toEqual([image]);
  });

  it("F001_R018 PrintQr ante 403 muestra el aviso y no llama a window.print", async () => {
    const { client } = fakeApi({
      "GET /api/owner/establishment/qr.png": { status: 403, body: { error: "email_not_verified" } },
      "GET /api/owner/me": { status: 200, body: ownerMe({ verified: false }) },
    });
    renderRoute("/panel/qr/imprimir", client);

    expect(await screen.findByRole("alert")).toHaveTextContent("primero verifica tu correo");
    expect(screen.getByRole("button", { name: "Reenviar el enlace" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(print).not.toHaveBeenCalled();
  });
});
