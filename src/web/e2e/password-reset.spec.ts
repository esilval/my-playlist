import { expect, test } from "@playwright/test";

import { linkIn, SUBJECTS, waitForMail } from "./helpers/mailpit";
import { loginInUi, registerByApi, uniqueEmail } from "./helpers/owners";

const NEW_PASSWORD = "contraseña-nueva";

async function resetPassword(page: import("@playwright/test").Page, email: string) {
  await page.goto("/recuperar");
  await page.getByLabel("Correo").fill(email);
  await page.getByRole("button", { name: "Enviar enlace" }).click();
  await expect(page.getByRole("status")).toContainText("Si ese correo tiene una cuenta");

  const text = await waitForMail(page.request, email, SUBJECTS.reset);
  await page.goto(linkIn(text, "/restablecer?token="));
  await page.getByLabel("Contraseña nueva").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page.getByRole("heading", { name: "Contraseña cambiada" })).toBeVisible();
}

test("F001_R016 recuperar y entrar con la nueva", async ({ page, request, baseURL }) => {
  const email = uniqueEmail("recupera");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");

  await resetPassword(page, email);
  await loginInUi(page, email, NEW_PASSWORD);

  await expect(page).toHaveURL(/\/panel$/);
});

test("F001_R021 dos contextos, ambos expulsados tras restablecer", async ({ browser, request, baseURL }) => {
  const email = uniqueEmail("dos-navegadores");
  await registerByApi(request, baseURL ?? "", email, "Bar La Esquina");
  const [one, two, three] = [await browser.newContext(), await browser.newContext(), await browser.newContext()];
  const [first, second, recovery] = [await one.newPage(), await two.newPage(), await three.newPage()];
  for (const page of [first, second]) {
    await loginInUi(page, email);
    await expect(page).toHaveURL(/\/panel$/);
  }

  // Un tercer navegador, sin sesión, restablece la contraseña.
  await resetPassword(recovery, email);

  for (const page of [first, second]) {
    await page.goto("/panel");
    await expect(page).toHaveURL(/\/entrar$/);
  }
  await loginInUi(second, email, NEW_PASSWORD);
  await expect(second).toHaveURL(/\/panel$/);
  await Promise.all([one, two, three].map((context) => context.close()));
});
