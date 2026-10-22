// @vitest-environment node
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "vite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { behaviourOf, createFakeProvider } from "./fake";

function recorder() {
  return { onPlaying: vi.fn(), onEnded: vi.fn(), onError: vi.fn() };
}

describe("proveedor de reproducción falso", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("F002_R005 el proveedor falso termina tras la duración de su referencia", () => {
    const events = recorder();
    const provider = createFakeProvider(events);

    provider.play("fake:3s");
    vi.advanceTimersByTime(60);
    expect(events.onPlaying).toHaveBeenCalledWith("fake:3s");
    vi.advanceTimersByTime(2900);
    expect(events.onEnded).not.toHaveBeenCalled();
    vi.advanceTimersByTime(200);
    expect(events.onEnded).toHaveBeenCalledWith("fake:3s");

    expect(behaviourOf("fake:500ms")).toEqual({ kind: "plays", durationMs: 500 });
    expect(behaviourOf("fake:A")).toEqual({ kind: "plays", durationMs: 3000 });

    // Detener o reproducir otra cancela la anterior: no se cuela un «terminó» tardío.
    provider.play("fake:1s");
    vi.advanceTimersByTime(60);
    provider.stop();
    vi.advanceTimersByTime(5000);
    expect(events.onEnded).toHaveBeenCalledTimes(1);
  });

  it("F002_R007 el proveedor falso emite error con fake:error", () => {
    const events = recorder();
    const provider = createFakeProvider(events);

    provider.play("fake:error");
    vi.advanceTimersByTime(100);

    expect(events.onError).toHaveBeenCalledWith("fake:error", "fake_error");
    expect(events.onPlaying).not.toHaveBeenCalled();

    // fake:silent no llega a sonar nunca: para el límite de 10 s del reproductor.
    provider.play("fake:silent");
    vi.advanceTimersByTime(60_000);
    expect(events.onPlaying).not.toHaveBeenCalled();
    expect(events.onError).toHaveBeenCalledTimes(1);
  });
});

describe("elección del proveedor en el build", () => {
  const root = fileURLToPath(new URL("../../../..", import.meta.url));
  const entry = fileURLToPath(new URL("./index.ts", import.meta.url));
  let outDir: string;

  beforeEach(() => {
    outDir = mkdtempSync(join(tmpdir(), "myplaylist-provider-"));
    vi.stubEnv("VITE_PLAYBACK_PROVIDER", "fake");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    rmSync(outDir, { recursive: true, force: true });
  });

  async function bundle(mode: "production" | "development"): Promise<string> {
    await build({
      root,
      mode,
      logLevel: "silent",
      configFile: false,
      build: {
        outDir,
        emptyOutDir: true,
        minify: false,
        // La entrada es index.ts y no una página: se conservan sus exportaciones para que
        // el árbol del proveedor no desaparezca entero.
        rollupOptions: { input: entry, preserveEntrySignatures: "exports-only" },
      },
    });
    const assets = join(outDir, "assets");
    return readdirSync(assets)
      .filter((file) => file.endsWith(".js"))
      .map((file) => readFileSync(join(assets, file), "utf8"))
      .join("\n");
  }

  it("el build de producción no incluye el proveedor falso aunque se pida", async () => {
    const production = await bundle("production");
    expect(production).toContain("youtube.com/iframe_api");
    expect(production).not.toContain("fake_error");

    // Control: fuera de producción, el mismo build sí lo incluye.
    const development = await bundle("development");
    expect(development).toContain("fake_error");
  }, 60_000);
});
