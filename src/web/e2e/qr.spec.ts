import { expect, test } from "@playwright/test";

import { loginInUi, registerByApi, uniqueEmail, verifyFromMail } from "./helpers/owners";

test("F001_R011 vista de impresión", async ({ page, request, baseURL }) => {
  // Se cuenta cuántas veces se abre el diálogo de impresión, sin abrirlo de verdad.
  await page.addInitScript(() => {
    (window as unknown as { printed: number }).printed = 0;
    window.print = () => {
      (window as unknown as { printed: number }).printed += 1;
    };
  });
  const email = uniqueEmail("imprimir");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");
  await verifyFromMail(page, email);

  await page.getByRole("link", { name: "Imprimir el QR" }).click();

  await expect(page).toHaveURL(/\/panel\/qr\/imprimir$/);
  const qr = page.getByRole("img", { name: "Código QR de Bar La Esquina" });
  await expect(qr).toBeVisible();
  await expect.poll(() => qr.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1200);
  await expect.poll(() => page.evaluate(() => (window as unknown as { printed: number }).printed)).toBe(1);

  // Al imprimir solo queda el QR (que lleva el nombre): lo demás se oculta.
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("link", { name: "Volver al panel" })).toBeHidden();
  await expect(qr).toBeVisible();
});

test("F001_R018 sin verificar no se puede imprimir el QR", async ({ page, request, baseURL }) => {
  await page.addInitScript(() => {
    window.print = () => {
      throw new Error("no debe imprimirse");
    };
  });
  const email = uniqueEmail("sin-verificar");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");
  await loginInUi(page, email);
  await expect(page).toHaveURL(/\/panel$/);

  await page.goto("/panel/qr/imprimir");

  await expect(page.getByRole("alert")).toContainText("primero verifica tu correo");
  await expect(page.getByRole("img")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reenviar el enlace" })).toBeVisible();
});
