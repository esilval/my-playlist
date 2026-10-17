import { expect, test } from "@playwright/test";

import { loginInUi, registerByApi, uniqueEmail } from "./helpers/owners";

test("F001_R005 entrar con contraseña", async ({ page, request, baseURL }) => {
  const email = uniqueEmail("entrar");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");

  await loginInUi(page, email);

  await expect(page).toHaveURL(/\/panel$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Bar La Esquina");
  // Sin verificar entra igual (R019), pero el QR espera a la verificación (R018).
  await expect(page.getByRole("button", { name: "Reenviar el enlace" })).toBeVisible();
});

test("F001_R006 credenciales erróneas dan el mensaje genérico", async ({ page }) => {
  await loginInUi(page, uniqueEmail("nadie"), "no-es-esta");

  await expect(page.getByRole("alert")).toHaveText("Correo o contraseña incorrectos.");
  await expect(page).toHaveURL(/\/entrar$/);
});

test("F001_R008 cerrar sesión pide entrar", async ({ page, request, baseURL }) => {
  const email = uniqueEmail("salir");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");
  await loginInUi(page, email);
  await expect(page).toHaveURL(/\/panel$/);

  await page.getByRole("button", { name: "Cerrar sesión" }).click();

  await expect(page).toHaveURL(/\/entrar$/);
  await page.goto("/panel");
  await expect(page).toHaveURL(/\/entrar$/);
});
