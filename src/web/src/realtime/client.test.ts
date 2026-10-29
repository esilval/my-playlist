import { describe, expect, it, vi } from "vitest";

import { fakeApi } from "../test/fake-api";
import {
  clientSource,
  createRealtimeClient,
  ownerSource,
  type AuthCallback,
  type SessionEvent,
  type SocketLike,
} from "./client";

// Socket falso: guarda los manejadores y la función `auth`, para simular cada intento
// de conexión (la primera y cada reconexión) y cada evento del servidor.
function fakeSocket() {
  const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
  let auth: AuthCallback | null = null;
  const socket = {
    active: false as boolean,
    on(event: string, listener: (...args: unknown[]) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
  } satisfies SocketLike;
  return {
    socket,
    connect: (callback: AuthCallback) => {
      auth = callback;
      return socket;
    },
    /** Un intento de conexión: el cliente pide el ticket y lo entrega. */
    attempt(): Promise<{ ticket?: string }> {
      return new Promise((resolve) => auth?.(resolve));
    },
    emit(event: string, payload?: unknown) {
      for (const listener of listeners.get(event) ?? []) listener(payload);
    },
  };
}

function event(
  type: SessionEvent["type"],
  version: number,
  extra: Record<string, unknown> = {},
  session = "s1",
): SessionEvent {
  return { type, session_id: session, version, ...extra };
}

function state(version: number, session = "s1") {
  return {
    status: "open",
    session: {
      id: session,
      opened_at: "2026-10-21T20:00:00Z",
      version,
      now_playing: null,
      player_active: true,
      failures: [],
    },
  };
}

function setUp(stateVersion = 7) {
  // Lo que devuelve la API en cada resincronización; cada prueba puede cambiarlo.
  const current = { body: state(stateVersion) };
  const api = fakeApi({ "GET /api/owner/music-session": () => ({ status: 200, body: current.body }) });
  const fake = fakeSocket();
  const realtime = createRealtimeClient({ source: ownerSource(api.client, "owner"), connect: fake.connect });
  const onEvent = vi.fn();
  const onState = vi.fn();
  realtime.subscribe({ onEvent, onState });
  const resyncs = () => api.sent.filter((request) => request.path === "/api/owner/music-session").length;
  return { ...api, current, fake, realtime, onEvent, onState, resyncs };
}

describe("cliente de tiempo real", () => {
  it("F002_R014 pide un ticket antes de conectar y de cada reconexión", async () => {
    let issued = 0;
    const { client, sent } = fakeApi({
      "POST /api/owner/realtime-ticket": () => ({ status: 200, body: { ticket: `t${++issued}`, expires_in: 60 } }),
    });
    const fake = fakeSocket();
    createRealtimeClient({ source: ownerSource(client, "player"), connect: fake.connect });

    // Cada intento (el primero y cada reconexión) usa un ticket nuevo: el anterior
    // pudo caducar (60 s).
    expect(await fake.attempt()).toEqual({ ticket: "t1" });
    expect(await fake.attempt()).toEqual({ ticket: "t2" });

    const tickets = sent.filter((request) => request.path === "/api/owner/realtime-ticket");
    expect(tickets).toEqual([
      { method: "POST", path: "/api/owner/realtime-ticket", body: { role: "player" } },
      { method: "POST", path: "/api/owner/realtime-ticket", body: { role: "player" } },
    ]);
  });

  it("F002_R014 si el servicio rechaza la conexión, reintenta con espera creciente", async () => {
    const { client } = fakeApi({ "POST /api/owner/realtime-ticket": { status: 503 } });
    const fake = fakeSocket();
    const delays: number[] = [];
    const pending: (() => void)[] = [];
    createRealtimeClient({
      source: ownerSource(client, "owner"),
      connect: fake.connect,
      schedule: (callback, delayMs) => {
        delays.push(delayMs);
        pending.push(callback);
      },
    });

    // Sin ticket, el intento sigue y el servicio lo rechaza; Socket.IO no reintenta solo.
    expect(await fake.attempt()).toEqual({ ticket: undefined });
    for (let attempt = 0; attempt < 6; attempt++) fake.emit("connect_error", new Error("unauthorized"));
    for (const retry of pending.splice(0)) retry();

    expect(delays).toEqual([1000, 2000, 4000, 8000, 16000, 30000]);
    expect(fake.socket.connect).toHaveBeenCalledTimes(6);

    // Al conectar, la espera vuelve a empezar.
    fake.emit("connect");
    fake.emit("connect_error", new Error("unauthorized"));
    expect(delays.at(-1)).toBe(1000);

    // Si Socket.IO ya está reintentando (un corte de red), no se duplica el intento.
    fake.socket.active = true;
    fake.emit("connect_error", new Error("xhr poll error"));
    expect(delays).toHaveLength(7);
  });

  it("F002_R014 ante un salto de versión pide el estado completo a la API", async () => {
    const { current, fake, realtime, onEvent, onState, resyncs } = setUp(7);

    // Al conectar pide el estado, para no dejar un hueco con la carga inicial.
    fake.emit("connect");
    await vi.waitFor(() => expect(onState).toHaveBeenCalledWith(state(7)));
    expect(resyncs()).toBe(1);

    fake.emit("track.started", event("track.started", 8, { title: "A" }));
    fake.emit("queue.changed", event("queue.changed", 9));
    expect(resyncs()).toBe(1);

    // Llega la 11 después de la 9: se perdió la 10. La API ya está en la 11.
    current.body = state(11);
    fake.emit("track.failed", event("track.failed", 11, { title: "B" }));
    await vi.waitFor(() => expect(resyncs()).toBe(2));
    expect(onEvent).toHaveBeenCalledTimes(3);

    // El latido del reproductor también avisa de una versión que creció (plan D3).
    current.body = state(14);
    realtime.observeVersion(14);
    await vi.waitFor(() => expect(resyncs()).toBe(3));

    // Y tras reconectar se pide de nuevo, porque se pudo perder cualquier evento.
    fake.emit("connect");
    await vi.waitFor(() => expect(resyncs()).toBe(4));
  });

  it("F002_R014 una sesión nueva empieza en la versión 0 y no cuenta como salto", async () => {
    const { current, fake, realtime, onState, resyncs } = setUp(20);
    fake.emit("connect");
    await vi.waitFor(() => expect(resyncs()).toBe(1));
    fake.emit("session.closed", event("session.closed", 21));

    // El propietario abre otra sesión: sus versiones empiezan de nuevo.
    fake.emit("session.opened", event("session.opened", 0, {}, "s2"));
    fake.emit("player.claimed", event("player.claimed", 1, { epoch: 1 }, "s2"));
    fake.emit("queue.changed", event("queue.changed", 2, {}, "s2"));
    expect(resyncs()).toBe(1);

    // Dentro de la sesión nueva, un salto se detecta igual (por evento o por el latido).
    current.body = state(4, "s2");
    fake.emit("queue.changed", event("queue.changed", 4, {}, "s2"));
    await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith(state(4, "s2")));
    expect(resyncs()).toBe(2);
    realtime.observeVersion(4);
    expect(resyncs()).toBe(2);
    // Una sola versión más en el latido ya es un evento que no llegó.
    current.body = state(5, "s2");
    realtime.observeVersion(5);
    await vi.waitFor(() => expect(resyncs()).toBe(3));
  });

  it("F002_R014 un salto durante una resincronización la repite sin retroceder la versión", async () => {
    // La primera petición devuelve la 7; las siguientes, lo último de la API.
    const answers = [state(7), state(9)];
    const api = fakeApi({
      "GET /api/owner/music-session": () => ({ status: 200, body: answers.length > 1 ? answers.shift() : answers[0] }),
    });
    const fake = fakeSocket();
    const realtime = createRealtimeClient({ source: ownerSource(api.client, "owner"), connect: fake.connect });
    const onState = vi.fn();
    realtime.subscribe({ onState });
    const resyncs = () => api.sent.filter((request) => request.path === "/api/owner/music-session").length;

    fake.emit("connect");
    // Mientras se pide el estado, llega la 9 por el canal.
    fake.emit("queue.changed", event("queue.changed", 9));

    // La API dijo 7, más viejo que la 9 ya entregada: no se entrega y se pide otra vez.
    await vi.waitFor(() => expect(onState).toHaveBeenCalledWith(state(9)));
    expect(onState).not.toHaveBeenCalledWith(state(7));
    expect(resyncs()).toBe(2);

    // Ya se vio la 9: la 10 no es un salto.
    fake.emit("queue.changed", event("queue.changed", 10));
    expect(resyncs()).toBe(2);

    // Dos saltos seguidos con una petición en curso: se repite una vez al terminar.
    answers[0] = state(25);
    realtime.observeVersion(20);
    realtime.observeVersion(25);
    await vi.waitFor(() => expect(resyncs()).toBe(4));
    expect(onState).toHaveBeenLastCalledWith(state(25));
  });

  it("F002_R014 si la API sigue devolviendo un estado viejo, deja de pedirlo", async () => {
    const { fake, onState, resyncs } = setUp(5);
    fake.emit("connect");
    fake.emit("queue.changed", event("queue.changed", 9));

    await vi.waitFor(() => expect(resyncs()).toBe(3));
    // Unas vueltas del bucle de eventos bastan para ver que no hay una cuarta petición.
    for (let turn = 0; turn < 10; turn++) await Promise.resolve();
    expect(resyncs()).toBe(3);
    expect(onState).not.toHaveBeenCalled();
  });

  it("F002_R014 una sesión que se abre durante una resincronización no se pisa con la anterior", async () => {
    // La primera petición aún ve la sesión s1; las siguientes, la nueva s2.
    const answers = [state(20, "s1"), state(0, "s2")];
    const api = fakeApi({
      "GET /api/owner/music-session": () => ({ status: 200, body: answers.length > 1 ? answers.shift() : answers[0] }),
    });
    const fake = fakeSocket();
    const realtime = createRealtimeClient({ source: ownerSource(api.client, "owner"), connect: fake.connect });
    const onState = vi.fn();
    realtime.subscribe({ onState });

    fake.emit("connect");
    // Mientras se pide el estado, se abre la sesión s2.
    fake.emit("session.opened", event("session.opened", 0, {}, "s2"));

    await vi.waitFor(() => expect(onState).toHaveBeenCalledWith(state(0, "s2")));
    expect(onState).not.toHaveBeenCalledWith(state(20, "s1"));

    // Sigue siendo s2: un salto en s2 se detecta. La API ya está en la 3.
    answers[0] = state(3, "s2");
    fake.emit("queue.changed", event("queue.changed", 1, {}, "s2"));
    fake.emit("queue.changed", event("queue.changed", 3, {}, "s2"));
    const resyncs = () => api.sent.filter((request) => request.path === "/api/owner/music-session").length;
    await vi.waitFor(() => expect(resyncs()).toBe(3));
  });

  it("F002_R008 entrega queue.changed a los suscriptores", () => {
    const { client } = fakeApi({});
    const fake = fakeSocket();
    const realtime = createRealtimeClient({ source: ownerSource(client, "player"), connect: fake.connect });
    const first = vi.fn();
    const second = vi.fn();
    realtime.subscribe({ onEvent: first });
    const unsubscribe = realtime.subscribe({ onEvent: second });

    fake.emit("queue.changed", event("queue.changed", 1));
    unsubscribe();
    fake.emit("queue.changed", event("queue.changed", 2));
    // Un mensaje sin la forma de un evento no se entrega.
    fake.emit("queue.changed", { session_id: "s1", version: "3" });

    expect(first.mock.calls.map(([received]) => (received as SessionEvent).version)).toEqual([1, 2]);
    expect(second.mock.calls.map(([received]) => (received as SessionEvent).version)).toEqual([1]);

    // Al cerrar se desconecta y nadie más recibe nada.
    realtime.close();
    expect(fake.socket.disconnect).toHaveBeenCalled();
    fake.emit("queue.changed", event("queue.changed", 3));
    expect(first).toHaveBeenCalledTimes(2);
  });

  it("F003_R010 el cliente de tiempo real usa el ticket y el estado que recibe", async () => {
    const music = "/api/public/establishments/ABC123/music";
    const ticketPath = "/api/public/establishments/ABC123/realtime-ticket";
    const clientState = (free: number) => ({
      status: "open",
      now_playing: { title: "Suena" },
      mine: [],
      quota: { limit: 5, free },
    });
    // Cada petición de estado devuelve el cupo siguiente: 5, 4, 3…
    let free = 6;
    const api = fakeApi({
      [`POST ${ticketPath}`]: { status: 200, body: { ticket: "tc", expires_in: 60 } },
      [`GET ${music}`]: () => ({ status: 200, body: clientState(--free) }),
    });
    const fake = fakeSocket();
    const realtime = createRealtimeClient({ source: clientSource(api.client, "ABC123"), connect: fake.connect });
    const onEvent = vi.fn();
    const onState = vi.fn();
    realtime.subscribe({ onEvent, onState });
    const fetches = () => api.sent.filter((request) => request.path === music).length;

    // El ticket sale de la ruta pública del establecimiento, sin rol: lo pone la API.
    expect(await fake.attempt()).toEqual({ ticket: "tc" });
    expect(api.sent).toContainEqual({ method: "POST", path: ticketPath, body: undefined });
    expect(api.sent.some((request) => request.path.startsWith("/api/owner/"))).toBe(false);

    // Al conectar, entrega el estado del cliente.
    fake.emit("connect");
    await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith(clientState(5)));

    // Su estado no lleva versión: lo vuelve a pedir tras cada evento, sin salto de versión.
    fake.emit("queue.changed", event("queue.changed", 1));
    await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith(clientState(4)));
    expect(onEvent).toHaveBeenCalledWith(event("queue.changed", 1));

    // Un evento mientras se pide el estado: se entrega esa respuesta y se pide otra.
    fake.emit("queue.changed", event("queue.changed", 2));
    fake.emit("queue.changed", event("queue.changed", 3));
    await vi.waitFor(() => expect(onState).toHaveBeenLastCalledWith(clientState(2)));
    expect(fetches()).toBe(4);

    // Los demás eventos que cambian lo que ve (D6) también lo piden, cada uno una vez.
    const others = [
      event("track.started", 4, { title: "Otra" }),
      event("track.failed", 5, { title: "Rota" }),
      event("session.closed", 6),
      event("session.opened", 0, {}, "s2"),
    ];
    for (const [index, other] of others.entries()) {
      fake.emit(other.type, other);
      await vi.waitFor(() => expect(fetches()).toBe(5 + index));
    }
    // Reclamar el reproductor no le cambia nada al cliente: no lo pide.
    fake.emit("player.claimed", event("player.claimed", 1, { epoch: 1 }, "s2"));
    await Promise.resolve();
    expect(fetches()).toBe(8);
    await vi.waitFor(() => expect(onState).toHaveBeenCalledTimes(8));
  });

  it("sin ticket del establecimiento, el intento de conexión va sin él", async () => {
    const { client } = fakeApi({
      "POST /api/public/establishments/ABC123/realtime-ticket": { status: 401, body: { error: "device_required" } },
    });
    const fake = fakeSocket();
    createRealtimeClient({ source: clientSource(client, "ABC123"), connect: fake.connect });

    expect(await fake.attempt()).toEqual({ ticket: undefined });
  });
});
