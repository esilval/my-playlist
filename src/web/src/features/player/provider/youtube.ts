// Adaptador de YouTube del proveedor de reproducción (plan D5, ADR-0010).
//
// Usa el IFrame Player API oficial (S7: sin bibliotecas no oficiales) con dos instancias
// que se alternan: mientras suena una, la otra tiene precargada la siguiente, y al
// terminar la actual empieza la otra al instante (Q5: menos de 3 s entre canciones).
//
// Precargar es cargar de verdad: `cueVideoById` solo trae la miniatura y no pide el
// vídeo hasta reproducirlo. Por eso la instancia libre carga la siguiente en silencio con
// `loadVideoById`, la pausa en cuanto empieza y vuelve al principio; al tocarle, recupera
// el sonido y sigue.
//
// Es el único sitio que entiende la referencia de una canción de YouTube: `yt:<videoId>`.
// Para C2 y para el reproductor es una cadena opaca.
import type { PlaybackEvents, PlaybackProvider } from "./types";

// Lo mínimo del IFrame Player API que usa el adaptador.
export interface YouTubePlayer {
  loadVideoById(videoId: string): void;
  playVideo(): void;
  pauseVideo(): void;
  stopVideo(): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  mute(): void;
  unMute(): void;
  destroy(): void;
}

export interface YouTubePlayerOptions {
  height: string;
  width: string;
  playerVars: Record<string, number>;
  events: {
    onReady: () => void;
    onStateChange: (event: { data: number }) => void;
    onError: (event: { data: number }) => void;
  };
}

export interface YouTubeApi {
  Player: new (element: HTMLElement, options: YouTubePlayerOptions) => YouTubePlayer;
}

const PLAYING = 1;
const ENDED = 0;

// Códigos de error del IFrame Player API.
export const ERROR_REASONS: Record<number, string> = {
  2: "invalid_video_id",
  5: "html5_error",
  100: "not_found",
  101: "not_embeddable",
  150: "not_embeddable",
};

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

export function videoIdOf(trackRef: string): string | null {
  if (!trackRef.startsWith("yt:")) return null;
  const id = trackRef.slice("yt:".length);
  return VIDEO_ID.test(id) ? id : null;
}

let apiPromise: Promise<YouTubeApi> | null = null;

/**
 * Carga una sola vez el script oficial del IFrame Player API.
 *
 * Si el script no carga (red, bloqueador), la promesa se rechaza y se olvida, para que
 * el siguiente intento lo vuelva a pedir. Si carga pero la API nunca avisa, la promesa
 * queda pendiente: lo cubre el límite de 10 s del reproductor (D5).
 */
