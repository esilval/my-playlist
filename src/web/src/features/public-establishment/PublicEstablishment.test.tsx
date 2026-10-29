import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api/client";
import { ApiProvider } from "../../api/context";
import type { AuthCallback, SocketLike } from "../../realtime/client";
import { fakeApi, type FakeResponse } from "../../test/fake-api";
import { renderRoute } from "../../test/render-route";
import { PublicEstablishment } from "./PublicEstablishment";

const CLOSED_MUSIC = { status: 200, body: { status: "closed", now_playing: null, mine: [], quota: { limit: 5, free: 5 } } };

describe("página pública del establecimiento", () => {
  it("F001_R012 muestra el nombre sin pedir registro", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/establishments/ABCDEFGHJK": { status: 200, body: { name: "Café Ñandú" } },
      "GET /api/public/establishments/ABCDEFGHJK/music": CLOSED_MUSIC,
    });
    renderRoute("/l/ABCDEFGHJK", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Café Ñandú");
    await screen.findByText("En este momento no se pueden pedir canciones.");
    // Nada que pida registrarse, entrar o instalar: ni formularios ni enlaces.
    expect(document.querySelector("form, input, button")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    // Solo el nombre y el estado de la música, que no piden nada al cliente.
    expect(sent).toEqual([
      { method: "GET", path: "/api/public/establishments/ABCDEFGHJK", body: undefined },
      { method: "GET", path: "/api/public/establishments/ABCDEFGHJK/music", body: undefined },
    ]);
  });

  it("F001_R013 muestra establecimiento no encontrado ante 404 sin otros datos", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/ZZZZZZZZZZ": { status: 404, body: { error: "not_found" } },
    });
    renderRoute("/l/ZZZZZZZZZZ", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Establecimiento no encontrado",
    );
    // Solo el aviso: ni el código pedido ni datos de ningún local.
    expect(screen.getByRole("main")).toHaveTextContent(
      "Establecimiento no encontradoRevisa que el enlace o el código QR estén completos.",
    );
  });

  it("F001_R013 un código con caracteres especiales se envía codificado", async () => {
    const { client, sent } = fakeApi({
      "GET /api/public/establishments/a%2Fb%20c": { status: 404, body: { error: "not_found" } },
    });
    renderRoute("/l/a%2Fb%20c", client);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Establecimiento no encontrado",
    );
    expect(sent[0]?.path).toBe("/api/public/establishments/a%2Fb%20c");
  });

  it("un fallo del servidor no se confunde con un establecimiento inexistente", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/ABCDEFGHJK": { status: 500 },
    });
    renderRoute("/l/ABCDEFGHJK", client);

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    expect(screen.queryByText("Establecimiento no encontrado")).not.toBeInTheDocument();
  });

  it("F001_R013 al cambiar de código no se ve el nombre del anterior", async () => {
    const { client } = fakeApi({
      "GET /api/public/establishments/AAAAAAAAAA": { status: 200, body: { name: "Bar A" } },
      "GET /api/public/establishments/AAAAAAAAAA/music": CLOSED_MUSIC,
      "GET /api/public/establishments/BBBBBBBBBB": { status: 200, body: { name: "Café B" } },
      "GET /api/public/establishments/BBBBBBBBBB/music": CLOSED_MUSIC,
    });
    const router = renderRoute("/l/AAAAAAAAAA", client);
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Bar A");

    await act(() => router.navigate("/l/BBBBBBBBBB"));

    expect(screen.queryByText("Bar A")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Café B");
  });
});

