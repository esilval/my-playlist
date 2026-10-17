// Lee los correos que el trabajador entrega a Mailpit (plan D10) para seguir sus enlaces.
import { expect, type APIRequestContext } from "@playwright/test";

export const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";

interface MailpitSummary {
  ID: string;
  Subject: string;
}

async function messagesTo(request: APIRequestContext, to: string): Promise<MailpitSummary[]> {
  const response = await request.get(`${MAILPIT_URL}/api/v1/search`, {
    params: { query: `to:"${to}"` },
  });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { messages: MailpitSummary[] }).messages;
}

/** Espera el correo con ese asunto y devuelve su texto (el trabajador envía cada ~2 s). */
export async function waitForMail(request: APIRequestContext, to: string, subject: string): Promise<string> {
  let found: MailpitSummary | undefined;
  await expect
    .poll(
      async () => {
        found = (await messagesTo(request, to)).find((m) => m.Subject === subject);
        return found !== undefined;
      },
      { timeout: 15_000, message: `correo «${subject}» a ${to}` },
    )
    .toBe(true);
  const message = await request.get(`${MAILPIT_URL}/api/v1/message/${found?.ID}`);
  return ((await message.json()) as { Text: string }).Text;
}

export function linkIn(text: string, path: string): string {
  const match = new RegExp(`https?://\\S+${path.replace("?", "\\?")}\\S*`).exec(text);
  expect(match, `enlace ${path} en el correo`).not.toBeNull();
  return match?.[0] ?? "";
}

export const SUBJECTS = {
  verify: "Verifica tu correo en MyPlaylist",
  reset: "Recupera tu contraseña de MyPlaylist",
} as const;