export function loadYouTubeApi(): Promise<YouTubeApi> {
  apiPromise ??= new Promise<YouTubeApi>((resolve, reject) => {
    const global = window as unknown as {
      YT?: YouTubeApi;
      onYouTubeIframeAPIReady?: () => void;
    };
    if (global.YT?.Player) {
      resolve(global.YT);
      return;
    }
    // Respeta un manejador que ya estuviera puesto.
    const previous = global.onYouTubeIframeAPIReady;
    global.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (global.YT) resolve(global.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.onerror = () => reject(new Error("youtube_api_unavailable"));
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    apiPromise = null;
    throw error;
  });
  return apiPromise;
}

interface Slot {
  element: HTMLElement;
  player: YouTubePlayer;
  trackRef: string | null;
  /** Cargando en silencio: al empezar a sonar se pausa y vuelve al principio. */
  preloading: boolean;
  /** Motivo si falló mientras estaba precargada: se avisa al reproducirla. */
  failed: string | null;
}

// La instancia libre queda detrás de la activa, invisible pero cargada: un iframe con
// `display: none` no precarga en algunos navegadores. Conserva el tamaño mínimo de
// 200×200 que piden las condiciones del IFrame Player API.
function show(element: HTMLElement, active: boolean): void {
  element.dataset.active = String(active);
  element.style.cssText = active
    ? "position: relative; width: 100%; height: 100%;"
    : "position: absolute; top: 0; left: 0; width: 200px; height: 200px; opacity: 0; " +
      "pointer-events: none; z-index: -1;";
}

export function createYouTubeProvider(
  events: PlaybackEvents,
  container: HTMLElement,
  loadApi: () => Promise<YouTubeApi> = loadYouTubeApi,
): PlaybackProvider {
  let active = 0;
  let destroyed = false;
  // La instancia libre se coloca sobre el contenedor.
  if (!container.style.position) container.style.position = "relative";

  const slots: Promise<Slot[]> = loadApi().then((api) =>
    Promise.all(
      [0, 1].map(
        (index) =>
          new Promise<Slot>((resolve) => {
            const element = document.createElement("div");
            show(element, index === active);
            const host = document.createElement("div");
            element.appendChild(host);
            container.appendChild(element);
            // Los manejadores se llaman después de construir el reproductor, con la
            // instancia ya creada.
            const created: { slot?: Slot } = {};
            const player = new api.Player(host, {
              height: "100%",
              width: "100%",
              playerVars: { autoplay: 0, controls: 0, disablekb: 1, playsinline: 1 },
              events: {
                onReady: () => {
                  if (created.slot) resolve(created.slot);
                },
                onStateChange: ({ data }) => {
                  const { slot } = created;
                  if (!slot || slot.trackRef === null) return;
                  if (index !== active) {
                    if (data === PLAYING && slot.preloading) {
                      slot.preloading = false;
                      slot.player.pauseVideo();
                      slot.player.seekTo(0, true);
                    }
                    return;
                  }
                  if (data === PLAYING) events.onPlaying(slot.trackRef);
                  else if (data === ENDED) events.onEnded(slot.trackRef);
                },
                onError: ({ data }) => {
                  const { slot } = created;
                  if (!slot || slot.trackRef === null) return;
                  const reason = ERROR_REASONS[data] ?? `youtube_error_${data}`;
                  if (index === active) events.onError(slot.trackRef, reason);
                  else slot.failed = reason;
                },
              },
            });
            created.slot = { element, player, trackRef: null, preloading: false, failed: null };
          }),
      ),
    ),
  );

  function withSlots(action: (all: Slot[]) => void): void {
    void slots.then((all) => {
      if (!destroyed) action(all);
    });
  }

  function failLater(trackRef: string, reason: string): void {
    // Como un error del IFrame: llega después de la llamada, nunca dentro de ella.
    queueMicrotask(() => {
      if (!destroyed) events.onError(trackRef, reason);
    });
  }

  return {
    load(trackRef) {
      const videoId = videoIdOf(trackRef);
      if (videoId === null) return;
      withSlots((all) => {
        const free = all[1 - active];
        if (!free || free.trackRef === trackRef) return;
        free.trackRef = trackRef;
        free.failed = null;
        free.preloading = true;
        free.player.mute();
        free.player.loadVideoById(videoId);
      });
    },
    play(trackRef) {
      const videoId = videoIdOf(trackRef);
      if (videoId === null) {
        failLater(trackRef, "invalid_track_ref");
        return;
      }
      withSlots((all) => {
        const current = all[active];
        const free = all[1 - active];
        if (free && free.trackRef === trackRef) {
          // Estaba precargada: se cambia de instancia y empieza al instante.
          current?.player.stopVideo();
          if (current) current.trackRef = null;
          active = 1 - active;
          all.forEach((slot, index) => show(slot.element, index === active));
          if (free.failed !== null) {
            failLater(trackRef, free.failed);
            return;
          }
          // Si aún no había empezado a cargar, sigue sin pausarse.
          free.preloading = false;
          free.player.unMute();
          free.player.playVideo();
          return;
        }
        if (!current) return;
        current.trackRef = trackRef;
        current.failed = null;
        current.preloading = false;
        current.player.unMute();
        current.player.loadVideoById(videoId);
      });
    },
    stop() {
      withSlots((all) => {
        for (const slot of all) {
          slot.player.stopVideo();
          slot.trackRef = null;
          slot.preloading = false;
          slot.failed = null;
        }
      });
    },
    destroy() {
      destroyed = true;
      void slots.then((all) => {
        for (const slot of all) {
          slot.player.destroy();
          slot.element.remove();
        }
      });
    },
  };
}
