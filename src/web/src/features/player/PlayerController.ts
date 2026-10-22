// Lógica del reproductor del local (plan D3, D4, D5, D8), sin React.
//
// El reproductor no decide el orden de la cola: informa de que una canción empezó,
// terminó o falló, y reproduce la que la API dice que suena ahora (D4). Cada informe se
// guarda antes de enviarlo y se reenvía en orden tras un corte; mientras tanto no empieza
// canciones nuevas (R012). Con la cola vacía espera, y pide avanzar cuando entra una
// canción (R008). Se detiene si otro reproductor toma el control (R010) o si se cierra la
// sesión de música (R011). Si se cierra la sesión iniciada del equipo (un 401), deja
// terminar la canción, guarda su informe y pide volver a entrar (R015, D11).
import type { ApiClient } from "../../api/client";
import { errorCode } from "../../api/errors";
import type { components } from "../../api/schema";
import type { MusicSessionState, SessionEvent } from "../../realtime/client";
import type { PendingReports, PlayerReport } from "./pendingReports";
import type { PlaybackEvents, PlaybackProvider } from "./provider";

type Track = components["schemas"]["TrackOut"];
type Progress = Pick<components["schemas"]["ProgressOut"], "current" | "next">;

export interface PlayerTiming {
  /** Sin empezar a sonar en este tiempo, la canción se da por fallida (D5, R007). */
  failTimeoutMs: number;
  /** Latido: mantiene el reproductor activo y trae la versión de la sesión (D3). */
  heartbeatMs: number;
  /** Reintento de los informes pendientes sin conexión (R012). */
  retryMs: number;
}

export const DEFAULT_TIMING: PlayerTiming = {
  failTimeoutMs: 10_000,
  heartbeatMs: 15_000,
  retryMs: 2_000,
};

// El motivo con que se informa una canción que no llegó a sonar.
export const TIMEOUT_REASON = "timeout";

export type PlayerStatus =
  | "loading" // comprobando si hay sesión de música abierta
  | "ready" // se puede poner en marcha
  | "starting"
  | "playing"
  | "advancing" // terminó una canción y espera a saber cuál sigue
  | "waiting" // la cola no tiene pendientes (R008)
  | "no_session" // sin sesión de música abierta, o se cerró (R009, R011)
  | "superseded" // otro reproductor tomó el control (R010)
  | "login_required"; // la sesión iniciada se cerró: hay que volver a entrar (R015)

export interface PlayerView {
  status: PlayerStatus;
  /** La canción que suena, con `playing`. */
  title?: string;
  /** No llegan las peticiones a la API. */
  offline: boolean;
}

export interface PlayerControllerOptions {
  api: ApiClient;
  createProvider: (events: PlaybackEvents) => Promise<PlaybackProvider>;
  reports: PendingReports;
  onChange: (view: PlayerView) => void;
  /** Al abrir sin sesión iniciada, como el resto del panel (D8, R013). */
  goToLogin: () => void;
  timing?: Partial<PlayerTiming>;
}

export interface PlayerController {
  /** Al abrir el reproductor: ¿hay sesión de música abierta? (R009) */
  check(): Promise<void>;
  /** «Poner en marcha» (R004, R010). */
  start(): Promise<void>;
  /** Eventos de la sala del establecimiento (D6). */
  onEvent(event: SessionEvent): void;
  /** Estado completo de la sesión: al conectar o tras un salto de versión (D6). */
  onState(state: MusicSessionState): void;
  /** Quién avisa de la versión que trae el latido (el cliente de tiempo real). */
  setVersionObserver(observe: ((version: number) => void) | null): void;
  destroy(): void;
}

type Outcome = "ok" | "offline" | "stopped" | "login";

