// Preparar la sesión de música para las pruebas e2e del reproductor (plan D9).
//
// Las canciones entran en la cola con la herramienta de desarrollo `devtools enqueue`,
// dentro del contenedor de la API: usa el mismo caso de uso que usará B03 y publica
// `queue.changed`. El servidor de desarrollo usa el proveedor falso
// (VITE_PLAYBACK_PROVIDER=fake en el compose), así que las referencias son `fake:…`.
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { expect, type BrowserContext, type Page, type Request } from "@playwright/test";

import { loginInUi, registerByApi, uniqueEmail, verifyFromMail } from "./owners";

const run = promisify(execFile);
const COMPOSE_FILE =
  process.env.E2E_COMPOSE_FILE ?? fileURLToPath(new URL("../../../docker-compose.yml", import.meta.url));

/** Agrega una canción al final de la cola de la sesión abierta del propietario. */
export async function enqueue(email: string, title: string, ref: string): Promise<void> {
  await run("docker", [
    "compose",
    "-f",
    COMPOSE_FILE,
    "exec",
    "-T",
    "api",
    "python",
    "-m",
    "app.sessions.devtools",
    "enqueue",
    "--email",
    email,
    "--title",
    title,
    "--ref",
    ref,
  ]);
}

// Como la SPA: misma cabecera y mismo origen (protección CSRF).
function spaHeaders(baseURL: string) {
  return { "X-MyPlaylist-Client": "web", Origin: baseURL };
}

/**
 * Un propietario con el correo verificado, con la sesión iniciada en `page` y la sesión
 * de música abierta. Devuelve su correo.
 */
export async function ownerWithMusicSession(page: Page, baseURL: string): Promise<string> {
  const email = uniqueEmail("musica");
  await registerByApi(page.request, baseURL, email, "Bar La Esquina");
  await verifyFromMail(page, email);
  const opened = await page.request.post("/api/owner/music-session", { headers: spaHeaders(baseURL) });
  expect(opened.status()).toBe(201);
  return email;
}

/** Otro navegador (contexto) con la sesión iniciada del mismo propietario. */
export async function secondDevice(context: BrowserContext, email: string): Promise<Page> {
  const page = await context.newPage();
  await loginInUi(page, email);
  await expect(page).toHaveURL(/\/panel$/);
  return page;
}

/** Abre el reproductor y lo pone en marcha. */
export async function startPlayer(page: Page): Promise<void> {
  await page.goto("/panel/reproductor");
  await page.getByRole("button", { name: "Poner en marcha" }).click();
}

export const nowPlaying = (page: Page) => page.getByRole("status").filter({ hasText: "Suena:" });

export interface Report {
  type: "started" | "ended" | "failed";
  item_id: string;
  at: number;
}

/** Anota, con su hora, cada informe que el reproductor envía a la API (plan D4). */
export function recordReports(page: Page): Report[] {
  const reports: Report[] = [];
  page.on("request", (request: Request) => {
    if (!request.url().endsWith("/api/owner/music-session/player/events")) return;
    const body = request.postDataJSON() as { type: Report["type"]; item_id: string };
    reports.push({ type: body.type, item_id: body.item_id, at: Date.now() });
  });
  return reports;
}

/** Huecos entre el final (o el fallo) de cada canción y el inicio de la siguiente (Q5). */
export function gaps(reports: Report[]): number[] {
  const result: number[] = [];
  const seen = new Set<string>();
  let finishedAt: number | null = null;
  for (const report of reports) {
    // Un informe reenviado no cuenta dos veces.
    const key = `${report.item_id}:${report.type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (report.type === "ended" || report.type === "failed") finishedAt = report.at;
    else if (finishedAt !== null) {
      result.push(report.at - finishedAt);
      finishedAt = null;
    }
  }
  return result;
}
