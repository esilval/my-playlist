// Reenvío de los eventos del monolito a las salas (ADR-0005, plan D6).
//
// El monolito publica cada cambio de la sesión de música en el canal de Redis
// `est:{establishment_id}`. Este servicio se suscribe por patrón a `est:*` y reenvía
// cada mensaje a la sala del mismo nombre, tal cual: el nombre del evento es su `type`
// y el cuerpo, el mensaje entero. No interpreta ni guarda nada (S5, S10).
import { createClient } from "redis";
import type { Server } from "socket.io";

const CHANNEL = /^est:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const CHANNEL_PATTERN = "est:*";

// Los eventos de la tabla de contratos del plan. Cualquier otro tipo se descarta: entre
// otras cosas, porque Socket.IO no deja emitir sus nombres reservados (connect…).
export const EVENT_TYPES: ReadonlySet<string> = new Set([
  "session.opened",
  "session.closed",
  "player.claimed",
  "track.started",
  "track.failed",
  "queue.changed",
]);

export interface SessionEventMessage {
  type: string;
  [field: string]: unknown;
}

/** El mensaje como evento, o null si no lo es: un canal o un cuerpo inesperado no se
 * reenvía a ninguna sala. */
export function parseEvent(channel: string, message: string): SessionEventMessage | null {
  if (!CHANNEL.test(channel)) return null;
  let event: unknown;
  try {
    event = JSON.parse(message);
  } catch {
    return null;
  }
  if (typeof event !== "object" || event === null || Array.isArray(event)) return null;
  const { type } = event as Record<string, unknown>;
  if (typeof type !== "string" || !EVENT_TYPES.has(type)) return null;
  return event as SessionEventMessage;
}

export interface Relay {
  close(): Promise<void>;
}

export async function startRelay(io: Server, redisUrl: string): Promise<Relay> {
  const subscriber = createClient({ url: redisUrl });
  subscriber.on("error", (error: unknown) => {
    // node-redis reconecta solo; mientras tanto, los clientes se resincronizan con la API.
    console.error("error de Redis en el reenvío", error);
  });
  await subscriber.connect();
  await subscriber.pSubscribe(CHANNEL_PATTERN, (message, channel) => {
    const event = parseEvent(channel, message);
    if (event === null) {
      console.error("mensaje descartado del canal", channel);
      return;
    }
    // La sala se llama igual que el canal: est:{id} solo llega a est:{id} (S8).
    io.to(channel).emit(event.type, event);
  });
  return {
    async close() {
      await subscriber.pUnsubscribe(CHANNEL_PATTERN);
      await subscriber.quit();
    },
  };
}
