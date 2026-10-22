import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../../api/context";
import type { AuthCallback, SocketLike } from "../../realtime/client";
import { fakeApi, type FakeResponse } from "../../test/fake-api";
import { STORAGE_KEY } from "./pendingReports";
import { Player } from "./Player";
import { DEFAULT_TIMING, TIMEOUT_REASON, type PlayerTiming } from "./PlayerController";
import { createFakeProvider } from "./provider/fake";
import type { PlaybackEvents } from "./provider";

type ItemState = "pending" | "playing" | "played" | "skipped";

interface Item {
  item_id: string;
  title: string;
  track_ref: string;
  state: ItemState;
}

// Servidor falso con las reglas de C2 (plan D3, D4): el avance lo decide él, los
// informes repetidos no cambian nada y una época vieja da 409.
function fakeServer(songs: [title: string, trackRef: string][]) {
  const server = {
    open: true,
    epoch: 0,
    version: 1,
    offline: false,
    loggedIn: true,
    items: [] as Item[],
    // Lo que pasa en el servidor justo antes de responder un informe.
    beforeReply: null as ((report: Record<string, unknown>) => void) | null,
    // Informes que se pierden por la red antes de llegar.
    lostReports: 0,
    // Lo que pasa en el servidor justo antes de responder a la puesta en marcha.
    beforeClaimReply: null as (() => void) | null,
  };
  const enqueue = (title: string, trackRef: string) => {
    server.items.push({ item_id: `item-${title}`, title, track_ref: trackRef, state: "pending" });
    server.version += 1;
  };
  for (const [title, ref] of songs) enqueue(title, ref);

  const track = (item: Item | undefined) =>
    item ? { item_id: item.item_id, title: item.title, track_ref: item.track_ref } : null;
  const playing = () => server.items.find((item) => item.state === "playing");
  const pending = () => server.items.filter((item) => item.state === "pending");
  const playNext = () => {
    const [first] = pending();
    if (first) first.state = "playing";
  };
  const progress = () => ({
    status: 200,
    body: { current: track(playing()), next: track(pending()[0]), version: server.version },
  });
  const refuse = (epoch: unknown): FakeResponse | null => {
    if (!server.open) return { status: 409, body: { error: "no_open_session" } };
    if (epoch !== server.epoch) return { status: 409, body: { error: "player_superseded" } };
    return null;
  };
  // Sin conexión, la petición no llega: `fetch` falla como lo haría el navegador.
  const online =
    (handler: (body: Record<string, unknown>) => FakeResponse) =>
    (body: unknown): FakeResponse => {
      if (server.offline) throw new TypeError("Failed to fetch");
      // La sesión iniciada se cerró (por ejemplo, al restablecer la contraseña): R015.
      if (!server.loggedIn) return { status: 401, body: { error: "unauthenticated" } };
      return handler((body ?? {}) as Record<string, unknown>);
    };

  const api = fakeApi({
    "GET /api/owner/music-session": online(() => ({
      status: 200,
      body: server.open
        ? {
            status: "open",
            session: {
              id: "s1",
              opened_at: "2026-10-21T20:00:00Z",
              version: server.version,
              now_playing: track(playing()),
              player_active: server.epoch > 0,
              failures: [],
            },
          }
        : { status: "closed", session: null },
    })),
    "POST /api/owner/realtime-ticket": online(() => ({ status: 200, body: { ticket: "t", expires_in: 60 } })),
    "POST /api/owner/music-session/player": online(() => {
      if (!server.open) return { status: 409, body: { error: "no_open_session" } };
      server.epoch += 1;
      if (!playing()) playNext();
      server.version += 1;
      const reply = {
        status: 200,
        body: { epoch: server.epoch, current: track(playing()), next: track(pending()[0]) },
      };
      server.beforeClaimReply?.();
      return reply;
    }),
    "POST /api/owner/music-session/player/events": online((body) => {
      if (server.lostReports > 0) {
        server.lostReports -= 1;
        throw new TypeError("Failed to fetch");
      }
      const refused = refuse(body.epoch);
      if (refused) return refused;
      const item = server.items.find((candidate) => candidate.item_id === body.item_id);
      if (!item) return { status: 404, body: { error: "not_found" } };
      if (item.state === "playing" && body.type !== "started") {
        item.state = body.type === "ended" ? "played" : "skipped";
        playNext();
        server.version += 1;
      }
      const reply = progress();
      server.beforeReply?.(body);
      return reply;
    }),
    "POST /api/owner/music-session/player/advance": online((body) => {
      const refused = refuse(body.epoch);
      if (refused) return refused;
      if (!playing() && pending().length > 0) {
        playNext();
        server.version += 1;
      }
      return progress();
    }),
    "POST /api/owner/music-session/player/heartbeat": online((body) => {
      return refuse(body.epoch) ?? { status: 200, body: { version: server.version } };
    }),
  });

  const reports = () =>
    api.sent
      .filter((request) => request.path.endsWith("/player/events"))
      .map((request) => request.body as { item_id: string; type: string; reason?: string });
  const states = () => server.items.map((item) => [item.title, item.state]);
  return { ...api, server, enqueue, reports, states };
}

