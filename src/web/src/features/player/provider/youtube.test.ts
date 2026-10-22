import { describe, expect, it, vi } from "vitest";

import {
  createYouTubeProvider,
  videoIdOf,
  type YouTubeApi,
  type YouTubePlayer,
  type YouTubePlayerOptions,
} from "./youtube";

const A = "yt:AAAAAAAAAAA";
const B = "yt:BBBBBBBBBBB";
const C = "yt:CCCCCCCCCCC";

// IFrame Player API simulado: cada instancia anota lo que le piden y deja emitir sus
// eventos. Como el real, avisa de que está lista después de construirse.
class FakePlayer implements YouTubePlayer {
  calls: string[] = [];
  constructor(readonly options: YouTubePlayerOptions) {
    queueMicrotask(() => options.events.onReady());
  }
  loadVideoById(id: string) {
    this.calls.push(`load ${id}`);
  }
  playVideo() {
    this.calls.push("play");
  }
  pauseVideo() {
    this.calls.push("pause");
  }
  stopVideo() {
    this.calls.push("stop");
  }
  seekTo(seconds: number) {
    this.calls.push(`seek ${seconds}`);
  }
  mute() {
    this.calls.push("mute");
  }
  unMute() {
    this.calls.push("unmute");
  }
  destroy() {
    this.calls.push("destroy");
  }
  state(data: number) {
    this.options.events.onStateChange({ data });
  }
  error(data: number) {
    this.options.events.onError({ data });
  }
}

async function setUp() {
  const players: FakePlayer[] = [];
  // Se llama con `new`, como el real: al devolver un objeto, `new` devuelve ese objeto.
  const Player = vi.fn(function (_element: HTMLElement, options: YouTubePlayerOptions) {
    const player = new FakePlayer(options);
    players.push(player);
    return player;
  });
  const api = { Player } as unknown as YouTubeApi;
  const events = { onPlaying: vi.fn(), onEnded: vi.fn(), onError: vi.fn() };
  const container = document.createElement("div");
  const provider = createYouTubeProvider(events, container, () => Promise.resolve(api));
  await vi.waitFor(() => expect(players).toHaveLength(2));
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  await settle();
  const visible = () =>
    [...container.children].map((element) => (element as HTMLElement).dataset.active === "true");
  return { provider, players, events, settle, visible };
}

describe("adaptador de YouTube", () => {
  it("F002_R005 youtube precarga la siguiente en la instancia libre y alterna", async () => {
    const { provider, players, events, settle, visible } = await setUp();
    const [first, second] = players as [FakePlayer, FakePlayer];

    provider.play(A);
    provider.load(B);
    await settle();
    expect(first.calls).toEqual(["unmute", "load AAAAAAAAAAA"]);
    // Se carga de verdad, en silencio, y se pausa al principio en cuanto empieza.
    expect(second.calls).toEqual(["mute", "load BBBBBBBBBBB"]);
    second.state(1);
    expect(second.calls).toEqual(["mute", "load BBBBBBBBBBB", "pause", "seek 0"]);
    expect(events.onPlaying).not.toHaveBeenCalled();
    expect(visible()).toEqual([true, false]);

    first.state(1);
    first.state(0);
    expect(events.onPlaying).toHaveBeenCalledWith(A);
    expect(events.onEnded).toHaveBeenCalledWith(A);

    // B estaba precargada: empieza en la otra instancia sin volver a cargarla.
    provider.play(B);
    await settle();
    expect(second.calls.slice(-2)).toEqual(["unmute", "play"]);
    expect(second.calls.filter((call) => call.startsWith("load"))).toHaveLength(1);
    expect(first.calls.at(-1)).toBe("stop");
    expect(visible()).toEqual([false, true]);
    second.state(1);
    expect(events.onPlaying).toHaveBeenLastCalledWith(B);

    // Ahora la libre es la primera: la siguiente se precarga ahí.
    provider.load(C);
    await settle();
    expect(first.calls.slice(-2)).toEqual(["mute", "load CCCCCCCCCCC"]);

    // Los eventos de la instancia libre no se toman por los de la que suena.
    first.state(1);
    expect(events.onPlaying).toHaveBeenCalledTimes(2);
  });

  it("F002_R005 una canción no precargada se carga en la instancia activa", async () => {
    const { provider, players, settle } = await setUp();
    const [first, second] = players as [FakePlayer, FakePlayer];

    provider.load(B);
    provider.play(A);
    await settle();

    expect(first.calls).toEqual(["unmute", "load AAAAAAAAAAA"]);
    expect(second.calls).toEqual(["mute", "load BBBBBBBBBBB"]);
  });

  it("F002_R007 youtube traduce los errores del IFrame en error", async () => {
    const { provider, players, events, settle } = await setUp();
    const [first, second] = players as [FakePlayer, FakePlayer];

    provider.play(A);
    await settle();
    first.error(150);
    expect(events.onError).toHaveBeenLastCalledWith(A, "not_embeddable");
    first.error(100);
    expect(events.onError).toHaveBeenLastCalledWith(A, "not_found");
    first.error(999);
    expect(events.onError).toHaveBeenLastCalledWith(A, "youtube_error_999");

    // La precargada falla mientras espera: no se avisa hasta que le toca sonar.
    provider.load(B);
    await settle();
    second.error(101);
    expect(events.onError).toHaveBeenCalledTimes(3);
    provider.play(B);
    await settle();
    expect(events.onError).toHaveBeenLastCalledWith(B, "not_embeddable");
    expect(second.calls).not.toContain("play");

    // Una referencia que no es de YouTube no se puede reproducir.
    provider.play("fake:3s");
    await settle();
    expect(events.onError).toHaveBeenLastCalledWith("fake:3s", "invalid_track_ref");
  });

  it("F002_R007 solo entiende referencias yt: con un id de video válido", () => {
    expect(videoIdOf(A)).toBe("AAAAAAAAAAA");
    expect(videoIdOf("yt:corto")).toBeNull();
    expect(videoIdOf("spotify:AAAAAAAAAAA")).toBeNull();
    expect(videoIdOf("AAAAAAAAAAA")).toBeNull();
  });
});
