import { expect, test } from "@playwright/test";

import { registerByApi, uniqueEmail, verifyFromMail } from "./helpers/owners";

test("F001_R012 abrir /l/:code muestra el nombre", async ({ page, browser, request, baseURL }) => {
  const email = uniqueEmail("publica");
  await registerByApi(request, baseURL ?? "", email, "Café Ñandú");
  await verifyFromMail(page, email);
  const publicUrl = await page.getByRole("link", { name: /\/l\// }).textContent();
  expect(publicUrl).toMatch(/\/l\/[0-9A-Z]{10}$/);

  // Un móvil cualquiera: sin la sesión del propietario ni cuenta.
  const visitor = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const phone = await visitor.newPage();
  await phone.goto(publicUrl ?? "");

  await expect(phone.getByRole("heading", { level: 1 })).toHaveText("Café Ñandú");
  await expect(phone.locator("form, input")).toHaveCount(0);
  await visitor.close();
});

test("F001_R013 código inexistente", async ({ page }) => {
  await page.goto("/l/ZZZZZZZZZZ");

  // Solo el aviso genérico: ni el código pedido ni datos de ningún establecimiento.
  await expect(page.getByRole("main")).toHaveText(
    "Establecimiento no encontradoRevisa que el enlace o el código QR estén completos.",
  );
});
