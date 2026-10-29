import { createHmac, randomUUID } from "node:crypto";
import type { AddressInfo } from "node:net";

import { io as connect, type Socket as ClientSocket } from "socket.io-client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { roomFor } from "../src/rooms.js";
import { createRealtimeServer, type RealtimeServer } from "../src/server.js";

const SECRET = "secreto-de-pruebas-de-las-salas-0123456789";
const NOW = 1_800_000_000;

// Firma con el mismo formato que el monolito; los vectores de ticket.test.ts
// comprueban que ambos coinciden.
function ticketFor(establishmentId: string, exp = NOW + 60, role = "owner"): string {
  const payload = { est: establishmentId, exp, jti: randomUUID(), role };
  const segment = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = createHmac("sha256", SECRET).update(segment).digest("base64url");
  return `${segment}.${signature}`;
}

let server: RealtimeServer;
let url: string;
const clients: ClientSocket[] = [];

beforeEach(async () => {
  server = createRealtimeServer({ port: 0, ticketSecret: SECRET, redisUrl: "redis://unused" }, () => NOW);
  await new Promise<void>((resolve) => server.http.listen(0, resolve));
  url = `http://localhost:${(server.http.address() as AddressInfo).port}`;
});

afterEach(async () => {
  for (const client of clients.splice(0)) client.disconnect();
  await server.io.close();
});

function open(ticket?: string): ClientSocket {
  const client = connect(url, { auth: ticket === undefined ? {} : { ticket }, reconnection: false, transports: ["websocket"] });
  clients.push(client);
  return client;
}

function connected(client: ClientSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    client.once("connect", () => resolve());
    client.once("connect_error", reject);
  });
}

function refused(client: ClientSocket): Promise<string> {
  return new Promise((resolve, reject) => {
    client.once("connect", () => reject(new Error("se conectó sin un ticket válido")));
    client.once("connect_error", (error) => resolve(error.message));
  });
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

describe("salas por establecimiento", () => {
  it("F002_R013 une el socket solo a la sala est:{id} de su ticket", async () => {
    const a = randomUUID();
    const client = open(ticketFor(a));
    await connected(client);

    const [socket] = await server.io.fetchSockets();
    expect(socket).toBeDefined();
    // Su sala propia de Socket.IO y la del establecimiento, nada más.
    expect([...(socket?.rooms ?? [])].sort()).toEqual([roomFor(a), socket?.id].sort());

    const received = nextEvent(client, "track.started", 1000);
    server.io.to(roomFor(a)).emit("track.started", { title: "A" });
    expect(await received).toEqual({ title: "A" });

    // Sin ticket, con uno caducado o con uno alterado, no entra.
    expect(await refused(open())).toBe("unauthorized");
    expect(await refused(open(ticketFor(a, NOW)))).toBe("unauthorized");
    expect(await refused(open(`${ticketFor(a)}x`))).toBe("unauthorized");
  });

  it("F002_R013 un socket no puede unirse a la sala de otro establecimiento", async () => {
    const a = randomUUID();
    const b = randomUUID();
    const clientA = open(ticketFor(a));
    const clientB = open(ticketFor(b));
    await Promise.all([connected(clientA), connected(clientB)]);

    // No hay ningún evento para unirse a una sala: pedirlo no hace nada.
    clientA.emit("join", roomFor(b));
    clientA.emit("subscribe", { room: roomFor(b) });
    await new Promise((resolve) => setTimeout(resolve, 100));

    const inB = await server.io.in(roomFor(b)).fetchSockets();
    expect(inB.map((socket) => socket.id)).toEqual([clientB.id]);

    const atA = nextEvent(clientA, "track.started", 300);
    const atB = nextEvent(clientB, "track.started", 1000);
    server.io.to(roomFor(b)).emit("track.started", { title: "de B" });
    expect(await atB).toEqual({ title: "de B" });
    expect(await atA).toBeUndefined();
  });

  it("F003_R010 acepta el ticket client y lo une a la sala de su establecimiento", async () => {
    const a = randomUUID();
    const client = open(ticketFor(a, NOW + 60, "client"));
    await connected(client);

    const [socket] = await server.io.fetchSockets();
    expect([...(socket?.rooms ?? [])].sort()).toEqual([roomFor(a), socket?.id].sort());
    // Recibe los cambios de la cola de su establecimiento.
    const received = nextEvent(client, "queue.changed", 1000);
    server.io.to(roomFor(a)).emit("queue.changed", { session_id: "s", version: 2 });
    expect(await received).toEqual({ session_id: "s", version: 2 });

    // Un tipo que no existe no entra.
    expect(await refused(open(ticketFor(a, NOW + 60, "screen-x")))).toBe("unauthorized");
  });

  it("F003_R011 un ticket client de un establecimiento no entra en la sala de otro", async () => {
    const a = randomUUID();
    const b = randomUUID();
    const clientA = open(ticketFor(a, NOW + 60, "client"));
    const ownerB = open(ticketFor(b));
    await Promise.all([connected(clientA), connected(ownerB)]);

    clientA.emit("join", roomFor(b));
    await new Promise((resolve) => setTimeout(resolve, 100));

    const inB = await server.io.in(roomFor(b)).fetchSockets();
    expect(inB.map((socket) => socket.id)).toEqual([ownerB.id]);
    const atA = nextEvent(clientA, "queue.changed", 300);
    server.io.to(roomFor(b)).emit("queue.changed", { session_id: "de B", version: 1 });
    expect(await atA).toBeUndefined();
  });
});
