// Estado del cliente que llega por el QR y sus acciones (feature 003, plan D7).
//
// Carga lo que suena, sus canciones pendientes y su cupo (R010), busca (R003) y pide
// (R005). Cada rechazo de la API tiene su aviso (R006, R008, R009, R012–R014). La sala
// del establecimiento entrega el estado nuevo por `onState` tras cada cambio; la página
// la abre después de la carga inicial, así que esa carga nunca pisa un estado más nuevo.
import { useCallback, useEffect, useState } from "react";

import { useApi } from "../../api/context";
import { errorCode } from "../../api/errors";
import type { components } from "../../api/schema";
import type { ClientMusicState } from "../../realtime/client";

export type RequestedTrack = components["schemas"]["RequestedTrackOut"];
export type TrackResult = components["schemas"]["TrackResultOut"];

export interface Quota {
  limit: number;
  free: number;
}

export type ClientMusicView =
  | { status: "loading" }
  | { status: "error" }
  | { status: "closed" }
  | { status: "open"; nowPlaying: string | null; mine: RequestedTrack[]; quota: Quota };

/** Un rechazo de la API, o un fallo de conexión (`error`). */
export type Rejection =
  | "quota_exceeded"
  | "already_queued"
  | "unknown_track"
  | "search_unavailable"
  | "too_many_searches"
  | "device_required"
  | "error";

export type ClientNotice = { kind: "requested"; title: string } | { kind: Rejection };

export interface ClientMusicControls {
  view: ClientMusicView;
  notice: ClientNotice | null;
  /** Los resultados, o `null` si la búsqueda se rechazó (el aviso dice por qué). */
  search(query: string): Promise<TrackResult[] | null>;
  request(track: TrackResult): Promise<void>;
  onState(state: ClientMusicState): void;
}

// Los rechazos con aviso propio; cualquier otro es un fallo de conexión.
const REJECTIONS: Record<string, Rejection> = {
  quota_exceeded: "quota_exceeded",
  already_queued: "already_queued",
  unknown_track: "unknown_track",
  search_unavailable: "search_unavailable",
  too_many_searches: "too_many_searches",
  device_required: "device_required",
};

function fromState(state: ClientMusicState): ClientMusicView {
  if (state.status === "closed") return { status: "closed" };
  return {
    status: "open",
    nowPlaying: state.now_playing?.title ?? null,
    mine: state.mine,
    quota: state.quota,
  };
}

export function useClientMusic(code: string): ClientMusicControls {
  const api = useApi();
  const [view, setView] = useState<ClientMusicView>({ status: "loading" });
  const [notice, setNotice] = useState<ClientNotice | null>(null);
  const params = { path: { code } };

  useEffect(() => {
    let active = true;
    api.GET("/api/public/establishments/{code}/music", { params: { path: { code } } }).then(
      ({ data }) => {
        if (!active) return;
        setView(data ? fromState(data) : { status: "error" });
      },
      () => {
        if (active) setView({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api, code]);

  const onState = useCallback((state: ClientMusicState) => setView(fromState(state)), []);

  /** Aplica un rechazo de la API: la sesión cerrada cambia la pantalla (R008). */
  function reject(status: number, body: unknown): void {
    const code = errorCode(body);
    if (status === 409 && code === "no_open_session") {
      setNotice(null);
      setView({ status: "closed" });
      return;
    }
    setNotice({ kind: (code && REJECTIONS[code]) || "error" });
  }

  async function search(query: string): Promise<TrackResult[] | null> {
    setNotice(null);
    try {
      const { data, error, response } = await api.GET("/api/public/establishments/{code}/search", {
        params: { ...params, query: { q: query } },
      });
      if (data) return data.results;
      reject(response.status, error);
    } catch {
      setNotice({ kind: "error" });
    }
    return null;
  }

  async function request(track: TrackResult): Promise<void> {
    setNotice(null);
    try {
      const { data, error, response } = await api.POST("/api/public/establishments/{code}/requests", {
        params,
        body: { ref: track.ref },
      });
      if (data) {
        setView((current) =>
          current.status === "open" ? { ...current, mine: data.mine, quota: data.quota } : current,
        );
        setNotice({ kind: "requested", title: track.title });
        return;
      }
      reject(response.status, error);
    } catch {
      setNotice({ kind: "error" });
    }
  }

  return { view, notice, search, request, onState };
}
