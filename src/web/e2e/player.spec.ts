// Reproductor del local de extremo a extremo (feature 002, plan D3–D8, D11), contra el
// compose con el proveedor falso. Las canciones entran con `devtools enqueue`.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { linkIn, SUBJECTS, waitForMail } from "./helpers/mailpit";
import { loginInUi } from "./helpers/owners";
import {
  enqueue,
  gaps,
  nowPlaying,
  ownerWithMusicSession,
  recordReports,
  secondDevice,
  startPlayer,
} from "./helpers/queue";

// Música sin silencios (Q5) y tiempo real en el panel (Q4). Los «menos de 3 s» se
// comprueban con el tiempo límite de la espera, que empieza justo después de provocar el
// cambio.
const GAP_MS = 3000;
const PANEL_MS = 1000;

const SUPERSEDED = "La música sigue en otro dispositivo.";
const NO_SESSION = /No hay ninguna sesión de música abierta/;

/**
 * Cuándo aparece `locator`. Se lanza antes de provocar el cambio: espera desde el propio
 * navegador, sin el sondeo espaciado de `expect`, así que sirve para medir menos de 1 s.
 */
function whenVisible(locator: Locator, timeout = 30_000): Promise<number> {
  return locator.waitFor({ state: "visible", timeout }).then(() => Date.now());
}

// Las pruebas de este archivo miden tiempos: van en orden, en un solo proceso, para no
// competir entre sí por el servidor de desarrollo.
test.describe.configure({ mode: "default" });

const panelNowPlaying = (panel: Page, title: string) =>
  panel.getByRole("region", { name: "Sesión de música" }).getByText(title, { exact: true });

test("F002_R005 A, B y C suenan en orden con huecos de menos de 3 s", async ({ page, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:1500ms");
  await enqueue(email, "B", "fake:1500ms");
  await enqueue(email, "C", "fake:1500ms");
  const reports = recordReports(page);

  await startPlayer(page);

  for (const title of ["A", "B", "C"]) {
    await expect(nowPlaying(page)).toHaveText(`Suena: ${title}`, { timeout: 10_000 });
  }
  await expect.poll(() => reports.filter((report) => report.type === "started").length).toBe(3);
  const measured = gaps(reports);
  expect(measured).toHaveLength(2);
  for (const gap of measured) expect(gap).toBeLessThan(GAP_MS);
});

test("F002_R007 una canción que falla se salta en menos de 3 s y el panel avisa en menos de 1 s", async ({
  page,
  context,
  baseURL,
}) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:1s");
  await enqueue(email, "Canción rota", "fake:error");
  await enqueue(email, "C", "fake:30s");
  const panel = await context.newPage();
  await panel.goto("/panel");
  await expect(panel.getByText("La sesión de música está abierta.")).toBeVisible();
  const reports = recordReports(page);
  const noticeAt = whenVisible(panel.getByText("No se pudo reproducir «Canción rota»; se saltó."));

  await startPlayer(page);

  await expect(nowPlaying(page)).toHaveText("Suena: C", { timeout: 10_000 });
  const failed = reports.find((report) => report.type === "failed");
  expect(failed).toBeDefined();
  expect((await noticeAt) - (failed?.at ?? 0)).toBeLessThan(PANEL_MS);
  // De su fallo al inicio de C (la que falla nunca llega a empezar).
  await expect.poll(() => reports.filter((report) => report.type === "started").length).toBe(2);
  const startedC = reports.filter((report) => report.type === "started")[1]?.at ?? Infinity;
  expect(startedC - (failed?.at ?? 0)).toBeLessThan(GAP_MS);
  // Y desde que terminó A, como dice el criterio.
  const endedA = reports.find((report) => report.type === "ended");
  expect(startedC - (endedA?.at ?? 0)).toBeLessThan(GAP_MS);
});