// Socket falso: deja conectar y emitir eventos de la sala.
function fakeSocket() {
  const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
  const socket = {
    active: false as boolean,
    on(event: string, listener: (...args: unknown[]) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
  } satisfies SocketLike;
  return {
    connect: (auth: AuthCallback) => {
      auth(() => queueMicrotask(() => emit("connect")));
      return socket;
    },
    emit,
  };
  function emit(event: string, payload?: unknown) {
    for (const listener of listeners.get(event) ?? []) listener(payload);
  }
}

// Proveedor falso de verdad (D5), anotando qué se reproduce y qué se precarga.
function recordingProvider() {
  const played: string[] = [];
  const loaded: string[] = [];
  const stops = { count: 0 };
  const createProvider = (events: PlaybackEvents) => {
    const provider = createFakeProvider(events);
    return Promise.resolve({
      load(ref: string) {
        loaded.push(ref);
        provider.load(ref);
      },
      play(ref: string) {
        played.push(ref);
        provider.play(ref);
      },
      stop() {
        stops.count += 1;
        provider.stop();
      },
      destroy: () => provider.destroy(),
    });
  };
  return { played, loaded, stops, createProvider };
}

const FAST: Partial<PlayerTiming> = { failTimeoutMs: 300, heartbeatMs: 60_000, retryMs: 50 };

// Monta el reproductor contra un servidor falso. El reproductor usa su propio cliente
// de la API (D11) con el `fetch` falso. El cliente del contexto, que lleva a /entrar
// ante un 401, solo está para comprobar que no se usa: `navigate` no debe llamarse.
function mount(server: ReturnType<typeof fakeServer>, timing: Partial<PlayerTiming> = FAST) {
  const socket = fakeSocket();
  const provider = recordingProvider();
  const view = render(
    <ApiProvider client={server.client}>
      <MemoryRouter>
        <Player
          createProvider={provider.createProvider}
          connect={socket.connect}
          timing={timing}
          fetch={server.fetch}
        />
      </MemoryRouter>
    </ApiProvider>,
  );
  return { socket, provider, unmount: view.unmount };
}

function setUp(songs: [string, string][], timing: Partial<PlayerTiming> = FAST) {
  const server = fakeServer(songs);
  const { socket, provider, unmount } = mount(server, timing);
  const start = async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Poner en marcha" }));
  };
  const event = (type: string, extra: Record<string, unknown> = {}) =>
    socket.emit(type, { session_id: "s1", version: server.server.version, ...extra });
  return { ...server, socket, provider, start, event, unmount };
}

const nowPlaying = (title: string) =>
  waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(`Suena: ${title}`), {
    timeout: 2000,
  });

