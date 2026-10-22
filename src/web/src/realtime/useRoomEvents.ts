// Suscripción a la sala del establecimiento desde un componente (plan D6, D7).
//
// Abre una conexión de tiempo real al montarse y la cierra al desmontarse. Los
// manejadores y `connect` se leen siempre en su última versión, sin reconectar en cada
// render. Al conectar, el cliente entrega por `onState` el estado completo de la sesión.
import { useCallback, useEffect, useRef } from "react";

import { useApi } from "../api/context";
import {
  createRealtimeClient,
  type Connect,
  type RealtimeClient,
  type RealtimeHandlers,
  type RealtimeRole,
} from "./client";

export interface RoomEvents {
  /** Avisa de una versión vista por otra vía, como el latido (plan D3). */
  observeVersion(version: number): void;
}

export function useRoomEvents(
  role: RealtimeRole,
  handlers: RealtimeHandlers,
  connect?: Connect,
): RoomEvents {
  const api = useApi();
  const latest = useRef(handlers);
  const connectRef = useRef(connect);
  const client = useRef<RealtimeClient | null>(null);

  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    const realtime = createRealtimeClient({ api, role, connect: connectRef.current });
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
  }, [api, role]);

  const observeVersion = useCallback((version: number) => {
    client.current?.observeVersion(version);
  }, []);
  return { observeVersion };
}
