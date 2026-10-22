// Reproductor del local en /panel/reproductor (plan D8, R004–R012).
//
// Los navegadores no dejan sonar nada sin una interacción, así que empieza con el botón
// «Poner en marcha». Desde ese momento escucha la sala del establecimiento (D6). La
// lógica vive en PlayerController; aquí solo se muestra su estado.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { api as defaultApi, createApiClient, LOGIN_PATH } from "../../api/client";
import { ApiProvider, useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import type { Connect } from "../../realtime/client";
import { useRoomEvents } from "../../realtime/useRoomEvents";
import { createPendingReports } from "./pendingReports";
import {
  createPlayerController,
  type PlayerController,
  type PlayerTiming,
  type PlayerView,
} from "./PlayerController";
import { createPlaybackProvider, type PlaybackEvents, type PlaybackProvider } from "./provider";

export interface PlayerProps {
  /** Para las pruebas: el proveedor falso en vez de elegirlo por el entorno. */
  createProvider?: (events: PlaybackEvents, container: HTMLElement) => Promise<PlaybackProvider>;
  /** Para las pruebas: un socket falso. */
  connect?: Connect;
  timing?: Partial<PlayerTiming>;
  /** Para las pruebas: el `fetch` del cliente propio del reproductor. */
  fetch?: typeof globalThis.fetch;
}

// Ante un 401, el reproductor no redirige: deja terminar la canción y pide volver a
// entrar (D11). Por eso tiene su propio cliente de la API, también para el ticket de
// tiempo real.
const stayHere = () => {};
const playerApi = createApiClient({ navigate: stayHere });

// Conectado a la sala solo mientras el reproductor está en marcha o lo estuvo.
function RoomLink({ controller, connect }: { controller: PlayerController; connect?: Connect }) {
  const room = useRoomEvents(
    "player",
    { onEvent: (event) => controller.onEvent(event), onState: (state) => controller.onState(state) },
    connect,
  );
  const { observeVersion } = room;
  useEffect(() => {
    controller.setVersionObserver(observeVersion);
    return () => controller.setVersionObserver(null);
  }, [controller, observeVersion]);
  return null;
}

function Status({ view, onStart }: { view: PlayerView; onStart: () => void }) {
  switch (view.status) {
    case "loading":
      return <p role="status">Cargando…</p>;
    case "ready":
      return (
        <>
          <p>Pon en marcha el reproductor en el equipo del local conectado a los altavoces.</p>
          <button type="button" onClick={onStart}>
            Poner en marcha
          </button>
        </>
      );
    case "starting":
      return <p role="status">Poniendo en marcha…</p>;
    case "playing":
      return (
        <p role="status">
          Suena: <strong>{view.title}</strong>
        </p>
      );
    case "advancing":
      return <p role="status">Pasando a la siguiente canción…</p>;
    case "waiting":
      return (
        <p role="status">Esperando canciones. La próxima que entre en la cola empezará sola.</p>
      );
    case "no_session":
      return (
        <p role="status">
          No hay ninguna sesión de música abierta. Ábrela desde el <Link to="/panel">panel</Link>{" "}
          para poner música.
        </p>
      );
    case "login_required":
      return (
        <>
          <p role="status">
            Tu sesión se cerró. <Link to={LOGIN_PATH}>Vuelve a iniciar sesión</Link> y pon en marcha el
            reproductor para seguir con la música.
          </p>
          <button type="button" onClick={onStart}>
            Poner en marcha
          </button>
        </>
      );
    case "superseded":
      return (
        <>
          <p role="status">La música sigue en otro dispositivo.</p>
          <button type="button" onClick={onStart}>
            Poner en marcha aquí
          </button>
        </>
      );
  }
}

export function Player({
  createProvider = createPlaybackProvider,
  connect,
  timing,
  fetch,
}: PlayerProps) {
  const contextApi = useApi();
  // El cliente propio, sin redirección. Solo si alguien sustituyó el de la app (una
  // prueba de rutas) se usa ese, para no salir a la red.
  const api = useMemo(() => {
    if (fetch) return createApiClient({ fetch, navigate: stayHere });
    return contextApi === defaultApi ? playerApi : contextApi;
  }, [contextApi, fetch]);
  const container = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<PlayerView>({ status: "loading", offline: false });
  const [controller, setController] = useState<PlayerController | null>(null);
  const [live, setLive] = useState(false);
  const navigate = useNavigate();
  const goToLogin = useRef(() => void navigate(LOGIN_PATH));
  // Se leen al crear el controlador: cambiarlos después no lo rehace.
  const settings = useRef({ createProvider, timing });

  useEffect(() => {
    const created = createPlayerController({
      api,
      createProvider: (events) => {
        if (!container.current) throw new Error("el reproductor no está montado");
        return settings.current.createProvider(events, container.current);
      },
      reports: createPendingReports(),
      onChange: setView,
      goToLogin: () => goToLogin.current(),
      timing: settings.current.timing,
    });
    setController(created);
    void created.check();
    return () => {
      created.destroy();
      setController(null);
      setLive(false);
    };
  }, [api]);

  const start = () => {
    if (!controller) return;
    setLive(true);
    void controller.start();
  };

  return (
    <main>
      <h1>Reproductor</h1>
      {view.offline && <p role="alert">{CONNECTION_ERROR}</p>}
      <Status view={view} onStart={start} />
      {/* El video se ve: las condiciones del IFrame de YouTube piden un reproductor visible. */}
      <div ref={container} style={{ width: "100%", maxWidth: "48rem", aspectRatio: "16 / 9" }} />
      {live && controller && (
        <ApiProvider client={api}>
          <RoomLink controller={controller} connect={connect} />
        </ApiProvider>
      )}
    </main>
  );
}
