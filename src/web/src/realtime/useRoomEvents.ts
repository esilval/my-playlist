// Suscripción a la sala del establecimiento desde un componente (plan D6, D7).
//
// Abre una conexión de tiempo real al montarse y la cierra al desmontarse. Los
// manejadores y `connect` se leen siempre en su última versión, sin reconectar en cada
// render. Al conectar, el cliente entrega por `onState` el estado completo de la sesión.
//
// `useRoomEvents` es la del dueño y el reproductor; `useClientRoomEvents`, la del
// cliente que llega por el QR (feature 003, plan D6), que recibe su propio estado.
import { useCallback, useEffect, useMemo, useRef } from "react";

import { useApi } from "../api/context";
import {
  clientSource,
  createRealtimeClient,
  ownerSource,
  type ClientMusicState,
  type Connect,
  type MusicSessionState,
  type RealtimeClient,
  type RealtimeHandlers,
  type RealtimeRole,
  type RealtimeSource,
} from "./client";

export interface RoomEvents {
  /** Avisa de una versión vista por otra vía, como el latido (plan D3). */
  observeVersion(version: number): void;
}

export function useRoomEvents(
  role: RealtimeRole,
  handlers: RealtimeHandlers<MusicSessionState>,
  connect?: Connect,
): RoomEvents {
  const api = useApi();
  const source = useMemo(() => ownerSource(api, role), [api, role]);
  return useRealtime(source, handlers, connect);
}

export function useClientRoomEvents(
  code: string,
  handlers: RealtimeHandlers<ClientMusicState>,
  connect?: Connect,
): RoomEvents {
  const api = useApi();
  const source = useMemo(() => clientSource(api, code), [api, code]);
  return useRealtime(source, handlers, connect);
}

function useRealtime<S>(
  source: RealtimeSource<S>,
  handlers: RealtimeHandlers<S>,
  connect?: Connect,
): RoomEvents {
  const latest = useRef(handlers);
  const connectRef = useRef(connect);
  const client = useRef<RealtimeClient<S> | null>(null);

  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    const realtime = createRealtimeClient({ source, connect: connectRef.current });
    client.current = realtime;
    const unsubscribe = realtime.subscribe({
      onEvent: (event) => latest.current.onEvent?.(event),
      onState: (state) => latest.current.onState?.(state),
    });
    return () => {
      unsubscribe();
      realtime.close();
      client.current = null;
    };
  }, [source]);

  const observeVersion = useCallback((version: number) => {
    client.current?.observeVersion(version);
  }, []);
  return { observeVersion };
}
