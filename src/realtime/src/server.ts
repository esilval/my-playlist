// Servicio de tiempo real de MyPlaylist (C6, ADR-0005): Socket.IO con una sala por
// establecimiento. Solo difunde: los navegadores reciben, y las acciones van por la
// API HTTP del monolito.
import { createServer, type IncomingMessage, type Server as HttpServer, type ServerResponse } from "node:http";
import { pathToFileURL } from "node:url";

import { Server } from "socket.io";

import { namespaceFor, RealtimeMetrics } from "./metrics.js";
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

// Entornos desplegados (feature 004, plan D7): los dos exigen el secreto propio.
const DEPLOYED_ENVS = new Set(["preproduction", "production"]);

export function loadConfig(env: NodeJS.ProcessEnv = process.env): RealtimeConfig {
  const ticketSecret = env.REALTIME_TICKET_SECRET ?? LOCAL_REALTIME_TICKET_SECRET;
  if (
    env.ENV !== undefined &&
    DEPLOYED_ENVS.has(env.ENV) &&
    (ticketSecret === LOCAL_REALTIME_TICKET_SECRET ||
      ticketSecret.length < MIN_REALTIME_TICKET_SECRET_LENGTH)
  ) {
    throw new Error(
      `en ${env.ENV} hace falta REALTIME_TICKET_SECRET propio, de al menos ${MIN_REALTIME_TICKET_SECRET_LENGTH} caracteres (ADR-0014)`,
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

// La comprobación de salud que llega por CloudFront (feature 004, plan D12): CloudFront
// solo encamina /socket.io/* hacia este servicio.
export const PUBLIC_HEALTH_PATH = "/socket.io/health";

export function createRealtimeServer(
  config: RealtimeConfig,
  nowSeconds: () => number = () => Date.now() / 1000,
  metrics?: RealtimeMetrics,
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
  // Socket.IO atiende todo lo que empieza por /socket.io/ y respondería 400 a la
  // comprobación de salud: se atiende antes que él, y el resto le llega igual. Depende de
  // que Engine.IO instale su manejador de `request` al crearse, como hoy: la prueba F004_R013
  // lo vigila, y hay que revisarlo al actualizar Socket.IO o Engine.IO.
  const socketIoHandlers = http.listeners("request") as ((...args: unknown[]) => void)[];
  http.removeAllListeners("request");
  http.on("request", (request: IncomingMessage, response: ServerResponse) => {
    if (request.url === PUBLIC_HEALTH_PATH) {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end('{"status":"ok"}');
      return;
    }
    for (const handler of socketIoHandlers) handler.call(http, request, response);
  });
  useEstablishmentRooms(io, config.ticketSecret, nowSeconds, metrics);
  return { http, io };
}

const isEntryPoint = process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isEntryPoint) {
  const config = loadConfig();
  const metrics = new RealtimeMetrics(namespaceFor(process.env.ENV));
  const { http, io } = createRealtimeServer(config, undefined, metrics);
  await startRelay(io, config.redisUrl, metrics);
  metrics.start();
  http.listen(config.port, () => {
    console.log(`tiempo real escuchando en el puerto ${config.port}`);
  });
}
