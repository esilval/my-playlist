// Elección del proveedor de reproducción (plan D5).
//
// En desarrollo y pruebas, `VITE_PLAYBACK_PROVIDER=fake` usa el proveedor falso. La
// condición se escribe sobre `import.meta.env` tal cual: Vite la sustituye al compilar, y
// en el build de producción la rama del falso queda muerta y su código no se incluye.
import type { PlaybackEvents, PlaybackProvider } from "./types";

export type { PlaybackEvents, PlaybackProvider } from "./types";

export async function createPlaybackProvider(
  events: PlaybackEvents,
  container: HTMLElement,
): Promise<PlaybackProvider> {
  if (import.meta.env.MODE !== "production" && import.meta.env.VITE_PLAYBACK_PROVIDER === "fake") {
    const { createFakeProvider } = await import("./fake");
    return createFakeProvider(events);
  }
  const { createYouTubeProvider } = await import("./youtube");
  return createYouTubeProvider(events, container);
}
