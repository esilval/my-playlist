// Estado de la sesión de música para la tarjeta del panel (plan D7).
//
// Carga el estado de la API, abre y cierra la sesión, y aplica los eventos de la sala del
// establecimiento: lo que suena, si hay reproductor activo y los fallos (R007, R014). Los
// fallos también llegan en el estado de la API, así que no se pierden al recargar.
//
// Cuando un evento no trae datos (`queue.changed`, `session.opened`), se vuelve a pedir
// el estado. Como esa respuesta puede llegar después de eventos más nuevos, solo se
// aplica si no es más vieja que lo que ya se mostró.
import { useCallback, useEffect, useRef, useState } from "react";

import { useApi } from "../../api/context";
import { errorCode } from "../../api/errors";
import type { components } from "../../api/schema";
import type { MusicSessionState, SessionEvent } from "../../realtime/client";

type Failure = components["schemas"]["FailureOut"];

export interface OpenSession {
  id: string;
  nowPlaying: string | null;
  playerActive: boolean;
  failures: Failure[];
  /** Se acaba de abrir y su cola no tiene canciones (R001). */
  fresh: boolean;
}

export type MusicSessionView =
  | { status: "loading" }
  | { status: "error" }
  | { status: "closed"; notice?: "email_not_verified" | "error" }
  | { status: "open"; session: OpenSession; notice?: "error" };

export interface MusicSessionControls {
  view: MusicSessionView;
  open(): Promise<void>;
  close(): Promise<void>;
  onEvent(event: SessionEvent): void;
  onState(state: MusicSessionState): void;
}

function fromState(state: MusicSessionState, fresh: boolean): MusicSessionView {
  if (state.status === "closed" || !state.session) return { status: "closed" };
  const { id, now_playing, player_active, failures } = state.session;
  return {
    status: "open",
    session: { id, nowPlaying: now_playing?.title ?? null, playerActive: player_active, failures, fresh },
  };
}

export function useMusicSession(): MusicSessionControls {
  const api = useApi();
  const [view, setView] = useState<MusicSessionView>({ status: "loading" });
  // Lo último que se mostró (de qué sesión y en qué versión), cuántos eventos llegaron y
  // de qué sesión era el último, y la versión con que se abrió la sesión recién creada.
  const shown = useRef<{
    session: string | null;
    version: number;
    events: number;
    eventSession: string | null;
    freshVersion: number | null;
  }>({ session: null, version: -1, events: 0, eventSession: null, freshVersion: null });

  /** Aplica un estado completo, salvo que sea más viejo que lo que ya se mostró. */
  const apply = useCallback((state: MusicSessionState, eventsBefore: number | null) => {
    const last = shown.current;
    const session = state.session ?? null;
    if (session && session.id === last.session && session.version < last.version) return;
    // Un estado pedido antes del último evento, de otra sesión que la de ese evento (o
    // «cerrada»), ya no vale.
    if (
      eventsBefore !== null &&
      last.events !== eventsBefore &&
      session?.id !== last.session &&
      session?.id !== last.eventSession
    ) {
      return;
    }
    shown.current = { ...last, session: session?.id ?? null, version: session?.version ?? -1 };
    setView((current) => {
      // La recién abierta sigue sin canciones mientras no cambie: cualquier cambio de la
      // cola sube la versión (plan D2).
      const fresh =
        current.status === "open" &&
        current.session.fresh &&
        current.session.id === session?.id &&
        session.version === last.freshVersion;
      return fromState(state, fresh);
    });
  }, []);

  const reload = useCallback(async () => {
    const eventsBefore = shown.current.events;
    try {
      const { data } = await api.GET("/api/owner/music-session");
      if (data) {
        apply(data, eventsBefore);
        return;
      }
    } catch {
      // Se trata abajo.
    }
    // Sin el estado nuevo, se conserva lo que había, con el aviso (D7).
    setView((current) =>
      current.status === "open" || current.status === "closed"
        ? { ...current, notice: "error" }
        : { status: "error" },
    );
  }, [api, apply]);

  useEffect(() => {
    let active = true;
    const eventsBefore = shown.current.events;
    api.GET("/api/owner/music-session").then(
      ({ data }) => {
        if (!active) return;
        if (data) apply(data, eventsBefore);
        else setView({ status: "error" });
      },
      () => {
        if (active) setView({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api, apply]);

  const open = useCallback(async () => {
    try {
      const { data, error, response } = await api.POST("/api/owner/music-session");
      if (data) {
        shown.current = {
          ...shown.current,
          session: data.session.id,
          version: data.session.version,
          freshVersion: response.status === 201 ? data.session.version : null,
        };
        // 201: recién abierta, con la cola vacía. 200: ya estaba abierta (R003).
        setView(fromState({ status: "open", session: data.session }, response.status === 201));
      } else if (response.status === 403 && errorCode(error) === "email_not_verified") {
        setView({ status: "closed", notice: "email_not_verified" });
      } else if (response.status !== 401) {
        setView({ status: "closed", notice: "error" });
      }
    } catch {
      setView({ status: "closed", notice: "error" });
    }
  }, [api]);

  const close = useCallback(async () => {
    const failed = () =>
      setView((current) => (current.status === "open" ? { ...current, notice: "error" } : current));
    try {
      const { response } = await api.DELETE("/api/owner/music-session");
      if (response.status === 204) {
        shown.current = { ...shown.current, session: null, version: -1 };
        setView({ status: "closed" });
      } else if (response.status !== 401) failed();
    } catch {
      failed();
    }
  }, [api]);

  const onEvent = useCallback(
    (event: SessionEvent) => {
      const last = shown.current;
      last.events += 1;
      last.eventSession = event.session_id;
      if (event.session_id === last.session) last.version = Math.max(last.version, event.version);
      switch (event.type) {
        case "session.closed":
          if (event.session_id === last.session || last.session === null) {
            shown.current = { ...last, session: null, version: -1 };
            setView({ status: "closed" });
          }
          return;
        case "session.opened":
          // Se abrió en otra pestaña u otro equipo.
          void reload();
          return;
        case "queue.changed":
          // Entró una canción o terminó la que sonaba: el estado dice cuál suena ahora.
          setView((current) =>
            current.status === "open"
              ? { ...current, session: { ...current.session, fresh: false } }
              : current,
          );
          void reload();
          return;
      }
      setView((current) => {
        if (current.status !== "open" || current.session.id !== event.session_id) return current;
        const session = { ...current.session };
        if (event.type === "player.claimed") session.playerActive = true;
        if (event.type === "track.started" && typeof event.title === "string") {
          session.nowPlaying = event.title;
          session.fresh = false;
        }
        if (event.type === "track.failed" && typeof event.title === "string") {
          session.failures = [
            ...session.failures,
            { title: event.title, failed_at: new Date().toISOString() },
          ];
        }
        return { ...current, session };
      });
    },
    [reload],
  );

  // El cliente de tiempo real ya ordena sus resincronizaciones.
  const onState = useCallback((state: MusicSessionState) => apply(state, null), [apply]);

  return { view, open, close, onEvent, onState };
}
