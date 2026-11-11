import type { AddressInfo } from "node:net";

import { describe, expect, it } from "vitest";

import { createRealtimeServer, LOCAL_REALTIME_TICKET_SECRET, loadConfig, PUBLIC_HEALTH_PATH } from "../src/server.js";

describe("configuración de los entornos desplegados (feature 004, plan D7)", () => {
  it("F004_R007 en preproduction exige un REALTIME_TICKET_SECRET propio", () => {
    for (const secret of [undefined, LOCAL_REALTIME_TICKET_SECRET, "corto"]) {
      expect(() => loadConfig({ ENV: "preproduction", REALTIME_TICKET_SECRET: secret }), String(secret)).toThrow(
        /en preproduction hace falta REALTIME_TICKET_SECRET/,
      );
    }
    const strong = "x".repeat(32);
    expect(loadConfig({ ENV: "preproduction", REALTIME_TICKET_SECRET: strong }).ticketSecret).toBe(strong);
    // Un entorno de desarrollo sigue arrancando con el secreto local.
    expect(loadConfig({ ENV: "local" }).ticketSecret).toBe(LOCAL_REALTIME_TICKET_SECRET);
  });
});

describe("comprobación de salud por CloudFront (feature 004, plan D12)", () => {
  it("F004_R013 GET /socket.io/health responde 200", async () => {
    const server = createRealtimeServer({ port: 0, ticketSecret: "x".repeat(32), redisUrl: "redis://unused" });
    await new Promise<void>((resolve) => server.http.listen(0, resolve));
    const base = `http://localhost:${(server.http.address() as AddressInfo).port}`;
    try {
      const health = await fetch(`${base}${PUBLIC_HEALTH_PATH}`);
      expect(health.status).toBe(200);
      expect(await health.json()).toEqual({ status: "ok" });
      // La del contenedor sigue igual, y el resto de /socket.io/ lo sigue atendiendo Socket.IO.
      expect((await fetch(`${base}/health`)).status).toBe(200);
      const handshake = await fetch(`${base}/socket.io/?EIO=4&transport=polling`);
      expect(handshake.status).toBe(200);
      expect((await fetch(`${base}/socket.io/otra`)).status).toBe(400);
    } finally {
      await server.io.close();
    }
  });
});
