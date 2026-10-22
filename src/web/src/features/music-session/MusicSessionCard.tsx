// Tarjeta de la sesión de música en el panel (plan D7; R001, R002, R007, R011, R014).
//
// Abre y cierra la sesión. Escucha la sala del establecimiento (también con la sesión
// cerrada, para enterarse de que se abre en otro equipo) y muestra lo que suena, si hay
// un reproductor activo y las canciones que fallaron. Si no puede conectar al tiempo
// real, sigue funcionando con la API y se actualiza al recargar.
import { Link } from "react-router";

import { CONNECTION_ERROR } from "../../api/errors";
import type { Connect, RealtimeHandlers } from "../../realtime/client";
import { useRoomEvents } from "../../realtime/useRoomEvents";
import { ResendVerification } from "../shared/ResendVerification";
import { useMusicSession, type OpenSession } from "./useMusicSession";

interface Props {
  /** Para las pruebas: un socket falso. */
  connect?: Connect;
}

function SessionRoom({ handlers, connect }: { handlers: RealtimeHandlers; connect?: Connect }) {
  useRoomEvents("owner", handlers, connect);
  return null;
}

function OpenDetails({ session }: { session: OpenSession }) {
  return (
    <>
      <p>La sesión de música está abierta.</p>
      {session.fresh && <p>La cola aún no tiene canciones.</p>}
      <p>{session.nowPlaying ? <>Suena: <strong>{session.nowPlaying}</strong></> : "No suena nada."}</p>
      <p>
        {session.playerActive
          ? "El reproductor está en marcha."
          : "No hay ningún reproductor activo."}{" "}
        <Link to="/panel/reproductor">Abrir el reproductor</Link>
      </p>
      {/* Región viva sin rol: el aviso de un fallo nuevo se anuncia (R007). */}
      <div aria-live="polite">
        {session.failures.length > 0 && (
          <ul aria-label="Canciones que no se pudieron reproducir">
            {session.failures.map((failure) => (
              <li key={`${failure.failed_at}-${failure.title}`}>
                No se pudo reproducir «{failure.title}»; se saltó.
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

export function MusicSessionCard({ connect }: Props) {
  const { view, open, close, onEvent, onState } = useMusicSession();

  return (
    <section aria-labelledby="music-session-heading">
      <h2 id="music-session-heading">Sesión de música</h2>
      {view.status === "loading" && <p>Cargando la sesión de música…</p>}
      {view.status === "error" && <p>{CONNECTION_ERROR}</p>}
      {view.status === "closed" && (
        <>
          <p>La sesión de música está cerrada.</p>
          {view.notice === "email_not_verified" ? (
            <>
              <p>Para abrir la sesión de música, primero verifica tu correo con el enlace que te enviamos.</p>
              <ResendVerification />
            </>
          ) : (
            view.notice === "error" && <p>{CONNECTION_ERROR}</p>
          )}
          <button type="button" onClick={() => void open()}>
            Abrir la sesión de música
          </button>
        </>
      )}
      {view.status === "open" && (
        <>
          <OpenDetails session={view.session} />
          {view.notice === "error" && <p>{CONNECTION_ERROR}</p>}
          <button type="button" onClick={() => void close()}>
            Cerrar la sesión de música
          </button>
        </>
      )}
      <SessionRoom handlers={{ onEvent, onState }} connect={connect} />
    </section>
  );
}
