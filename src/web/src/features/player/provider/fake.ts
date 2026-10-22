// Proveedor de reproducción falso, para desarrollo y pruebas (plan D5).
//
// Simula lo que indica su referencia, sin sonido ni red: así las pruebas e2e no dependen
// de YouTube, de su cuota ni de su publicidad. Nunca llega al build de producción: lo
// carga index.ts solo fuera de producción.
//
//   fake:3s      suena 3 s y termina (también fake:500ms)
//   fake:error   falla al reproducirse
//   fake:silent  no llega a sonar nunca (para el límite de 10 s del reproductor)
//   fake:<otra>  suena el tiempo por defecto (3 s)
import type { PlaybackEvents, PlaybackProvider } from "./types";

const DEFAULT_DURATION_MS = 3000;
// Lo que tarda en «empezar» a sonar una canción, como lo haría un reproductor real.
const START_DELAY_MS = 50;

type Behaviour = { kind: "plays"; durationMs: number } | { kind: "error" } | { kind: "silent" };

export function behaviourOf(trackRef: string): Behaviour {
  const spec = trackRef.startsWith("fake:") ? trackRef.slice("fake:".length) : "";
  if (spec === "error") return { kind: "error" };
  if (spec === "silent") return { kind: "silent" };
  const duration = /^(\d+)(ms|s)$/.exec(spec);
  if (duration) {
    const amount = Number(duration[1]);
    return { kind: "plays", durationMs: duration[2] === "s" ? amount * 1000 : amount };
  }
  return { kind: "plays", durationMs: DEFAULT_DURATION_MS };
}

export function createFakeProvider(events: PlaybackEvents): PlaybackProvider {
  let timers: ReturnType<typeof setTimeout>[] = [];

  function clear() {
    for (const timer of timers) clearTimeout(timer);
    timers = [];
  }

  return {
    // Precargar no cuesta nada en el falso: la reproducción empieza igual de rápido.
    load() {},
    play(trackRef) {
      clear();
      const behaviour = behaviourOf(trackRef);
      if (behaviour.kind === "silent") return;
      if (behaviour.kind === "error") {
        timers.push(setTimeout(() => events.onError(trackRef, "fake_error"), START_DELAY_MS));
        return;
      }
      timers.push(
        setTimeout(() => {
          events.onPlaying(trackRef);
          timers.push(setTimeout(() => events.onEnded(trackRef), behaviour.durationMs));
        }, START_DELAY_MS),
      );
    },
    stop: clear,
    destroy: clear,
  };
}
