import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../../api/context";
import type { AuthCallback, SocketLike } from "../../realtime/client";
import { fakeApi, type FakeResponse } from "../../test/fake-api";
import { MusicSessionCard } from "./MusicSessionCard";

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: "s1",
    opened_at: "2026-10-21T20:00:00Z",
    version: 3,
    now_playing: null,
    player_active: false,
    failures: [],
    ...overrides,
  };
}

const CLOSED = { status: 200, body: { status: "closed", session: null } };
const open = (overrides: Record<string, unknown> = {}) => ({
  status: 200,
  body: { status: "open", session: session(overrides) },
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
  return { connect, emit, socket };
}

function setUp(handlers: Record<string, FakeResponse | ((body: unknown) => FakeResponse)>) {
  const api = fakeApi({
    "POST /api/owner/realtime-ticket": { status: 200, body: { ticket: "t", expires_in: 60 } },
    ...handlers,
  });
  const socket = fakeSocket();
  render(
    <ApiProvider client={api.client}>
      <MemoryRouter>
        <MusicSessionCard connect={socket.connect} />
      </MemoryRouter>
    </ApiProvider>,
  );
  const stateRequests = () =>
    api.sent.filter((request) => request.method === "GET" && request.path === "/api/owner/music-session")
      .length;
  const event = (type: string, extra: Record<string, unknown> = {}) =>
    socket.emit(type, { session_id: "s1", version: 4, ...extra });
  return { ...api, socket, stateRequests, event };
}

describe("tarjeta de sesión de música", () => {
  it("F002_R001 abrir muestra la sesión abierta", async () => {
    const server = { open: false, version: 0 };
    const { sent, socket, stateRequests } = setUp({
      "GET /api/owner/music-session": () => (server.open ? open({ version: server.version }) : CLOSED),
      "POST /api/owner/music-session": () => {
        server.open = true;
        return { status: 201, body: { session: session({ version: 0 }) } };
      },
    });
    expect(await screen.findByText("La sesión de música está cerrada.")).toBeInTheDocument();
    await waitFor(() => expect(stateRequests()).toBe(2)); // al cargar y al conectar

    fireEvent.click(screen.getByRole("button", { name: "Abrir la sesión de música" }));

    expect(await screen.findByText("La sesión de música está abierta.")).toBeInTheDocument();
    expect(screen.getByText("La cola aún no tiene canciones.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar la sesión de música" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir el reproductor" })).toHaveAttribute(
      "href",
      "/panel/reproductor",
    );
    expect(sent.some((request) => request.method === "POST" && request.path === "/api/owner/music-session")).toBe(
      true,
    );

    // Al reconectar se vuelve a pedir el estado: la cola sigue vacía y el aviso sigue.
    socket.emit("connect");
    await waitFor(() => expect(stateRequests()).toBe(3));
    expect(screen.getByText("La sesión de música está abierta.")).toBeInTheDocument();
    expect(screen.getByText("La cola aún no tiene canciones.")).toBeInTheDocument();

    // Entra una canción y su queue.changed se pierde: el estado llega con otra versión
    // (aún no suena nada) y el aviso desaparece.
    server.version = 1;
    socket.emit("connect");
    await waitFor(() => expect(stateRequests()).toBe(4));
    await waitFor(() =>
      expect(screen.queryByText("La cola aún no tiene canciones.")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("La sesión de música está abierta.")).toBeInTheDocument();
  });

  it("F002_R002 sin verificar muestra el aviso con reenvío y sigue cerrada", async () => {
    const { sent } = setUp({
      "GET /api/owner/music-session": CLOSED,
      "POST /api/owner/music-session": { status: 403, body: { error: "email_not_verified" } },
      "POST /api/owner/email-verification/resend": { status: 202, body: { status: "check_email" } },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Abrir la sesión de música" }));

    expect(await screen.findByText(/primero verifica tu correo/)).toBeInTheDocument();
    expect(screen.getByText("La sesión de música está cerrada.")).toBeInTheDocument();
    expect(screen.queryByText("La sesión de música está abierta.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reenviar el enlace" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Te enviamos un enlace nuevo");
    expect(sent.at(-1)).toMatchObject({ method: "POST", path: "/api/owner/email-verification/resend" });
  });

  it("F002_R007 muestra el aviso de la canción que falló, también tras recargar", async () => {
    // Al cargar (por ejemplo, tras recargar la página) llegan los fallos guardados.
    const { event, stateRequests } = setUp({
      "GET /api/owner/music-session": open({
        failures: [{ title: "Canción B", failed_at: "2026-10-21T20:05:00Z" }],
      }),
    });
    const failures = await screen.findByRole("list", {
      name: "Canciones que no se pudieron reproducir",
    });
    expect(failures).toHaveTextContent("No se pudo reproducir «Canción B»; se saltó.");
    await waitFor(() => expect(stateRequests()).toBe(2)); // al cargar y al conectar

    // Y los nuevos llegan por tiempo real.
    event("track.failed", { item_id: "item-C", title: "Canción C" });

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(failures).toHaveTextContent("No se pudo reproducir «Canción C»; se saltó.");
  });

  it("F002_R011 cerrar muestra la sesión cerrada", async () => {
    const { sent, event } = setUp({
      "GET /api/owner/music-session": open({ now_playing: { item_id: "a", title: "A", track_ref: "yt:AAAAAAAAAAA" } }),
      "DELETE /api/owner/music-session": { status: 204 },
      "POST /api/owner/music-session": { status: 201, body: { session: session({ version: 0 }) } },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar la sesión de música" }));

    expect(await screen.findByText("La sesión de música está cerrada.")).toBeInTheDocument();
    expect(screen.queryByText(/Suena:/)).not.toBeInTheDocument();
    expect(sent.some((request) => request.method === "DELETE")).toBe(true);

    // Si la cierra otra pestaña, llega por tiempo real.
    fireEvent.click(screen.getByRole("button", { name: "Abrir la sesión de música" }));
    await screen.findByText("La sesión de música está abierta.");
    event("session.closed");
    expect(await screen.findByText("La sesión de música está cerrada.")).toBeInTheDocument();
  });

  it("F002_R014 muestra lo que suena y si hay reproductor activo, y se actualiza con track.started", async () => {
    const { event, stateRequests } = setUp({
      "GET /api/owner/music-session": open({
        now_playing: { item_id: "a", title: "Canción A", track_ref: "yt:AAAAAAAAAAA" },
        player_active: false,
      }),
    });
    expect(await screen.findByText("Canción A")).toBeInTheDocument();
    expect(screen.getByText(/No hay ningún reproductor activo/)).toBeInTheDocument();
    await waitFor(() => expect(stateRequests()).toBe(2));

    event("player.claimed", { epoch: 1 });
    expect(await screen.findByText(/El reproductor está en marcha/)).toBeInTheDocument();

    event("track.started", { item_id: "b", title: "Canción B", version: 5 });
    expect(await screen.findByText("Canción B")).toBeInTheDocument();
    expect(screen.queryByText("Canción A")).not.toBeInTheDocument();
  });

  it("F002_R014 se entera de una sesión que se abre en otro equipo", async () => {
    const server = { open: false };
    const { event, stateRequests } = setUp({
      "GET /api/owner/music-session": () => (server.open ? open({ version: 0 }) : CLOSED),
    });
    expect(await screen.findByText("La sesión de música está cerrada.")).toBeInTheDocument();
    await waitFor(() => expect(stateRequests()).toBe(2));

    server.open = true;
    event("session.opened", { version: 0 });

    expect(await screen.findByText("La sesión de música está abierta.")).toBeInTheDocument();
  });

  it("F002_R014 un estado viejo no pisa un evento más nuevo, y un fallo al recargar conserva la tarjeta", async () => {
    const answers: FakeResponse[] = [
      open({ version: 3, now_playing: { item_id: "a", title: "Canción A", track_ref: "yt:AAAAAAAAAAA" } }),
    ];
    const { event, socket, stateRequests } = setUp({
      "GET /api/owner/music-session": () => {
        const answer = answers.length > 1 ? answers.shift() : answers[0];
        if (!answer) throw new TypeError("Failed to fetch");
        return answer;
      },
    });
    expect(await screen.findByText("Canción A")).toBeInTheDocument();
    await waitFor(() => expect(stateRequests()).toBe(2));

    // Cambia la cola y, antes de que llegue el estado pedido, empieza B (versión 5): el
    // estado de la versión 4 ya es viejo.
    answers.unshift(
      open({ version: 4, now_playing: { item_id: "a", title: "Canción A", track_ref: "yt:AAAAAAAAAAA" } }),
    );
    event("queue.changed", { version: 4 });
    event("track.started", { item_id: "b", title: "Canción B", version: 5 });
    await waitFor(() => expect(stateRequests()).toBe(3));
    expect(await screen.findByText("Canción B")).toBeInTheDocument();
    expect(screen.queryByText("Canción A")).not.toBeInTheDocument();

    // Sin red al recargar: la tarjeta sigue con lo que tenía, con el aviso.
    answers.splice(0, answers.length);
    event("queue.changed", { version: 6 });
    expect(await screen.findByText(/No se pudo conectar con MyPlaylist/)).toBeInTheDocument();
    expect(screen.getByText("Canción B")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar la sesión de música" })).toBeInTheDocument();
    expect(socket.socket.disconnect).not.toHaveBeenCalled();
  });
});
