// El buscador del cliente y sus resultados (plan D7; R003, R005).
//
// Solo busca al pulsar «Buscar», no mientras se escribe: cada búsqueda cuenta para el
// límite de R013 y gasta cuota del proveedor.
import { useState, type FormEvent } from "react";

import type { TrackResult } from "./useClientMusic";

// El mismo límite que la API (plan D1).
const MAX_QUERY_LENGTH = 100;

interface Props {
  onSearch(query: string): Promise<TrackResult[] | null>;
  onRequest(track: TrackResult): Promise<void>;
}

export function SongSearch({ onSearch, onRequest }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TrackResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [requesting, setRequesting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || searching) return;
    setSearching(true);
    try {
      setResults(await onSearch(text));
    } finally {
      setSearching(false);
    }
  }

  async function request(track: TrackResult) {
    setRequesting(true);
    try {
      await onRequest(track);
    } finally {
      setRequesting(false);
    }
  }

  return (
    <section aria-labelledby="song-search-heading">
      <h2 id="song-search-heading">Pide una canción</h2>
      <form role="search" onSubmit={submit}>
        <div className="field">
          <label htmlFor="song-query">Canción, artista o álbum</label>
          <input
            id="song-query"
            type="search"
            name="q"
            maxLength={MAX_QUERY_LENGTH}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <button type="submit" disabled={searching}>
          Buscar
        </button>
      </form>
      {results !== null && results.length === 0 && <p>No se encontraron canciones.</p>}
      {results !== null && results.length > 0 && (
        <ul aria-label="Resultados">
          {results.map((track) => (
            <li key={track.ref}>
              <strong>{track.title}</strong> · {track.author}{" "}
              <button
                type="button"
                disabled={requesting}
                aria-label={`Pedir «${track.title}»`}
                onClick={() => void request(track)}
              >
                Pedir
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
