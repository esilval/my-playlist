// Servicio de tiempo real de MyPlaylist (C6, ADR-0005): Socket.IO con una sala por
// establecimiento. Solo difunde: los navegadores reciben, y las acciones van por la
// API HTTP del monolito.
import { createServer, type Server as HttpServer } from "node:http";
import { pathToFileURL } from "node:url";

import { Server } from "socket.io";

import { startRelay } from "./relay.js";
import { useEstablishmentRooms } from "./rooms.js";

// El mismo secreto de desarrollo que el monolito (app/shared/config.py): en local los
// tickets validan sin configurar nada; producción no arranca con él (ADR-0014).
export const LOCAL_REALTIME_TICKET_SECRET = "solo-para-desarrollo-local-no-usar-en-produccion";
export const MIN_REALTIME_TICKET_SECRET_LENGTH = 32;

export interface RealtimeConfig {
  port: number;
  ticketSecret: string;
  redisUrl: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): RealtimeConfig {
  const ticketSecret = env.REALTIME_TICKET_SECRET ?? LOCAL_REALTIME_TICKET_SECRET;
  if (
    env.ENV === "production" &&
    (ticketSecret === LOCAL_REALTIME_TICKET_SECRET ||
      ticketSecret.length < MIN_REALTIME_TICKET_SECRET_LENGTH)
  ) {
    throw new Error(
      `en producción hace falta REALTIME_TICKET_SECRET propio, de al menos ${MIN_REALTIME_TICKET_SECRET_LENGTH} caracteres (ADR-0014)`,
    );
  }
  return {
    port: Number(env.PORT ?? 3001),
    ticketSecret,
    redisUrl: env.REDIS_URL ?? "redis://localhost:6379/0",
  };
}

export interface RealtimeServer {
  http: HttpServer;
  io: Server;
}

export function createRealtimeServer(
  config: RealtimeConfig,
  nowSeconds: () => number = () => Date.now() / 1000,
): RealtimeServer {
  const http = createServer((request, response) => {
    // Para el healthcheck del contenedor; Socket.IO atiende /socket.io por su cuenta.
    if (request.url === "/health") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end('{"status":"ok"}');
      return;
    }
    response.writeHead(404).end();
  });
  // Mismo origen que la SPA (el proxy reenvía /socket.io): sin CORS ni cliente servido.
  const io = new Server(http, { serveClient: false });
  useEstablishmentRooms(io, config.ticketSecret, nowSeconds);
  return { http, io };
}

const isEntryPoint = process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isEntryPoint) {
  const config = loadConfig();
  const { http, io } = createRealtimeServer(config);
  await startRelay(io, config.redisUrl);
  http.listen(config.port, () => {
    console.log(`tiempo real escuchando en el puerto ${config.port}`);
  });
}
