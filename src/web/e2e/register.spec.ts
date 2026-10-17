import { expect, test } from "@playwright/test";

import { linkIn, SUBJECTS, waitForMail } from "./helpers/mailpit";
import { PASSWORD, uniqueEmail } from "./helpers/owners";

test("F001_R023 registro muestra revisa tu correo sin sesión", async ({ page }) => {
  const email = uniqueEmail("registro");
  await page.goto("/registro");
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByLabel("Nombre del establecimiento").fill("Bar La Esquina");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page).toHaveURL(/\/registro\/revisa-tu-correo$/);
  await expect(page.getByRole("heading", { name: "Revisa tu correo" })).toBeVisible();
  // Sin sesión: el panel manda a entrar.
  await page.goto("/panel");
  await expect(page).toHaveURL(/\/entrar$/);
});

test("F001_R025 enlace del correo verifica y deja en el panel", async ({ page, request, baseURL }) => {
  const email = uniqueEmail("verifica");
  await page.goto("/registro");
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByLabel("Nombre del establecimiento").fill("Café Ñandú");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Revisa tu correo" })).toBeVisible();

  const text = await waitForMail(request, email, SUBJECTS.verify);
  const link = linkIn(text, "/verificar?token=");
  expect(new URL(link).origin).toBe(baseURL);
  await page.goto(link);

  await expect(page).toHaveURL(/\/panel$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Café Ñandú");
  // Verificado: el QR ya se puede descargar.
  await expect(page.getByRole("link", { name: "Descargar el QR" })).toBeVisible();

  // Reabrir el enlace ya usado no abre otra sesión: dice que ya está verificado.
  await page.context().clearCookies();
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Tu correo ya está verificado" })).toBeVisible();
});

test("F001_R022 la política se abre desde el registro", async ({ page, context }) => {
  await page.goto("/registro");

  const [policy] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("link", { name: "política de tratamiento de datos" }).click(),
  ]);

  await expect(policy).toHaveURL(/\/politica-de-datos$/);
  await expect(policy.getByRole("heading", { level: 1 })).toHaveText("Política de tratamiento de datos");
  await expect(policy.getByText(/Versión/)).toBeVisible();
});
