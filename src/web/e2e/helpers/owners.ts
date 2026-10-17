// Preparar propietarios por la API (rápido) para que cada prueba ejercite por la
// interfaz solo lo que comprueba.
import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { linkIn, SUBJECTS, waitForMail } from "./mailpit";

export const PASSWORD = "contraseña-segura";

// Como la SPA: misma cabecera y mismo origen (protección CSRF, plan D9).
function spaHeaders(baseURL: string) {
  return { "X-MyPlaylist-Client": "web", Origin: baseURL };
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@ejemplo.com`;
}

export async function registerByApi(
  request: APIRequestContext,
  baseURL: string,
  email: string,
  name: string,
): Promise<void> {
  const policy = await request.get("/api/public/data-policy");
  const { version } = (await policy.json()) as { version: string };
  const response = await request.post("/api/auth/register", {
    headers: spaHeaders(baseURL),
    data: {
      email,
      password: PASSWORD,
      establishment_name: name,
      data_authorization: true,
      policy_version: version,
    },
  });
  expect(response.status()).toBe(202);
}

/** Abre en la página el enlace de verificación del correo: queda verificado y dentro. */
export async function verifyFromMail(page: Page, email: string): Promise<void> {
  const text = await waitForMail(page.request, email, SUBJECTS.verify);
  await page.goto(linkIn(text, "/verificar?token="));
  await expect(page).toHaveURL(/\/panel$/);
}

export async function loginInUi(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/entrar");
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}
