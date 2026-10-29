// Lo que suena, las canciones pendientes del cliente y su cupo (plan D7; R010).
import type { Quota, RequestedTrack } from "./useClientMusic";

interface Props {
  nowPlaying: string | null;
  mine: RequestedTrack[];
  quota: Quota;
}

export function MyRequests({ nowPlaying, mine, quota }: Props) {
  return (
    <section aria-labelledby="my-requests-heading">
      <p>{nowPlaying ? <>Suena: <strong>{nowPlaying}</strong></> : "No suena nada."}</p>
      <h2 id="my-requests-heading">Tus canciones</h2>
      {mine.length === 0 ? (
        <p>Aún no has pedido ninguna.</p>
      ) : (
        // En el orden en que sonarán.
        <ol aria-label="Tus canciones pendientes">
          {mine.map((track) => (
            <li key={track.item_id}>{track.title}</li>
          ))}
        </ol>
      )}
      <p>
        Te quedan {quota.free} de {quota.limit}.
      </p>
    </section>
  );
}
