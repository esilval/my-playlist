// El cliente que pide canciones desde el QR, de extremo a extremo (feature 003, plan D6,
// D7), contra el compose con el catálogo falso y el proveedor de reproducción falso. Los
// resultados del catálogo falso suenan 3 s en el reproductor falso.
import { expect, test, type Locator } from "@playwright/test";

import {
  clientPhone,
  enqueue,
  nowPlaying,
  ownerWithMusicSession,
  publicUrl,
  recordReports,
  requestSong,
  startPlayer,
} from "./helpers/queue";

// Tiempo real en el móvil del cliente (Q4).
const CLIENT_MS = 1000;

/** Cuándo aparece `locator`; se lanza antes de provocar el cambio, para medir menos de 1 s. */
function whenVisible(locator: Locator, timeout = 30_000): Promise<number> {
  const at = locator.waitFor({ state: "visible", timeout }).then(() => Date.now());
  // Si caduca antes de llegar a esperarla, que no salga como rechazo sin tratar.
  at.catch(() => undefined);
  return at;
}

// Las pruebas con reproductor miden tiempos: en orden, para no competir por el servidor.
test.describe.configure({ mode: "default" });

test("F003_R001 desde la URL del QR se busca y se pide sin registrarse", async ({ page, browser, baseURL }) => {
  await ownerWithMusicSession(page, baseURL ?? "");
  const phone = await clientPhone(browser, await publicUrl(page));

  await expect(phone.getByRole("heading", { level: 1 })).toHaveText("Bar La Esquina");
  // Ni registro ni datos: el único campo es el del buscador, y no lleva a ninguna cuenta.
  await expect(phone.locator("input")).toHaveCount(1);
  await expect(phone.getByRole("link")).toHaveCount(0);

  const title = await requestSong(phone, "salsa", 2);

  await expect(phone.getByText(`Pediste «${title}».`)).toBeVisible();
  await expect(phone.getByRole("list", { name: "Tus canciones pendientes" })).toHaveText(title);
  await expect(phone.getByText("Te quedan 4 de 5.")).toBeVisible();
  // Al volver desde el QR en el mismo navegador, el dispositivo es el mismo (R002).
  await phone.reload();
  await expect(phone.getByText("Te quedan 4 de 5.")).toBeVisible();
  await phone.context().close();
});

test("F003_R005 la canción pedida suena en el reproductor que estaba en espera", async ({
  page,
  browser,
  baseURL,
}) => {
  await ownerWithMusicSession(page, baseURL ?? "");
  const url = await publicUrl(page);
  // El reproductor en marcha, con la cola vacía.
  await startPlayer(page);
  await expect(page.getByText(/Esperando canciones/)).toBeVisible();
  await expect(nowPlaying(page)).toHaveCount(0);
  const phone = await clientPhone(browser, url);

  const title = await requestSong(phone, "cumbia", 1);

  await expect(nowPlaying(page)).toHaveText(`Suena: ${title}`, { timeout: 10_000 });
  await expect(phone.getByText(`Suena: ${title}`)).toBeVisible();
  await phone.context().close();
});

test("F003_R006 dos móviles: cada uno tiene su cupo", async ({ page, browser, baseURL }) => {
  await ownerWithMusicSession(page, baseURL ?? "");
  const url = await publicUrl(page);
  const first = await clientPhone(browser, url);
  const second = await clientPhone(browser, url);

  for (let n = 1; n <= 5; n++) {
    await requestSong(first, "rock", n);
    await expect(first.getByText(`Te quedan ${5 - n} de 5.`)).toBeVisible();
  }
  await requestSong(first, "pop", 1);
  await expect(first.getByRole("alert")).toHaveText(
    "Ya tienes 5 canciones pedidas, el máximo. Recuperarás un cupo cuando empiece a sonar una de las tuyas.",
  );
  await expect(first.getByText("Te quedan 0 de 5.")).toBeVisible();
  // La rechazada no entra: siguen las 5 de antes.
  const mine = first.getByRole("list", { name: "Tus canciones pendientes" }).getByRole("listitem");
  await expect(mine).toHaveText([1, 2, 3, 4, 5].map((n) => `Canción ${n} de rock`));

  // El otro móvil tiene su cupo completo, y no ve las del primero (R010).
  await expect(second.getByText("Te quedan 5 de 5.")).toBeVisible();
  const title = await requestSong(second, "pop", 1);
  await expect(second.getByText(`Pediste «${title}».`)).toBeVisible();
  await expect(second.getByRole("list", { name: "Tus canciones pendientes" })).toHaveText(title);
  await expect(second.getByText("Te quedan 4 de 5.")).toBeVisible();
  await first.context().close();
  await second.context().close();
});

test("F003_R010 al empezar a sonar su canción, el cliente recupera el cupo sin recargar, en menos de 1 s", async ({
  page,
  browser,
  baseURL,
}) => {
  const email = await ownerWithMusicSession(page, baseURL ?? "");
  const url = await publicUrl(page);
  // Suena A, del propietario; la del cliente espera detrás.
  await enqueue(email, "A", "fake:6s");
  const reports = recordReports(page);
  await startPlayer(page);
  await expect(nowPlaying(page)).toHaveText("Suena: A", { timeout: 10_000 });
  const phone = await clientPhone(browser, url);
  const title = await requestSong(phone, "bolero", 1);
  await expect(phone.getByText("Te quedan 4 de 5.")).toBeVisible();
  const startedA = reports.find((report) => report.type === "started");
  expect(startedA).toBeDefined();
  const recoveredAt = whenVisible(phone.getByText("Te quedan 5 de 5."));
  const playingAt = whenVisible(phone.getByText(`Suena: ${title}`));

  // Termina A y empieza la del cliente. El servidor la pasa a sonar al recibir el
  // informe del final de A: desde ahí se mide.
  await expect
    .poll(() => reports.some((report) => report.type === "ended" && report.item_id === startedA?.item_id), {
      timeout: 15_000,
    })
    .toBe(true);
  const endedA = reports.find((report) => report.type === "ended" && report.item_id === startedA?.item_id);
  for (const shownAt of [await recoveredAt, await playingAt]) {
    const elapsed = shownAt - (endedA?.at ?? 0);
    expect(elapsed).toBeGreaterThanOrEqual(0);
    expect(elapsed).toBeLessThan(CLIENT_MS);
  }
  await expect(nowPlaying(page)).toHaveText(`Suena: ${title}`, { timeout: 10_000 });
  await expect(phone.getByRole("list", { name: "Tus canciones pendientes" })).toHaveCount(0);
  await phone.context().close();
});
