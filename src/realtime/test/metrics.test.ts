import { createHmac, randomUUID } from "node:crypto";
import type { AddressInfo } from "node:net";

import { io as connect } from "socket.io-client";
import { describe, expect, it, vi } from "vitest";

import { FLUSH_INTERVAL_MS, MAX_DELAY_SAMPLES, MAX_VALUES_PER_LINE, namespaceFor, RealtimeMetrics } from "../src/metrics.js";
import { createRealtimeServer } from "../src/server.js";

interface Line {
  event: string;
  Service: string;
  Connections: number;
  EventsRelayed: number;
  RedisErrors: number;
  RelayDelay?: number[];
  _aws: { Timestamp: number; CloudWatchMetrics: { Namespace: string; Dimensions: string[][]; Metrics: { Name: string; Unit: string }[] }[] };
}

function at(lines: Line[], index: number): Line {
  const line = lines[index];
  if (line === undefined) throw new Error(`falta la línea ${index}`);
  return line;
}

function recorder(now: () => number): { metrics: RealtimeMetrics; lines: Line[] } {
  const lines: Line[] = [];
  const metrics = new RealtimeMetrics("MyPlaylist/test", (line) => lines.push(JSON.parse(line) as Line), now);
  return { metrics, lines };
}

describe("métricas del tiempo real (feature 004, plan D11)", () => {
  it("F004_R011 cada 60 s escribe Connections, EventsRelayed, RelayDelay y RedisErrors en EMF", () => {
    const { metrics, lines } = recorder(() => 10_000);
    metrics.onConnect();
    metrics.onConnect();
    metrics.onDisconnect();
    metrics.onRelay(9_800);
    metrics.onRelay(9_950);
    metrics.onRedisError();

    metrics.flush();
    metrics.flush();

    const counters = at(lines, 0);
    const delays = at(lines, 1);
    const next = at(lines, 2);
    expect(counters).toMatchObject({ event: "metric", Service: "realtime", Connections: 1, EventsRelayed: 2, RedisErrors: 1 });
    expect(counters._aws.CloudWatchMetrics).toEqual([
      {
        Namespace: "MyPlaylist/test",
        Dimensions: [["Service"]],
        Metrics: [
          { Name: "Connections", Unit: "Count" },
          { Name: "EventsRelayed", Unit: "Count" },
          { Name: "RedisErrors", Unit: "Count" },
        ],
      },
    ]);
    expect(delays.RelayDelay).toEqual([200, 50]);
    expect(delays._aws.CloudWatchMetrics[0]?.Metrics).toEqual([{ Name: "RelayDelay", Unit: "Milliseconds" }]);
    expect(counters._aws.Timestamp).toBe(10_000);
    // El periodo siguiente empieza de cero, salvo las conexiones abiertas, y sin retrasos no
    // escribe su línea.
    expect(next).toMatchObject({ Connections: 1, EventsRelayed: 0, RedisErrors: 0 });
    expect(lines).toHaveLength(3);
    expect(FLUSH_INTERVAL_MS).toBe(60_000);
    expect(namespaceFor("production")).toBe("MyPlaylist/production");
    expect(namespaceFor(undefined)).toBe("MyPlaylist/local");

    // Con el temporizador, la línea sale sola cada intervalo.
    vi.useFakeTimers();
    try {
      const stop = metrics.start();
      vi.advanceTimersByTime(FLUSH_INTERVAL_MS * 2);
      stop();
      vi.advanceTimersByTime(FLUSH_INTERVAL_MS);
    } finally {
      vi.useRealTimers();
    }
    expect(lines).toHaveLength(5);
  });

  it("F004_R011 RelayDelay se mide desde published_at y se omite si el evento no lo trae", () => {
    const { metrics, lines } = recorder(() => 5_000);
    metrics.onRelay(undefined);
    metrics.onRelay("4000");
    metrics.onRelay(Number.NaN);
    metrics.onRelay(6_000); // reloj adelantado: nunca un retraso negativo
    metrics.onRelay(4_000);

    metrics.flush();

    expect(at(lines, 0).EventsRelayed).toBe(5);
    expect(at(lines, 1).RelayDelay).toEqual([0, 1_000]);
  });

  it("F004_R011 parte RelayDelay en líneas de 100 valores como mucho", () => {
    const { metrics, lines } = recorder(() => 100_000);
    for (let i = 0; i < 250; i += 1) metrics.onRelay(100_000 - i);

    metrics.flush();

    const delays = lines.slice(1).map((line) => line.RelayDelay ?? []);
    expect(delays.map((values) => values.length)).toEqual([100, 100, 50]);
    expect(delays.every((values) => values.length <= MAX_VALUES_PER_LINE)).toBe(true);
    expect(delays.flat()).toHaveLength(250);
    expect(at(lines, 0).EventsRelayed).toBe(250);

    // Una ráfaga no hace crecer la lista sin límite.
    for (let i = 0; i < MAX_DELAY_SAMPLES + 500; i += 1) metrics.onRelay(99_000);
    lines.length = 0;
    metrics.flush();
    expect(lines.slice(1).flatMap((line) => line.RelayDelay ?? [])).toHaveLength(MAX_DELAY_SAMPLES);
    expect(at(lines, 0).EventsRelayed).toBe(MAX_DELAY_SAMPLES + 500);
  });

  it("F004_R011 cuenta las conexiones que abre y cierra el servidor", async () => {
    const secret = "secreto-de-pruebas-de-las-metricas-0123456789";
    const segment = Buffer.from(JSON.stringify({ est: randomUUID(), exp: 1_800_000_060, jti: randomUUID(), role: "client" })).toString("base64url");
    const ticket = `${segment}.${createHmac("sha256", secret).update(segment).digest("base64url")}`;
    const { metrics, lines } = recorder(() => Date.now());
    const server = createRealtimeServer({ port: 0, ticketSecret: secret, redisUrl: "redis://unused" }, () => 1_800_000_000, metrics);
    await new Promise<void>((resolve) => server.http.listen(0, resolve));
    const url = `http://localhost:${(server.http.address() as AddressInfo).port}`;
    try {
      const client = connect(url, { auth: { ticket }, reconnection: false, transports: ["websocket"] });
      await new Promise<void>((resolve, reject) => {
        client.once("connect", () => resolve());
        client.once("connect_error", reject);
      });
      metrics.flush();
      client.disconnect();
      await new Promise((resolve) => setTimeout(resolve, 50));
      metrics.flush();
    } finally {
      await server.io.close();
    }
    expect(lines.map((line) => line.Connections)).toEqual([1, 0]);
  });
});