test("F002_R008 en espera, la canción que entra suena en menos de 3 s", async ({ page, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await startPlayer(page);
  await expect(page.getByText(/Esperando canciones/)).toBeVisible();
  await page.waitForTimeout(500);
  await expect(nowPlaying(page)).toHaveCount(0);

  // Desde antes de encolar: cota superior, que incluye lo que tarda la herramienta.
  const entered = Date.now();
  const playingAt = whenVisible(nowPlaying(page));
  await enqueue(email, "D", "fake:30s");

  await expect(nowPlaying(page)).toHaveText("Suena: D");
  expect((await playingAt) - entered).toBeLessThan(GAP_MS);
});

test("F002_R010 dos contextos: el primero se detiene en menos de 3 s y lo indica", async ({
  page,
  browser,
  baseURL,
}) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:60s");
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  const tabletContext = await browser.newContext();
  const tablet = await secondDevice(tabletContext, email);
  await startPlayer(tablet);

  await expect(page.getByText(SUPERSEDED)).toBeVisible({ timeout: GAP_MS });
  await expect(nowPlaying(tablet)).toHaveText("Suena: A");
  await tabletContext.close();
});

test("F002_R011 cerrar la sesión detiene la música en menos de 3 s", async ({ page, context, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:60s");
  await enqueue(email, "B", "fake:60s");
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");
  const panel = await context.newPage();
  await panel.goto("/panel");

  await panel.getByRole("button", { name: "Cerrar la sesión de música" }).click();

  await expect(page.getByText(NO_SESSION)).toBeVisible({ timeout: GAP_MS });
  await expect(nowPlaying(page)).toHaveCount(0);
  await expect(panel.getByText("La sesión de música está cerrada.")).toBeVisible();
});

test("F002_R011 cerrar durante un corte detiene al reconectar", async ({ page, context, browser, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:60s");
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  const otherContext = await browser.newContext();
  const panel = await secondDevice(otherContext, email);
  await context.setOffline(true);
  await panel.getByRole("button", { name: "Cerrar la sesión de música" }).click();
  await expect(panel.getByText("La sesión de música está cerrada.")).toBeVisible();
  // Sin conexión (tampoco el tiempo real), el reproductor aún no se ha enterado.
  await page.waitForTimeout(1000);
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  await context.setOffline(false);

  await expect(page.getByText(NO_SESSION)).toBeVisible({ timeout: GAP_MS });
  await otherContext.close();
});

test("F002_R012 un corte durante A sigue con B al terminar A", async ({ page, context, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:4s");
  await enqueue(email, "B", "fake:60s");
  const reports = recordReports(page);
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");
  await expect.poll(() => reports.some((report) => report.type === "started")).toBe(true);

  // Se corta y vuelve antes de que termine A.
  await context.setOffline(true);
  await page.waitForTimeout(1000);
  await context.setOffline(false);
  // A siguió sonando durante el corte y sigue al volver.
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  await expect(nowPlaying(page)).toHaveText("Suena: B", { timeout: 10_000 });
  const [gap] = gaps(reports);
  expect(gap).toBeLessThan(GAP_MS);
  // A no se volvió a reproducir: un solo started suyo.
  const startedA = reports.filter((report) => report.type === "started" && report.item_id === reports[0]?.item_id);
  expect(startedA).toHaveLength(1);
});

test("F002_R012 un corte al terminar A sigue con B al reconectar", async ({ page, context, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:2s");
  await enqueue(email, "B", "fake:60s");
  const reports = recordReports(page);
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");
  await expect.poll(() => reports.some((report) => report.type === "started")).toBe(true);

  // A termina sin conexión: B no empieza.
  await context.setOffline(true);
  await expect(page.getByText("Pasando a la siguiente canción…")).toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(1000);
  await expect(nowPlaying(page)).toHaveCount(0);

  await context.setOffline(false);

  await expect(nowPlaying(page)).toHaveText("Suena: B", { timeout: GAP_MS });
  const startedA = reports.filter((report) => report.type === "started" && report.item_id === reports[0]?.item_id);
  expect(startedA).toHaveLength(1);
});

test("F002_R012 cambio a otro reproductor durante un corte: el primero se detiene al reconectar", async ({
  page,
  context,
  browser,
  baseURL,
}) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", "fake:60s");
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  await context.setOffline(true);
  const tabletContext = await browser.newContext();
  const tablet = await secondDevice(tabletContext, email);
  await startPlayer(tablet);
  await expect(nowPlaying(tablet)).toHaveText("Suena: A");
  // Sin conexión, el portátil no recibió el player.claimed: sigue sonando.
  await page.waitForTimeout(1000);
  await expect(nowPlaying(page)).toHaveText("Suena: A");

  await context.setOffline(false);

  await expect(page.getByText(SUPERSEDED)).toBeVisible({ timeout: GAP_MS });
  await expect(nowPlaying(tablet)).toHaveText("Suena: A");
  await tabletContext.close();
});

test("F002_R015 restablecer la contraseña: A termina, pide entrar y tras entrar suena B y no A", async ({
  page,
  browser,
  baseURL,
}) => {
  // A dura más que el primer latido (a los 15 s): el 401 llega seguro a mitad de A.
  test.setTimeout(120_000);
  const A_MS = 40_000;
  const NEW_PASSWORD = "contraseña-nueva";
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "A", `fake:${A_MS}ms`);
  await enqueue(email, "B", "fake:60s");
  const reports = recordReports(page);
  const unauthorized = page.waitForResponse(
    (response) => response.url().endsWith("/player/heartbeat") && response.status() === 401,
    { timeout: 60_000 },
  );
  // Si caduca antes de llegar a esperarla, que no salga como rechazo sin tratar.
  unauthorized.catch(() => undefined);
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A");
  await expect.poll(() => reports.some((report) => report.type === "started")).toBe(true);
  const startedA = reports.find((report) => report.type === "started")?.at ?? 0;

  // Desde otro equipo, el propietario restablece la contraseña: se cierran todas sus
  // sesiones iniciadas, también la del reproductor.
  const otherContext = await browser.newContext();
  const recovery = await otherContext.newPage();
  await recovery.goto("/recuperar");
  await recovery.getByLabel("Correo").fill(email);
  await recovery.getByRole("button", { name: "Enviar enlace" }).click();
  const text = await waitForMail(recovery.request, email, SUBJECTS.reset);
  await recovery.goto(linkIn(text, "/restablecer?token="));
  await recovery.getByLabel("Contraseña nueva").fill(NEW_PASSWORD);
  await recovery.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(recovery.getByRole("heading", { name: "Contraseña cambiada" })).toBeVisible();

  // El reproductor ya sabe que perdió la sesión (el latido recibió el 401)…
  await unauthorized;
  // …y aun así A sigue sonando, sin el aviso ni redirigir.
  await page.waitForTimeout(500);
  await expect(nowPlaying(page)).toHaveText("Suena: A");
  await expect(page.getByText(/Tu sesión se cerró/)).toHaveCount(0);

  // A suena hasta el final: el aviso sale cuando termina, no antes.
  await expect(page.getByText(/Tu sesión se cerró/)).toBeVisible({ timeout: A_MS });
  expect(Date.now() - startedA).toBeGreaterThan(A_MS - 1000);
  await expect(page).toHaveURL(/\/panel\/reproductor$/);
  // B no empezó.
  expect(reports.filter((report) => report.type === "started")).toHaveLength(1);
  await expect(nowPlaying(page)).toHaveCount(0);

  // Vuelve a entrar en el equipo del reproductor y lo pone en marcha.
  await loginInUi(page, email, NEW_PASSWORD);
  await expect(page).toHaveURL(/\/panel$/);
  await startPlayer(page);

  await expect(nowPlaying(page)).toHaveText("Suena: B", { timeout: GAP_MS });
  // Solo empezó B: A no volvió a sonar.
  await expect.poll(() => reports.filter((report) => report.type === "started").length).toBe(2);
  await page.waitForTimeout(500);
  expect(reports.filter((report) => report.type === "started")).toHaveLength(2);
  await otherContext.close();
});

test("F002_R014 el panel muestra lo que suena en menos de 1 s", async ({ page, context, baseURL }) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  await enqueue(email, "Canción A", "fake:2s");
  await enqueue(email, "Canción B", "fake:60s");
  const panel = await context.newPage();
  await panel.goto("/panel");
  await expect(panel.getByText("No hay ningún reproductor activo.", { exact: false })).toBeVisible();
  const reports = recordReports(page);
  const shownAt = whenVisible(panelNowPlaying(panel, "Canción B"));

  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: Canción B", { timeout: 10_000 });
  await expect.poll(() => reports.filter((report) => report.type === "started").length).toBe(2);
  // B pasa a sonar en el servidor al recibir el ended de A: desde ahí se mide.
  const endedA = reports.find((report) => report.type === "ended")?.at ?? 0;

  expect((await shownAt) - endedA).toBeLessThan(PANEL_MS);
  await expect(panel.getByText(/El reproductor está en marcha/)).toBeVisible();
});
