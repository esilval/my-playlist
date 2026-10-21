// Reenvío de Redis a las salas contra el Redis real de docker-compose (plan D6).
import { createHmac, randomUUID } from "node:crypto";
import type { AddressInfo } from "node:net";

import { createClient } from "redis";
import { io as connect, type Socket as ClientSocket } from "socket.io-client";
import { afterAll, afterEach, beforeEach, describe, expect, it } from "vitest";

import { parseEvent, startRelay, type Relay } from "../src/relay.js";
import { createRealtimeServer, type RealtimeServer } from "../src/server.js";

const SECRET = "secreto-de-pruebas-del-reenvio-0123456789";
const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6379/0";

// Mismo formato que el monolito; los vectores de ticket.test.ts lo comprueban.
function ticketFor(establishmentId: string): string {
  const payload = { est: establishmentId, exp: Math.floor(Date.now() / 1000) + 60, jti: randomUUID(), role: "player" };
  const segment = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${segment}.${createHmac("sha256", SECRET).update(segment).digest("base64url")}`;
}

let server: RealtimeServer;
let relay: Relay;
let url: string;
const publisher = createClient({ url: REDIS_URL });
const clients: ClientSocket[] = [];

beforeEach(async () => {
  server = createRealtimeServer({ port: 0, ticketSecret: SECRET, redisUrl: REDIS_URL });
  relay = await startRelay(server.io, REDIS_URL);
  await new Promise<void>((resolve) => server.http.listen(0, resolve));
  url = `http://localhost:${(server.http.address() as AddressInfo).port}`;
  if (!publisher.isOpen) await publisher.connect();
});

afterEach(async () => {
  for (const client of clients.splice(0)) client.disconnect();
  await relay.close();
  await server.io.close();
});

afterAll(async () => {
  if (publisher.isOpen) await publisher.quit();
});

async function joined(establishmentId: string): Promise<ClientSocket> {
  const client = connect(url, { auth: { ticket: ticketFor(establishmentId) }, reconnection: false, transports: ["websocket"] });
  clients.push(client);
  await new Promise<void>((resolve, reject) => {
    client.once("connect", () => resolve());
    client.once("connect_error", reject);
  });
  return client;
}

function nextEvent(client: ClientSocket, name: string, timeoutMs: number): Promise<unknown> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(undefined), timeoutMs);
    client.once(name, (payload: unknown) => {
      clearTimeout(timer);
      resolve(payload);
    });
  });
}

/** Publica en el canal del establecimiento como lo hace el monolito (RedisEventPublisher). */
async function publish(establishmentId: string, event: Record<string, unknown>): Promise<void> {
  await publisher.publish(`est:${establishmentId}`, JSON.stringify(event));
}

describe("reenvío de Redis a las salas", () => {
  it("F002_R014 un mensaje de est:{id} llega a su sala en menos de 1 s", async () => {
    const a = randomUUID();
    const client = await joined(a);
    const event = { item_id: randomUUID(), title: "A", type: "track.started", session_id: randomUUID(), version: 4 };

    const received = nextEvent(client, "track.started", 1000);
    const start = performance.now();
    await publish(a, event);
    const payload = await received;
    const elapsed = performance.now() - start;

    expect(payload).toEqual(event);
    expect(elapsed).toBeLessThan(1000);
  });

  it("F002_R014 un mensaje de est:{a} no llega a la sala de b", async () => {
    const a = randomUUID();
    const b = randomUUID();
    const [clientA, clientB] = await Promise.all([joined(a), joined(b)]);

    const atA = nextEvent(clientA, "track.started", 1000);
    const atB = nextEvent(clientB, "track.started", 1000);
    await publish(a, { type: "track.started", session_id: randomUUID(), version: 1, item_id: "x", title: "de A" });
    expect(await atA).toMatchObject({ title: "de A" });
    // Después, uno para B: si el de A le hubiera llegado, sería lo primero que recibe.
    await publish(b, { type: "track.started", session_id: randomUUID(), version: 1, item_id: "y", title: "de B" });

    expect(await atB).toMatchObject({ title: "de B" });
  });

  it("F002_R011 reenvía session.closed tal cual", async () => {
    const a = randomUUID();
    const client = await joined(a);
    const event = { type: "session.closed", session_id: randomUUID(), version: 9 };

    const received = nextEvent(client, "session.closed", 1000);
    await publish(a, event);

    expect(await received).toEqual(event);
  });

  it("F002_R010 reenvía player.claimed tal cual", async () => {
    const a = randomUUID();
    const client = await joined(a);
    const event = { epoch: 3, type: "player.claimed", session_id: randomUUID(), version: 7 };

    const received = nextEvent(client, "player.claimed", 1000);
    await publish(a, event);

    expect(await received).toEqual(event);
  });

  it("F002_R008 reenvía queue.changed tal cual", async () => {
    const a = randomUUID();
    const client = await joined(a);
    const event = { type: "queue.changed", session_id: randomUUID(), version: 2 };

    const received = nextEvent(client, "queue.changed", 1000);
    await publish(a, event);

    expect(await received).toEqual(event);
  });

  it("F002_R014 descarta canales y mensajes que no son eventos de un establecimiento", () => {
    const id = randomUUID();
    const event = JSON.stringify({ type: "queue.changed", session_id: id, version: 1 });

    expect(parseEvent(`est:${id}`, event)).toEqual(JSON.parse(event));
    for (const channel of ["est:", "est:otro", "global", `est:${id}:x`]) {
      expect(parseEvent(channel, event), channel).toBeNull();
    }
    const unknown = ['{"type":"connect"}', '{"type":"disconnect"}', '{"type":"otro.evento"}'];
    for (const message of ["no es json", "[1,2]", "null", '{"version":1}', '{"type":""}', ...unknown]) {
      expect(parseEvent(`est:${id}`, message), message).toBeNull();
    }
  });
});