beforeEach(() => sessionStorage.clear());
afterEach(() => sessionStorage.clear());

describe("reproductor del local", () => {
  it("F002_R004 poner en marcha reproduce la primera pendiente", async () => {
    const { start, provider, sent, states } = setUp([
      ["A", "fake:5s"],
      ["B", "fake:5s"],
      ["C", "fake:5s"],
    ]);

    // No suena nada hasta pulsar el botón: el navegador no lo dejaría (D8).
    await screen.findByRole("button", { name: "Poner en marcha" });
    expect(provider.played).toEqual([]);

    await start();

    await nowPlaying("A");
    expect(provider.played).toEqual(["fake:5s"]);
    expect(sent.some((request) => request.path === "/api/owner/music-session/player")).toBe(true);
    // Mientras suena A, B ya está precargada (D5).
    expect(provider.loaded).toEqual(["fake:5s"]);
    expect(states()[0]).toEqual(["A", "playing"]);
  });

  it("F002_R005 al terminar informa ended y reproduce la siguiente", async () => {
    const { start, provider, reports, states } = setUp([
      ["A", "fake:150ms"],
      ["B", "fake:200ms"],
      ["C", "fake:5s"],
    ]);
    await start();

    await nowPlaying("A");
    await nowPlaying("B");
    await nowPlaying("C");

    expect(provider.played).toEqual(["fake:150ms", "fake:200ms", "fake:5s"]);
    await waitFor(() =>
      expect(reports().map((report) => [report.item_id, report.type])).toEqual([
        ["item-A", "started"],
        ["item-A", "ended"],
        ["item-B", "started"],
        ["item-B", "ended"],
        ["item-C", "started"],
      ]),
    );
    expect(states()).toEqual([
      ["A", "played"],
      ["B", "played"],
      ["C", "playing"],
    ]);
  });

  it("F002_R006 no reproduce una canción que el servidor ya dio por sonada", async () => {
    const { start, provider, server, states } = setUp([
      ["A", "fake:300ms"],
      ["B", "fake:b"],
      ["C", "fake:5s"],
    ]);
    await start();
    await nowPlaying("A");
    expect(provider.loaded).toContain("fake:b");

    // Mientras suena A, B deja de estar pendiente (ya sonó en esta sesión): aunque el
    // reproductor la tenía precargada, sigue lo que dice el servidor.
    const b = server.items.find((item) => item.title === "B");
    if (b) b.state = "played";
    await nowPlaying("C");

    expect(provider.played).toEqual(["fake:300ms", "fake:5s"]);
    expect(states()).toEqual([
      ["A", "played"],
      ["B", "played"],
      ["C", "playing"],
    ]);
  });

  it("F002_R007 sin sonar en 10 s informa failed y sigue", async () => {
    expect(DEFAULT_TIMING.failTimeoutMs).toBe(10_000);
    const { start, provider, reports, states } = setUp([
      ["A", "fake:silent"],
      ["B", "fake:error"],
      ["C", "fake:5s"],
    ]);
    await start();

    // A no llega a sonar en el límite (aquí 300 ms); B falla en el proveedor.
    await nowPlaying("C");

    expect(provider.played).toEqual(["fake:silent", "fake:error", "fake:5s"]);
    expect(reports().slice(0, 2)).toEqual([
      expect.objectContaining({ item_id: "item-A", type: "failed", reason: TIMEOUT_REASON }),
      expect.objectContaining({ item_id: "item-B", type: "failed", reason: "fake_error" }),
    ]);
    expect(states()).toEqual([
      ["A", "skipped"],
      ["B", "skipped"],
      ["C", "playing"],
    ]);
  });

  it("F002_R008 en espera no suena y reproduce al llegar queue.changed", async () => {
    const { start, provider, enqueue, event, sent } = setUp([]);
    await start();

    expect(await screen.findByText(/Esperando canciones/)).toBeInTheDocument();
    expect(provider.played).toEqual([]);

    // Entra D en la cola: el reproductor pide avanzar y la reproduce.
    enqueue("D", "fake:5s");
    event("queue.changed");
    await nowPlaying("D");

    expect(provider.played).toEqual(["fake:5s"]);
    expect(sent.filter((request) => request.path.endsWith("/player/advance"))).not.toHaveLength(0);
  });

  it("F002_R008 una canción que entra mientras se informa el ended también suena", async () => {
    const { start, server, enqueue, event } = setUp([["A", "fake:150ms"]]);
    // El servidor aplica el ended de A (la cola queda vacía) y, antes de que llegue su
    // respuesta, entra D: su queue.changed llega primero al reproductor.
    server.beforeReply = (report) => {
      if (report.type !== "ended") return;
      server.beforeReply = null;
      // El queue.changed del ended y el de D, con versiones seguidas: no hay ningún salto
      // que haga pedir el estado.
      event("queue.changed");
      enqueue("D", "fake:5s");
      event("queue.changed");
    };
    await start();

    await nowPlaying("A");
    await nowPlaying("D");
  });

  it("F002_R008 una canción que entra mientras se pone en marcha también suena", async () => {
    const { start, server, enqueue, event } = setUp([["A", "fake:5s"]]);
    await start();
    await nowPlaying("A");
    // Otro dispositivo toma el control y A termina allí: la cola queda vacía.
    server.epoch += 1;
    server.version += 1;
    event("player.claimed", { epoch: server.epoch });
    await screen.findByText("La música sigue en otro dispositivo.");
    const a = server.items.find((item) => item.title === "A");
    if (a) a.state = "played";

    // Con el socket ya conectado, se vuelve a poner en marcha aquí. La puesta en marcha
    // se confirma con la cola vacía y, antes de que llegue su respuesta, entra D: su
    // queue.changed llega primero, con versiones seguidas (ningún salto).
    server.beforeClaimReply = () => {
      server.beforeClaimReply = null;
      event("player.claimed", { epoch: server.epoch });
      enqueue("D", "fake:5s");
      event("queue.changed");
    };
    fireEvent.click(screen.getByRole("button", { name: "Poner en marcha aquí" }));

    await nowPlaying("D");
  });

  it("F002_R008 un salto de versión en el latido hace pedir el estado", async () => {
    const { start, enqueue, sent } = setUp([], { ...FAST, heartbeatMs: 100 });
    await start();
    expect(await screen.findByText(/Esperando canciones/)).toBeInTheDocument();
    const stateRequests = () =>
      sent.filter((request) => request.path === "/api/owner/music-session").length;
    await waitFor(() => expect(stateRequests()).toBe(2)); // al abrir y al conectar
    const before = stateRequests();

    // Entra una canción y su queue.changed se pierde: el latido trae la versión nueva.
    enqueue("D", "fake:5s");

    await waitFor(() => expect(stateRequests()).toBeGreaterThan(before), { timeout: 2000 });
    await nowPlaying("D");
  });

  it("F002_R009 sin sesión abierta lo indica y no reproduce", async () => {
    const { server, provider, sent } = (() => {
      const context = fakeServer([["A", "fake:5s"]]);
      context.server.open = false;
      const provider = recordingProvider();
      render(
        <ApiProvider client={context.client}>
          <MemoryRouter>
            <Player createProvider={provider.createProvider} connect={fakeSocket().connect} />
          </MemoryRouter>
        </ApiProvider>,
      );
      return { ...context, provider };
    })();

    expect(await screen.findByText(/No hay ninguna sesión de música abierta/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Poner en marcha" })).not.toBeInTheDocument();
    expect(provider.played).toEqual([]);
    expect(sent.map((request) => request.path)).toEqual(["/api/owner/music-session"]);
    expect(server.epoch).toBe(0);
  });

  it("F002_R010 ante player_superseded o player.claimed se detiene y lo indica", async () => {
    // Aviso por tiempo real: otro reproductor se puso en marcha (época 2).
    const first = setUp([
      ["A", "fake:5s"],
      ["B", "fake:5s"],
    ]);
    await first.start();
    await nowPlaying("A");
    first.event("player.claimed", { epoch: 2 });

    expect(await screen.findByText("La música sigue en otro dispositivo.")).toBeInTheDocument();
    expect(first.provider.stops.count).toBe(1);
  });

  it("F002_R010 ante player_superseded en el latido se detiene y lo indica", async () => {
    const { start, server, provider, reports } = setUp(
      [
        ["A", "fake:5s"],
        ["B", "fake:5s"],
      ],
      { ...FAST, heartbeatMs: 100 },
    );
    await start();
    await nowPlaying("A");

    // Otro reproductor tomó el control y el aviso no llegó: lo dice el latido.
    server.epoch += 1;

    expect(
      await screen.findByText("La música sigue en otro dispositivo.", {}, { timeout: 2000 }),
    ).toBeInTheDocument();
    expect(provider.stops.count).toBe(1);
    // Ya no informa de nada: la cola es del otro reproductor.
    const sentBefore = reports().length;
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(reports()).toHaveLength(sentBefore);
  });

  it("F002_R011 ante session.closed se detiene", async () => {
    const { start, event, server, provider } = setUp([
      ["A", "fake:5s"],
      ["B", "fake:5s"],
    ]);
    await start();
    await nowPlaying("A");

    server.open = false;
    event("session.closed");

    expect(await screen.findByText(/No hay ninguna sesión de música abierta/)).toBeInTheDocument();
    expect(provider.stops.count).toBe(1);
  });

  it("F002_R012 sin conexión guarda los informes en sessionStorage y los reenvía en orden", async () => {
    const { start, server, provider, reports, states } = setUp([
      ["A", "fake:300ms"],
      ["B", "fake:5s"],
    ]);
    await start();
    await nowPlaying("A");
    await waitFor(() => expect(reports()).toHaveLength(1)); // el started de A

    // Se corta la conexión y A termina: el ended queda guardado y B no empieza.
    server.offline = true;
    expect(await screen.findByRole("alert", {}, { timeout: 2000 })).toBeInTheDocument();
    await waitFor(() =>
      expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([
        expect.objectContaining({ item_id: "item-A", type: "ended", epoch: 1 }),
      ]),
    );
    expect(provider.played).toEqual(["fake:300ms"]);
    expect(states()[0]).toEqual(["A", "playing"]);

    // Vuelve la conexión: el ended llega, en orden, y suena B; A no se repite.
    server.offline = false;
    await nowPlaying("B");

    expect(provider.played).toEqual(["fake:300ms", "fake:5s"]);
    expect(states()).toEqual([
      ["A", "played"],
      ["B", "playing"],
    ]);
    // Durante el corte se reintenta el ended (los intentos fallidos también cuentan aquí),
    // nunca el started ni nada de B antes de tiempo.
    const [first, ...retries] = reports().filter((report) => report.item_id === "item-A");
    expect(first?.type).toBe("started");
    expect(retries.length).toBeGreaterThan(1);
    expect(new Set(retries.map((report) => report.type))).toEqual(new Set(["ended"]));
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("F002_R012 al reconectar sin informes pendientes comprueba enseguida si sigue al mando", async () => {
    const { start, server, socket, provider, reports } = setUp([
      ["A", "fake:5s"],
      ["B", "fake:5s"],
    ]);
    await start();
    await nowPlaying("A");
    await waitFor(() => expect(reports()).toHaveLength(1)); // el started de A

    // Durante un corte, con A sonando, otro reproductor toma el control y su
    // player.claimed se pierde. Al reconectar no hay informes que enviar, y el latido
    // normal tardaría 15 s (aquí 60 s): se comprueba al conectar.
    server.epoch += 1;
    socket.emit("connect");

    expect(
      await screen.findByText("La música sigue en otro dispositivo.", {}, { timeout: 1000 }),
    ).toBeInTheDocument();
    expect(provider.stops.count).toBe(1);
  });

  it("F002_R012 no pone en marcha hasta entregar los informes guardados, y uno viejo no lo detiene", async () => {
    // Al recargar quedó un informe de una puesta en marcha anterior, y no llega.
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ epoch: 7, item_id: "item-X", type: "ended" }]),
    );
    const { start, server, reports, sent } = setUp([["A", "fake:5s"]]);
    server.lostReports = 1;
    await start();

    // Sin entregarlo no se pone en marcha: lo indica y deja volver a intentarlo.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(sent.some((request) => request.path === "/api/owner/music-session/player")).toBe(false);
    await start();

    await nowPlaying("A");
    await waitFor(() => expect(reports().some((report) => report.type === "started")).toBe(true));
    // El informe viejo se envió dos veces (la que se perdió y la que llegó), siempre con
    // su época: la API lo rechazó por ser de otra puesta en marcha, se descartó y no
    // detiene la música.
    expect(reports().filter((report) => report.item_id === "item-X")).toHaveLength(2);
    expect(screen.getByRole("status")).toHaveTextContent("Suena: A");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("F002_R012 al reconectar con player_superseded se detiene y descarta los informes", async () => {
    const { start, server, provider, states } = setUp([
      ["A", "fake:300ms"],
      ["B", "fake:5s"],
    ]);
    await start();
    await nowPlaying("A");

    // Sin conexión termina A; mientras tanto, otro reproductor toma el control.
    server.offline = true;
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).not.toBeNull(), {
      timeout: 2000,
    });
    server.epoch += 1;
    server.offline = false;

    expect(
      await screen.findByText("La música sigue en otro dispositivo.", {}, { timeout: 2000 }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(provider.played).toEqual(["fake:300ms"]);
    // El informe viejo no tocó la cola del otro reproductor.
    expect(states()[0]).toEqual(["A", "playing"]);
  });

  describe("cierre de la sesión iniciada (R015, D11)", () => {
    // A suena con B pendiente y, a mitad de A, se cierra la sesión iniciada del equipo: el
    // latido recibe un 401.
    async function loggedOutDuringA() {
      const context = setUp(
        [
          ["A", "fake:500ms"],
          ["B", "fake:5s"],
        ],
        { ...FAST, heartbeatMs: 100 },
      );
      await context.start();
      await nowPlaying("A");
      await waitFor(() => expect(context.reports()).toHaveLength(1)); // el started de A
      context.server.loggedIn = false;
      const closedAt = context.sent.length;
      // Requests enviadas tras el cierre de la sesión iniciada.
      const afterClose = () => context.sent.slice(closedAt);
      return { ...context, afterClose };
    }

    const loginNotice = () =>
      screen.findByText(/Tu sesión se cerró/, {}, { timeout: 2000 });

    it("F002_R015 ante un 401 termina la canción sin redirigir y no empieza la siguiente", async () => {
      const { navigate, provider, afterClose } = await loggedOutDuringA();
      // Un latido enviado ya sin sesión iniciada recibe el 401.
      await waitFor(() =>
        expect(afterClose().some((request) => request.path.endsWith("/heartbeat"))).toBe(true),
      );
      // Tras el 401 (con tiempo para procesar la respuesta), A sigue sonando.
      await new Promise((resolve) => setTimeout(resolve, 60));
      expect(screen.getByRole("status")).toHaveTextContent("Suena: A");
      expect(provider.stops.count).toBe(0);

      await loginNotice();

      expect(provider.played).toEqual(["fake:500ms"]);
      expect(navigate).not.toHaveBeenCalled();
    });

    it("F002_R015 al terminar guarda el ended y muestra el aviso con el enlace a entrar", async () => {
      const { states } = await loggedOutDuringA();

      await loginNotice();

      expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([
        expect.objectContaining({ item_id: "item-A", type: "ended", epoch: 1 }),
      ]);
      expect(screen.getByRole("link", { name: "Vuelve a iniciar sesión" })).toHaveAttribute(
        "href",
        "/entrar",
      );
      // La sesión de música sigue abierta, con B pendiente.
      expect(states()).toEqual([
        ["A", "playing"],
        ["B", "pending"],
      ]);
    });

    it("F002_R015 al poner en marcha entrega primero los informes guardados y suena la siguiente", async () => {
      const context = await loggedOutDuringA();
      await loginNotice();

      // Vuelve a iniciar sesión y abre otra vez el reproductor.
      context.server.loggedIn = true;
      context.unmount();
      const before = context.sent.length;
      const again = mount(context);
      fireEvent.click(await screen.findByRole("button", { name: "Poner en marcha" }));

      await nowPlaying("B");
      const after = context.sent.slice(before).map((request) => [request.path, request.body]);
      const ended = after.findIndex(([path]) => path === "/api/owner/music-session/player/events");
      const claim = after.findIndex(([path]) => path === "/api/owner/music-session/player");
      expect(ended).toBeGreaterThanOrEqual(0);
      expect(ended).toBeLessThan(claim);
      expect(after[ended]?.[1]).toMatchObject({ item_id: "item-A", type: "ended", epoch: 1 });
      // A no vuelve a sonar.
      expect(again.provider.played).toEqual(["fake:5s"]);
      expect(context.states()).toEqual([
        ["A", "played"],
        ["B", "playing"],
      ]);
      expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    });

    it("F002_R015 desde el aviso, tras entrar en otra pestaña, se pone en marcha y suena la siguiente", async () => {
      const context = await loggedOutDuringA();
      await loginNotice();

      context.server.loggedIn = true;
      fireEvent.click(screen.getByRole("button", { name: "Poner en marcha" }));

      await nowPlaying("B");
      expect(context.provider.played).toEqual(["fake:500ms", "fake:5s"]);
      expect(context.states()).toEqual([
        ["A", "played"],
        ["B", "playing"],
      ]);
    });

    it("F002_R013 al abrir el reproductor sin sesión iniciada lleva a entrar", async () => {
      const server = fakeServer([["A", "fake:5s"]]);
      server.server.loggedIn = false;
      render(
        <ApiProvider client={server.client}>
          <MemoryRouter initialEntries={["/panel/reproductor"]}>
            <Routes>
              <Route
                path="/panel/reproductor"
                element={<Player createProvider={recordingProvider().createProvider} fetch={server.fetch} />}
              />
              <Route path="/entrar" element={<p>Pantalla de entrar</p>} />
            </Routes>
          </MemoryRouter>
        </ApiProvider>,
      );

      expect(await screen.findByText("Pantalla de entrar")).toBeInTheDocument();
    });

    it("F002_R015 si los informes guardados reciben player_superseded se descartan y pone en marcha como en R010", async () => {
      const context = await loggedOutDuringA();
      await loginNotice();

      // Mientras tanto, otro reproductor tomó el control: A suena allí.
      context.server.epoch += 1;
      context.server.loggedIn = true;
      context.unmount();
      const before = context.sent.length;
      const again = mount(context);
      fireEvent.click(await screen.findByRole("button", { name: "Poner en marcha" }));

      // Como en R010: este reproductor toma el control y empieza A desde el principio.
      await nowPlaying("A");
      const reported = context.sent
        .slice(before)
        .filter((request) => request.path.endsWith("/player/events"));
      expect(reported[0]?.body).toMatchObject({ item_id: "item-A", type: "ended", epoch: 1 });
      expect(again.provider.played).toEqual(["fake:500ms"]);
      expect(context.states()[0]).toEqual(["A", "playing"]);
      expect(context.server.epoch).toBe(3);
      await waitFor(() =>
        expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]")).not.toContainEqual(
          expect.objectContaining({ epoch: 1 }),
        ),
      );
    });
  });
});
