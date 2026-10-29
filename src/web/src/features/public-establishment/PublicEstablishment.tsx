// La página que abre el QR (R012, R013): sin registro, sin instalar nada y sin datos
// de más. Es la entrada de C5.
//
// Con la sesión de música abierta, el cliente busca y pide canciones, y ve lo que suena,
// sus pendientes y su cupo, que se actualizan solos (feature 003, plan D7). Con la
// sesión cerrada, un aviso sin buscador (R008); sigue escuchando la sala para enterarse
// de que se abre.
import { useEffect, useState } from "react";
import { useParams } from "react-router";

import { useApi } from "../../api/context";
import { CONNECTION_ERROR } from "../../api/errors";
import type { ClientMusicState, Connect } from "../../realtime/client";
import { useClientRoomEvents } from "../../realtime/useRoomEvents";
import { MyRequests } from "./MyRequests";
import { SongSearch } from "./SongSearch";
import { useClientMusic, type Rejection } from "./useClientMusic";

type PageState =
  | { status: "loading" }
  | { status: "found"; name: string }
  | { status: "not_found" }
  | { status: "error" };

interface Props {
  /** Para las pruebas: un socket falso. */
  connect?: Connect;
}

const CLOSED_NOTICE = "En este momento no se pueden pedir canciones.";

// Un aviso por código de error de la API (D7).
const NOTICES: Record<Rejection, string> = {
  quota_exceeded:
    "Ya tienes 5 canciones pedidas, el máximo. Recuperarás un cupo cuando empiece a sonar una de las tuyas.",
  already_queued: "Esa canción ya está en la cola.",
  unknown_track: "Esa canción no está disponible. Elige otra.",
  search_unavailable: "La búsqueda no está disponible en este momento. Inténtalo de nuevo.",
  too_many_searches: "Hiciste muchas búsquedas seguidas. Espera un minuto y vuelve a buscar.",
  device_required: "No pudimos reconocer este dispositivo. Recarga la página y vuelve a intentarlo.",
  error: CONNECTION_ERROR,
};

export function PublicEstablishment({ connect }: Props) {
  const { code = "" } = useParams();
  // Una página nueva por código: nunca se ve el nombre de otro local mientras carga (R013).
  return <EstablishmentPage key={code} code={code} connect={connect} />;
}

function EstablishmentPage({ code, connect }: { code: string; connect?: Connect }) {
  const api = useApi();
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api.GET("/api/public/establishments/{code}", { params: { path: { code } } }).then(
      ({ data, response }) => {
        if (!active) return;
        if (data) setState({ status: "found", name: data.name });
        else if (response.status === 404) setState({ status: "not_found" });
        else setState({ status: "error" });
      },
      () => {
        if (active) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [api, code]);

  if (state.status === "loading") {
    return (
      <main>
        <p role="status">Cargando…</p>
      </main>
    );
  }
  if (state.status === "not_found") {
    return (
      <main>
        <h1>Establecimiento no encontrado</h1>
        <p>Revisa que el enlace o el código QR estén completos.</p>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main>
        <p role="alert">{CONNECTION_ERROR}</p>
      </main>
    );
  }
  return (
    <main>
      <h1>{state.name}</h1>
      <p>Te damos la bienvenida a {state.name}.</p>
      <ClientMusic code={code} connect={connect} />
    </main>
  );
}

// La sala solo se abre tras la carga inicial: esa respuesta trae la cookie del
// dispositivo, sin la que la API no da el ticket (D3, D6).
function ClientRoom({ code, connect, onState }: { code: string; connect?: Connect; onState(state: ClientMusicState): void }) {
  useClientRoomEvents(code, { onState }, connect);
  return null;
}

function ClientMusic({ code, connect }: { code: string; connect?: Connect }) {
  const { view, notice, search, request, onState } = useClientMusic(code);

  if (view.status === "loading") return <p role="status">Cargando la música…</p>;
  const room = <ClientRoom code={code} connect={connect} onState={onState} />;
  if (view.status === "error") return <>{room}<p role="alert">{CONNECTION_ERROR}</p></>;
  if (view.status === "closed") return <>{room}<p role="alert">{CLOSED_NOTICE}</p></>;
  return (
    <>
      {room}
      <MyRequests nowPlaying={view.nowPlaying} mine={view.mine} quota={view.quota} />
      {notice?.kind === "requested" && <p role="status">Pediste «{notice.title}».</p>}
      {notice && notice.kind !== "requested" && <p role="alert">{NOTICES[notice.kind]}</p>}
      <SongSearch onSearch={search} onRequest={request} />
    </>
  );
}
