// Cliente de tiempo real de la SPA (plan D6, ADR-0014).
//
// Se conecta al servicio de tiempo real por el mismo origen (/socket.io) con un ticket
// de 60 s que pide a la API antes de cada intento de conexión, también al reconectar.
// Solo recibe: las acciones van por la API.
//
// Los eventos llevan la sesión y su versión. Al conectar (también la primera vez, para
// no dejar un hueco entre la carga inicial de la pantalla y la entrada en la sala),
// tras un salto de versión dentro de la misma sesión, o cuando el latido avisa de una
// versión más alta, pide el estado completo a la API y se lo entrega a los suscriptores.
// Cada sesión de música empieza en la versión 0: un cambio de sesión no es un salto.
//
// De dónde salen el ticket y el estado lo decide la fuente: la del dueño y el
// reproductor (feature 002) o la del cliente del QR (feature 003, plan D6). El estado
// del cliente no lleva versión: tras cada evento lo vuelve a pedir, porque sus
// pendientes y su cupo no viajan en los eventos.
import { io } from "socket.io-client";

import type { ApiClient } from "../api/client";
import type { components } from "../api/schema";

export type RealtimeRole = "owner" | "player";
export type MusicSessionState = components["schemas"]["MusicSessionOut"];
export type ClientMusicState = components["schemas"]["ClientMusicOut"];

// La tabla de eventos del plan; el servicio de tiempo real no reenvía otros.
export const EVENT_TYPES = [
  "session.opened",
  "session.closed",
  "player.claimed",
  "track.started",
  "track.failed",
  "queue.changed",
] as const;
export type SessionEventType = (typeof EVENT_TYPES)[number];

export interface SessionEvent {
  type: SessionEventType;
  session_id: string;
  version: number;
  [field: string]: unknown;
}

export interface RealtimeHandlers<S = MusicSessionState> {
  onEvent?: (event: SessionEvent) => void;
  /** Estado completo de la API: al conectar, tras un salto de versión o un aviso del latido. */
  onState?: (state: S) => void;
}

/** Un estado de la API, con la sesión y la versión a las que corresponde, si las lleva. */
export interface FetchedState<S> {
  state: S;
  sessionId: string | null;
  version: number | null;
}

/** De dónde saca el cliente el ticket y el estado completo. */
export interface RealtimeSource<S> {
  requestTicket(): Promise<string | undefined>;
  /** `null` si la API respondió con un error. */
  fetchState(): Promise<FetchedState<S> | null>;
  /**
   * Los eventos tras los que se vuelve a pedir el estado, para una fuente cuyo estado no
   * lleva versión; `null` si la lleva, y entonces se pide solo tras un salto de versión.
   */
  readonly refreshOn: readonly SessionEventType[] | null;
}

/** La fuente del dueño y del reproductor, con su sesión iniciada (feature 002). */
export function ownerSource(api: ApiClient, role: RealtimeRole): RealtimeSource<MusicSessionState> {
  return {
    async requestTicket() {
      const { data } = await api.POST("/api/owner/realtime-ticket", { body: { role } });
      return data?.ticket;
    },
    async fetchState() {
      const { data } = await api.GET("/api/owner/music-session");
      if (!data) return null;
      return { state: data, sessionId: data.session?.id ?? null, version: data.session?.version ?? null };
    },
    refreshOn: null,
  };
}

// Los que cambian lo que ve el cliente (D6); `player.claimed` no le cambia nada.
const CLIENT_REFRESH_ON: readonly SessionEventType[] = [
  "session.opened",
  "session.closed",
  "track.started",
  "track.failed",
  "queue.changed",
];

/** La fuente del cliente que llega por el QR, con la cookie de su dispositivo (D6). */
export function clientSource(api: ApiClient, code: string): RealtimeSource<ClientMusicState> {
  const params = { path: { code } };
  return {
    async requestTicket() {
      const { data } = await api.POST("/api/public/establishments/{code}/realtime-ticket", { params });
      return data?.ticket;
    },
    async fetchState() {
      const { data } = await api.GET("/api/public/establishments/{code}/music", { params });
      if (!data) return null;
      return { state: data, sessionId: null, version: null };
    },
    refreshOn: CLIENT_REFRESH_ON,
  };
}

/** Lo que el cliente necesita de un socket; en pruebas se sustituye por uno falso. */
export interface SocketLike {
  on(event: string, listener: (...args: unknown[]) => void): unknown;
  connect(): unknown;
  disconnect(): unknown;
  /** Si Socket.IO sigue intentando reconectar por su cuenta. */
  readonly active: boolean;
}

export type AuthCallback = (callback: (data: { ticket?: string }) => void) => void;
export type Connect = (auth: AuthCallback) => SocketLike;

const defaultConnect: Connect = (auth) =>
  io(window.location.origin, { auth, transports: ["websocket"] });

// Si el servicio rechaza la conexión (sin ticket, o con uno caducado), Socket.IO no
// vuelve a intentarlo solo: se reintenta con un ticket nuevo, con espera creciente.
const RETRY_FIRST_MS = 1000;
const RETRY_MAX_MS = 30_000;
// Peticiones de estado seguidas como mucho, si la API devuelve algo más viejo que lo que
// ya llegó por el canal (el estado se pidió justo antes de ese evento).
const MAX_RESYNC_ATTEMPTS = 3;

