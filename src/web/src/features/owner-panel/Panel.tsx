// Panel del propietario (R008, R010, R011, R014, R018, R019, R020; feature 002: R001,
// R002, R007, R011, R014 en la tarjeta de sesión de música).
import { CONNECTION_ERROR } from "../../api/errors";
import { MusicSessionCard } from "../music-session/MusicSessionCard";
import { EstablishmentForm } from "./EstablishmentForm";
import { LogoutButton } from "./LogoutButton";
import { QrCard } from "./QrCard";
import { useOwnerMe } from "./useOwnerMe";

export function Panel() {
  const [state, setState] = useOwnerMe();

  if (state.status === "unauthenticated") {
    return <main aria-busy="true" />;
  }
  if (state.status === "loading") {
    return (
      <main>
        <p role="status">Cargando…</p>
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

  const { me } = state;
  return (
    <main>
      <h1>{me.establishment.name}</h1>
      <p>
        Sesión de {me.account.email} · <LogoutButton />
      </p>
      <EstablishmentForm
        establishment={me.establishment}
        onSaved={(establishment) =>
          setState({ status: "ready", me: { ...me, establishment } })
        }
      />
      <MusicSessionCard />
      <QrCard
        emailVerified={me.account.email_verified}
        publicUrl={me.establishment.public_url}
        name={me.establishment.name}
      />
    </main>
  );
}