// Socket falso: conecta en cuanto tiene ticket y deja emitir eventos de la sala.
function fakeSocket() {
  const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
  const emit = (event: string, payload?: unknown) => {
    for (const listener of listeners.get(event) ?? []) listener(payload);
  };
  const socket = {
    active: false as boolean,
    on(event: string, listener: (...args: unknown[]) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
  } satisfies SocketLike;
  const connect = vi.fn((auth: AuthCallback) => {
    auth(() => queueMicrotask(() => emit("connect")));
    return socket;
  });
  return { connect, emit };
}

const BASE = "/api/public/establishments/ABC123";
const track = (n: number) => ({ ref: `fake:son-${n}`, title: `Canción ${n}`, author: `Autor ${n}` });

// El establecimiento ABC123, abierto, con el estado del cliente que guarda `server`.
function setUp(
  handlers: Record<string, FakeResponse | ((body: unknown) => FakeResponse)> = {},
  { holdFirstMusic = false } = {},
) {
  const server = {
    status: "open" as "open" | "closed",
    nowPlaying: null as string | null,
    mine: [] as { item_id: string; title: string }[],
  };
  const music = () => ({
    status: 200,
    body: {
      status: server.status,
      now_playing: server.nowPlaying ? { title: server.nowPlaying } : null,
      mine: server.mine,
      quota: { limit: 5, free: 5 - server.mine.length },
    },
  });
  const api = fakeApi({
    [`GET ${BASE}`]: { status: 200, body: { name: "Café Ñandú" } },
    [`GET ${BASE}/music`]: music,
    [`POST ${BASE}/realtime-ticket`]: { status: 200, body: { ticket: "tc", expires_in: 60 } },
    ...handlers,
  });
  // Si se pide, la respuesta a la primera petición de estado (la de la carga inicial) se
  // retiene hasta `release`: llega después de otras más nuevas.
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  let musicRequests = 0;
  const client = holdFirstMusic
    ? createApiClient({
        fetch: async (input) => {
          const response = api.fetch(input as Request);
          const first = new URL((input as Request).url).pathname === `${BASE}/music` && musicRequests++ === 0;
          if (first) await held;
          return response;
        },
      })
    : api.client;
  const socket = fakeSocket();
  render(
    <ApiProvider client={client}>
      <MemoryRouter initialEntries={["/l/ABC123"]}>
        <Routes>
          <Route path="/l/:code" element={<PublicEstablishment connect={socket.connect} />} />
        </Routes>
      </MemoryRouter>
    </ApiProvider>,
  );
  const searches = () => api.sent.filter((request) => request.path === `${BASE}/search`).length;
  return { ...api, server, socket, searches, release };
}

async function search(text: string) {
  fireEvent.change(await screen.findByLabelText("Canción, artista o álbum"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
}

const rejected = (status: number, error: string) => ({ status, body: { error } });

describe("página del cliente (feature 003)", () => {
  it("F003_R001 con la sesión abierta muestra el nombre y el buscador", async () => {
    setUp();

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Café Ñandú");
    expect(await screen.findByRole("search")).toBeInTheDocument();
    expect(screen.getByLabelText("Canción, artista o álbum")).toBeInTheDocument();
    // Sin registro ni datos personales: el único campo es el del buscador.
    expect(document.querySelectorAll("input")).toHaveLength(1);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Te quedan 5 de 5.")).toBeInTheDocument();
  });

  it("F003_R003 muestra los resultados con título y autor, o que no hay", async () => {
    let results = [track(1), track(2)];
    setUp({ [`GET ${BASE}/search`]: () => ({ status: 200, body: { results } }) });

    await search("son");
    const list = await screen.findByRole("list", { name: "Resultados" });
    expect(within(list).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Canción 1 · Autor 1 Pedir",
      "Canción 2 · Autor 2 Pedir",
    ]);

    results = [];
    await search("nada");
    expect(await screen.findByText("No se encontraron canciones.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Resultados" })).not.toBeInTheDocument();
  });

  it("F003_R003 solo busca al pulsar Buscar, no mientras se escribe", async () => {
    const { fetch, searches } = setUp({ [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1)] } } });
    const input = await screen.findByLabelText("Canción, artista o álbum");

    for (const text of ["s", "so", "son"]) fireEvent.change(input, { target: { value: text } });
    await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
    expect(searches()).toBe(0);

    // Un texto en blanco tampoco se busca.
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(searches()).toBe(0);

    await search("  son ");
    await screen.findByRole("list", { name: "Resultados" });
    expect(searches()).toBe(1);
    // Se busca el texto sin los espacios de los extremos.
    const urls = fetch.mock.calls.map(([input]) => new URL((input as Request).url));
    expect(urls.find((url) => url.pathname === `${BASE}/search`)?.searchParams.get("q")).toBe("son");
  });

  it("F003_R005 pedir muestra la canción entre las mías y el cupo actualizado", async () => {
    const { server, sent } = setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1), track(2)] } },
      [`POST ${BASE}/requests`]: (body) => {
        const { ref } = body as { ref: string };
        server.mine = [...server.mine, { item_id: `i-${ref}`, title: ref === "fake:son-2" ? "Canción 2" : "Canción 1" }];
        return { status: 201, body: { mine: server.mine, quota: { limit: 5, free: 5 - server.mine.length } } };
      },
    });
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 2»" }));

    expect(await screen.findByText("Pediste «Canción 2».")).toBeInTheDocument();
    const mine = screen.getByRole("list", { name: "Tus canciones pendientes" });
    expect(within(mine).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Canción 2"]);
    expect(screen.getByText("Te quedan 4 de 5.")).toBeInTheDocument();
    // Se pide por la referencia del resultado: el título lo pone el servidor.
    expect(sent.find((request) => request.path === `${BASE}/requests`)?.body).toEqual({ ref: "fake:son-2" });
  });

  it("F003_R006 con el cupo lleno avisa de cuándo lo recupera", async () => {
    const { server } = setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(6)] } },
      [`POST ${BASE}/requests`]: rejected(409, "quota_exceeded"),
    });
    server.mine = [1, 2, 3, 4, 5].map((n) => ({ item_id: `i${n}`, title: `Canción ${n}` }));
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 6»" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ya tienes 5 canciones pedidas, el máximo. Recuperarás un cupo cuando empiece a sonar una de las tuyas.",
    );
    expect(screen.getByText("Te quedan 0 de 5.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Tus canciones pendientes" })).getAllByRole("listitem")).toHaveLength(5);
  });

  it("F003_R008 con la sesión cerrada avisa y no muestra el buscador", async () => {
    const { server, sent } = setUp();
    server.status = "closed";

    expect(await screen.findByRole("alert")).toHaveTextContent("En este momento no se pueden pedir canciones.");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Café Ñandú");
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
    expect(document.querySelector("input")).toBeNull();
    expect(sent.some((request) => request.path === `${BASE}/search`)).toBe(false);
  });

  it("F003_R008 si la sesión se cerró al pedir, avisa con el mismo texto y quita el buscador", async () => {
    setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1)] } },
      [`POST ${BASE}/requests`]: rejected(409, "no_open_session"),
    });
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 1»" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("En este momento no se pueden pedir canciones.");
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
  });

  it("F003_R009 avisa de que la canción ya está en la cola", async () => {
    setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1)] } },
      [`POST ${BASE}/requests`]: rejected(409, "already_queued"),
    });
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 1»" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esa canción ya está en la cola.");
    expect(screen.getByText("Te quedan 5 de 5.")).toBeInTheDocument();
  });

  it("F003_R010 al llegar queue.changed pide el estado y lo muestra", async () => {
    const { server, socket, sent } = setUp();
    server.nowPlaying = "Canción A";
    server.mine = [
      { item_id: "b", title: "Canción B" },
      { item_id: "c", title: "Canción C" },
    ];
    expect(await screen.findByText("Te quedan 3 de 5.")).toBeInTheDocument();
    expect(screen.getByText("Canción A")).toBeInTheDocument();
    // El ticket sale de la ruta pública, con la cookie del dispositivo.
    await waitFor(() => expect(sent.some((request) => request.path === `${BASE}/realtime-ticket`)).toBe(true));

    // Termina A y empieza B: ya no es de las pendientes y su cupo vuelve (R007).
    server.nowPlaying = "Canción B";
    server.mine = [{ item_id: "c", title: "Canción C" }];
    act(() => socket.emit("queue.changed", { session_id: "s1", version: 5 }));

    expect(await screen.findByText("Te quedan 4 de 5.")).toBeInTheDocument();
    expect(screen.getByText("Suena:")).toHaveTextContent("Suena: Canción B");
    const mine = screen.getByRole("list", { name: "Tus canciones pendientes" });
    expect(within(mine).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Canción C"]);
  });

  it("F003_R010 con la sesión cerrada se entera de que se abre, sin recargar", async () => {
    const { server, socket } = setUp();
    server.status = "closed";
    await screen.findByText("En este momento no se pueden pedir canciones.");

    server.status = "open";
    act(() => socket.emit("session.opened", { session_id: "s2", version: 0 }));

    expect(await screen.findByRole("search")).toBeInTheDocument();
  });

  it("F003_R010 no pide el ticket hasta que la carga inicial trae la cookie del dispositivo", async () => {
    const { sent, release } = setUp({}, { holdFirstMusic: true });
    const tickets = () => sent.filter((request) => request.path === `${BASE}/realtime-ticket`).length;
    await waitFor(() => expect(sent.some((request) => request.path === `${BASE}/music`)).toBe(true));
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(tickets()).toBe(0);

    await act(async () => release());

    await waitFor(() => expect(tickets()).toBe(1));
  });

  it("F003_R012 avisa de que la búsqueda no está disponible", async () => {
    setUp({ [`GET ${BASE}/search`]: rejected(503, "search_unavailable") });

    await search("son");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La búsqueda no está disponible en este momento. Inténtalo de nuevo.",
    );
    expect(screen.getByText("Te quedan 5 de 5.")).toBeInTheDocument();
  });

  it("F003_R013 avisa de que espere tras demasiadas búsquedas", async () => {
    setUp({ [`GET ${BASE}/search`]: rejected(429, "too_many_searches") });

    await search("son");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Hiciste muchas búsquedas seguidas. Espera un minuto y vuelve a buscar.",
    );
  });

  it("F003_R014 avisa de que la canción no está disponible y que elija otra", async () => {
    setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1)] } },
      [`POST ${BASE}/requests`]: rejected(422, "unknown_track"),
    });
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 1»" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esa canción no está disponible. Elige otra.");
    expect(screen.getByText("Te quedan 5 de 5.")).toBeInTheDocument();
  });

  it("F003_R008 si la sesión se cerró al buscar, avisa y quita el buscador", async () => {
    setUp({ [`GET ${BASE}/search`]: rejected(409, "no_open_session") });

    await search("son");

    expect(await screen.findByRole("alert")).toHaveTextContent("En este momento no se pueden pedir canciones.");
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
  });

  it("sin la cookie del dispositivo, pide recargar la página", async () => {
    setUp({ [`GET ${BASE}/search`]: rejected(401, "device_required") });

    await search("son");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos reconocer este dispositivo. Recarga la página y vuelve a intentarlo.",
    );
  });

  it("un fallo de conexión al buscar o pedir no se confunde con un rechazo", async () => {
    setUp({
      [`GET ${BASE}/search`]: { status: 200, body: { results: [track(1)] } },
      [`POST ${BASE}/requests`]: { status: 500 },
    });
    await search("son");

    fireEvent.click(await screen.findByRole("button", { name: "Pedir «Canción 1»" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    await waitFor(() => expect(screen.getByRole("button", { name: "Pedir «Canción 1»" })).toBeEnabled());
  });
});