export function createPlayerController(options: PlayerControllerOptions): PlayerController {
  const { api, reports, onChange } = options;
  const timing = { ...DEFAULT_TIMING, ...options.timing };

  let view: PlayerView = { status: "loading", offline: false };
  let provider: PlaybackProvider | null = null;
  // La época de este reproductor, mientras está en marcha.
  let epoch: number | null = null;
  let current: Track | null = null;
  // La que se precargó por última vez (D5).
  let preloaded: string | null = null;
  let startedReported = false;
  let flushing = false;
  let destroyed = false;
  // Entró algo en la cola (o hubo que pedir el estado) cuando no se estaba en espera, o
  // falló la petición de avanzar: al quedar en espera se pide avanzar (R008).
  let advanceWanted = false;
  // La API respondió 401: la canción que suena termina, pero no empieza otra (R015).
  let loggedOut = false;
  let observeVersion: ((version: number) => void) | null = null;
  let failTimer: ReturnType<typeof setTimeout> | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  function set(patch: Partial<PlayerView>): void {
    if (destroyed) return;
    view = { ...view, ...patch };
    if (view.status !== "playing") delete view.title;
    onChange(view);
  }

  const active = () => epoch !== null && !destroyed;

  function clearFail(): void {
    if (failTimer !== null) clearTimeout(failTimer);
    failTimer = null;
  }

  function clearTimers(): void {
    clearFail();
    if (retryTimer !== null) clearTimeout(retryTimer);
    if (heartbeatTimer !== null) clearInterval(heartbeatTimer);
    retryTimer = null;
    heartbeatTimer = null;
  }

  /** Detiene la música y deja de actuar como reproductor (R010, R011). */
  function halt(status: "no_session" | "superseded"): void {
    epoch = null;
    current = null;
    advanceWanted = false;
    loggedOut = false;
    preloaded = null;
    clearTimers();
    provider?.stop();
    // Los informes pendientes eran de esta época: ya no se pueden aplicar.
    reports.clear();
    set({ status, offline: false });
  }

  /**
   * Sin sesión iniciada no se puede seguir, pero la canción que suena termina (R015). Al
   * terminar se para, conservando los informes guardados: se entregarán, con su época, al
   * volver a ponerlo en marcha tras iniciar sesión (D11).
   */
  function loginLost(): void {
    loggedOut = true;
    if (view.offline) set({ offline: false });
    if (retryTimer !== null) clearTimeout(retryTimer);
    if (heartbeatTimer !== null) clearInterval(heartbeatTimer);
    retryTimer = null;
    heartbeatTimer = null;
    if (current === null) requireLogin();
  }

  function requireLogin(): void {
    epoch = null;
    current = null;
    advanceWanted = false;
    loggedOut = false;
    preloaded = null;
    clearTimers();
    provider?.stop();
    set({ status: "login_required", offline: false });
  }

  /** Un 409 de la API: la sesión se cerró u otro reproductor tomó el control. */
  function conflict(body: unknown): void {
    halt(errorCode(body) === "player_superseded" ? "superseded" : "no_session");
  }

  /** Reproduce lo que dice la API (D4): nunca una canción que decidió el cliente. */
  function follow(progress: Progress): void {
    if (!active() || !provider) return;
    const next = progress.current;
    if (next === null) {
      if (current !== null) provider.stop();
      current = null;
      clearFail();
      set({ status: "waiting" });
      if (advanceWanted) void advance();
      return;
    }
    if (current?.item_id !== next.item_id) {
      current = next;
      startedReported = false;
      provider.play(next.track_ref);
      clearFail();
      const item = next.item_id;
      failTimer = setTimeout(() => {
        if (current?.item_id === item && !startedReported) fail(next.track_ref, TIMEOUT_REASON);
      }, timing.failTimeoutMs);
      set({ status: "playing", title: next.title });
    }
    // Cada respuesta trae la siguiente: se precarga solo si cambió.
    if (progress.next && progress.next.item_id !== preloaded) {
      preloaded = progress.next.item_id;
      provider.load(progress.next.track_ref);
    }
  }

  function report(type: PlayerReport["type"], item: Track, reason?: string): void {
    if (epoch === null) return;
    reports.push({ epoch, item_id: item.item_id, type, ...(reason ? { reason } : {}) });
    if (loggedOut) {
      // Se guarda sin enviarlo. Si la canción terminó, el reproductor se para.
      if (current === null) requireLogin();
      return;
    }
    void flush();
  }

  function scheduleRetry(): void {
    if (retryTimer !== null || destroyed) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void flush().then(() => {
        if (advanceWanted && view.status === "waiting") void advance();
      });
    }, timing.retryMs);
  }

  /**
   * Entrega los informes pendientes, en orden (R012). Solo sigue la respuesta del
   * último: la de uno anterior (por ejemplo, el `started` de una canción que ya terminó)
   * ya no dice lo que suena.
   */
  async function deliver(): Promise<{ outcome: Outcome; progress: Progress | null }> {
    let progress: Progress | null = null;
    const sent = epoch;
    for (let pending = reports.all()[0]; pending; pending = reports.all()[0]) {
      let response;
      try {
        response = await api.POST("/api/owner/music-session/player/events", { body: pending });
      } catch {
        return { outcome: epoch === sent ? "offline" : "stopped", progress: null };
      }
      // Entretanto se detuvo o se volvió a poner en marcha: los informes que quedan son de
      // la puesta en marcha nueva, y esta respuesta ya no dice nada de ellos.
      if (destroyed || epoch !== sent) return { outcome: "stopped", progress: null };
      const { data, error, response: raw } = response;
      if (data) {
        reports.shift();
        progress = data;
        continue;
      }
      if (raw.status === 401) return { outcome: "login", progress: null };
      if (raw.status === 409) {
        if (pending.epoch !== epoch) {
          // De una puesta en marcha anterior: no dice nada del reproductor actual.
          reports.shift();
          continue;
        }
        conflict(error);
        return { outcome: "stopped", progress: null };
      }
      if (raw.status === 404 || raw.status === 422) {
        // La canción no es de esta sesión, o el informe no es válido: no se aplicará nunca.
        reports.shift();
        continue;
      }
      return { outcome: "offline", progress: null };
    }
    return { outcome: "ok", progress };
  }

  async function flush(): Promise<void> {
    if (flushing || !active() || loggedOut) return;
    flushing = true;
    try {
      const { outcome, progress } = await deliver();
      if (outcome === "login") {
        loginLost();
        return;
      }
      if (outcome === "offline") {
        set({ offline: true });
        scheduleRetry();
        return;
      }
      if (outcome === "ok") {
        if (view.offline) set({ offline: false });
        if (progress) follow(progress);
        else if (current === null && view.status === "advancing") {
          // Ningún informe se aplicó (por ejemplo, la canción ya no es de la sesión): se
          // pregunta qué toca.
          set({ status: "waiting" });
          void advance();
        }
      }
    } finally {
      flushing = false;
    }
    // Llegó otro informe mientras se entregaban.
    if (reports.all().length > 0 && active() && !view.offline) void flush();
  }

  function fail(trackRef: string, reason: string): void {
    if (!current || current.track_ref !== trackRef) return;
    const item = current;
    clearFail();
    provider?.stop();
    current = null;
    set({ status: "advancing" });
    report("failed", item, reason);
  }

  const events: PlaybackEvents = {
    onPlaying(trackRef) {
      // Puede llegar repetido (tras una pausa o publicidad) o tarde, de otra canción.
      if (!current || current.track_ref !== trackRef || startedReported) return;
      startedReported = true;
      clearFail();
      report("started", current);
    },
    onEnded(trackRef) {
      if (!current || current.track_ref !== trackRef) return;
      const item = current;
      clearFail();
      current = null;
      set({ status: "advancing" });
      report("ended", item);
    },
    onError(trackRef, reason) {
      fail(trackRef, reason);
    },
  };

  async function heartbeat(): Promise<void> {
    const sent = epoch;
    if (sent === null || loggedOut) return;
    try {
      const { data, error, response } = await api.POST(
        "/api/owner/music-session/player/heartbeat",
        { body: { epoch: sent } },
      );
      // La respuesta de una puesta en marcha anterior ya no cuenta.
      if (!active() || epoch !== sent) return;
      if (data) {
        if (view.offline) set({ offline: false });
        observeVersion?.(data.version);
        if (reports.all().length > 0) void flush();
        if (advanceWanted && view.status === "waiting") void advance();
      } else if (response.status === 409) {
        conflict(error);
      } else if (response.status === 401) {
        loginLost();
      }
    } catch {
      if (epoch === sent) set({ offline: true });
    }
  }

  /** En espera, pide empezar la canción que entró (R008, D4). */
  async function advance(): Promise<void> {
    const sent = epoch;
    if (!active() || sent === null || loggedOut) return;
    if (view.status !== "waiting") {
      // Suena algo o se espera la respuesta de un informe: se pide al quedar en espera.
      advanceWanted = true;
      return;
    }
    advanceWanted = false;
    try {
      const { data, error, response } = await api.POST("/api/owner/music-session/player/advance", {
        body: { epoch: sent },
      });
      if (!active() || epoch !== sent) return;
      if (data) {
        if (view.offline) set({ offline: false });
        follow(data);
      } else if (response.status === 409) conflict(error);
      else if (response.status === 401) loginLost();
      else {
        advanceWanted = true;
        scheduleRetry();
      }
    } catch {
      if (epoch !== sent) return;
      advanceWanted = true;
      set({ offline: true });
      scheduleRetry();
    }
  }

  /**
   * Antes de poner en marcha, entrega los informes que quedaron de antes (al recargar la
   * pestaña). Si ya no se pueden aplicar, se descartan (D11).
   */
  async function deliverLeftovers(): Promise<"ok" | "offline" | "login"> {
    for (let pending = reports.all()[0]; pending; pending = reports.all()[0]) {
      try {
        const { data, response } = await api.POST("/api/owner/music-session/player/events", {
          body: pending,
        });
        if (data || response.status === 404 || response.status === 422) {
          reports.shift();
          continue;
        }
        if (response.status === 409) {
          // Otro reproductor tomó el control o se cerró la sesión de música: ya no se
          // aplicarán, y la puesta en marcha sigue como en R010 (D11).
          reports.clear();
          return "ok";
        }
        // Siguen guardados para cuando haya sesión iniciada (R015).
        if (response.status === 401) return "login";
      } catch {
        // Sin conexión: se queda para el próximo intento.
      }
      return "offline";
    }
    return "ok";
  }

  return {
    async check() {
      try {
        const { data, response } = await api.GET("/api/owner/music-session");
        if (view.status !== "loading") return;
        // Aún no suena nada: se va a entrar, como el resto del panel (D8).
        if (response.status === 401) options.goToLogin();
        else set({ status: data?.status === "closed" ? "no_session" : "ready" });
      } catch {
        if (view.status === "loading") set({ status: "ready", offline: true });
      }
    },

    async start() {
      if (destroyed || view.status === "starting") return;
      set({ status: "starting" });
      advanceWanted = false;
      try {
        provider ??= await options.createProvider(events);
      } catch {
        // No se pudo cargar el reproductor (por ejemplo, el script de YouTube).
        set({ status: "ready", offline: true });
        return;
      }
      // Sin entregar antes lo que quedó guardado, la canción que ya terminó volvería a
      // empezar: se espera a poder entregarlo (D11).
      const leftovers = await deliverLeftovers();
      if (leftovers !== "ok") {
        set(leftovers === "login" ? { status: "login_required", offline: false } : { status: "ready", offline: true });
        return;
      }
      let claim;
      try {
        claim = await api.POST("/api/owner/music-session/player");
      } catch {
        set({ status: "ready", offline: true });
        return;
      }
      if (destroyed) return;
      const { data, response } = claim;
      if (!data) {
        const status =
          response.status === 409 ? "no_session" : response.status === 401 ? "login_required" : "ready";
        set({ status, offline: false });
        return;
      }
      epoch = data.epoch;
      current = null;
      preloaded = null;
      // Por si algo quedó de otra época: ya no se aplicará (D11).
      reports.clear();
      set({ offline: false });
      if (heartbeatTimer !== null) clearInterval(heartbeatTimer);
      heartbeatTimer = setInterval(() => void heartbeat(), timing.heartbeatMs);
      follow(data);
    },

    onEvent(event) {
      if (!active()) {
        if (event.type === "session.opened" && view.status === "no_session") set({ status: "ready" });
        // Entró una canción mientras se pone en marcha: si el claim llega con la cola
        // vacía, se pide avanzar al quedar en espera (R008).
        if (event.type === "queue.changed" && view.status === "starting") advanceWanted = true;
        return;
      }
      if (event.type === "session.closed") halt("no_session");
      else if (event.type === "player.claimed") {
        // El aviso de la propia puesta en marcha lleva la época de este reproductor.
        if (typeof event.epoch === "number" && epoch !== null && event.epoch > epoch) {
          halt("superseded");
        }
      } else if (event.type === "queue.changed") void advance();
    },

    onState(state) {
      if (!active()) {
        if (state.status === "open" && view.status === "no_session") set({ status: "ready" });
        if (state.status === "open" && view.status === "starting") advanceWanted = true;
        return;
      }
      if (state.status === "closed") {
        halt("no_session");
        return;
      }
      // Al reconectar se comprueba ya la época: un player.claimed perdido durante el
      // corte se nota en menos de 3 s, sin esperar al siguiente latido (R012).
      void heartbeat();
      if (reports.all().length > 0) void flush();
      void advance();
    },

    setVersionObserver(observe) {
      observeVersion = observe;
    },

    destroy() {
      destroyed = true;
      epoch = null;
      clearTimers();
      provider?.destroy();
      provider = null;
    },
  };
}