export interface RealtimeClient<S = MusicSessionState> {
  subscribe(handlers: RealtimeHandlers<S>): () => void;
  /** La versión que vio otra fuente, como el latido del reproductor (plan D3). */
  observeVersion(version: number): void;
  close(): void;
}

export interface RealtimeClientOptions<S> {
  source: RealtimeSource<S>;
  connect?: Connect;
  /** Para las pruebas: cómo se programa el reintento tras un rechazo. */
  schedule?: (callback: () => void, delayMs: number) => unknown;
}

function isSessionEvent(payload: unknown): payload is SessionEvent {
  if (typeof payload !== "object" || payload === null) return false;
  const { session_id, version } = payload as Record<string, unknown>;
  return typeof session_id === "string" && typeof version === "number" && Number.isInteger(version);
}

export function createRealtimeClient<S>({
  source,
  connect = defaultConnect,
  schedule = (callback, delayMs) => setTimeout(callback, delayMs),
}: RealtimeClientOptions<S>): RealtimeClient<S> {
  const subscribers = new Set<RealtimeHandlers<S>>();
  // La última versión conocida, de la sesión a la que pertenece.
  let sessionId: string | null = null;
  let version: number | null = null;
  let resyncing = false;
  let resyncAgain = false;
  // Cuántos eventos llegaron: si llega alguno mientras se pide el estado, la respuesta
  // puede ser de antes de ese evento.
  let eventsSeen = 0;
  let retryMs = RETRY_FIRST_MS;
  let closed = false;

  /** Recuerda la versión más alta de la sesión; con otra sesión, empieza de nuevo. */
  function remember(session: string | null, seen: number | null): void {
    if (session !== sessionId) {
      sessionId = session;
      version = seen;
    } else if (seen !== null && (version === null || seen > version)) {
      version = seen;
    }
  }

  async function resync(): Promise<void> {
    if (resyncing) {
      // Llegó otro salto mientras se pedía el estado: se repite al terminar.
      resyncAgain = true;
      return;
    }
    resyncing = true;
    try {
      let staleAttempts = 0;
      do {
        resyncAgain = false;
        const eventsBefore = eventsSeen;
        const fetched = await source.fetchState();
        if (closed) return;
        // Una respuesta de error no descarta una repetición pendiente.
        if (!fetched) continue;
        const { state, sessionId: id, version: seen } = fetched;
        // Más viejo que lo ya entregado: de la misma sesión con una versión menor, o de
        // otra sesión cuando entretanto llegó un evento de la sesión actual (por
        // ejemplo, se abrió una sesión nueva). No se entrega y se pide otra vez.
        // Sin versión no hay forma de saberlo: se entrega, y el evento que llegó
        // entretanto ya pidió repetirla.
        const olderInSession =
          id !== null && id === sessionId && seen !== null && version !== null && seen < version;
        const overtakenByEvent = eventsSeen !== eventsBefore && id !== sessionId;
        if (source.refreshOn === null && (olderInSession || overtakenByEvent)) {
          staleAttempts += 1;
          resyncAgain = staleAttempts < MAX_RESYNC_ATTEMPTS;
          continue;
        }
        staleAttempts = 0;
        remember(id, seen);
        for (const handlers of subscribers) handlers.onState?.(state);
      } while (resyncAgain && !closed);
    } catch {
      // Sin red: lo intentará de nuevo al reconectar o con el siguiente salto.
    } finally {
      resyncing = false;
    }
  }

  function observeVersion(seen: number): void {
    // El latido no es un evento: cualquier versión mayor que la última vista quiere decir
    // que hay un evento que no llegó (o que aún viene de camino; pedir el estado de más
    // no hace daño).
    if (version !== null && seen > version) void resync();
  }

  const auth: AuthCallback = (callback) => {
    void source
      .requestTicket()
      .then((ticket) => callback({ ticket }))
      .catch(() => callback({}));
  };

  const socket = connect(auth);
  socket.on("connect", () => {
    retryMs = RETRY_FIRST_MS;
    void resync();
  });
  socket.on("connect_error", () => {
    if (closed || socket.active) return;
    const delayMs = retryMs;
    retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
    schedule(() => {
      if (!closed) socket.connect();
    }, delayMs);
  });
  for (const type of EVENT_TYPES) {
    socket.on(type, (payload: unknown) => {
      if (!isSessionEvent(payload)) return;
      eventsSeen += 1;
      const event: SessionEvent = { ...payload, type };
      const jumped =
        event.session_id === sessionId && version !== null && event.version > version + 1;
      remember(event.session_id, event.version);
      for (const handlers of subscribers) handlers.onEvent?.(event);
      if (jumped || source.refreshOn?.includes(type)) void resync();
    });
  }

  return {
    subscribe(handlers) {
      subscribers.add(handlers);
      return () => subscribers.delete(handlers);
    },
    observeVersion,
    close() {
      closed = true;
      subscribers.clear();
      socket.disconnect();
    },
  };
}
