# ADR-0010 — YouTube como única plataforma del piloto, con salida a un proveedor B2B

| Campo     | Valor |
| --------- | ----- |
| Estado    | Approved · 369be456100b |
| Fecha     | 2026-10-16 |
| Motivo    | Q1, Q2, Q5, D1§2, D1§4 |
| Sustituye | ADR-0008 |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

ADR-0008 integraba YouTube y Spotify, mezclados en la cola y reproducidos en el navegador del local (C4). La respuesta a su pregunta de licencias lo invalida en parte: los términos de Spotify no permiten usarlo en un local comercial con fines de lucro, y Spotify for Business no tiene API pública. El Web Playback SDK sí funciona técnicamente en el navegador (con cuenta Premium), así que el bloqueo es legal, no técnico.

Para YouTube, el propietario del producto acepta reproducir en el piloto (menos de 50 locales) porque MyPlaylist no es un servicio de streaming. Los términos de YouTube no prevén excepciones por tamaño, así que se trata de un riesgo asumido, no de un permiso. Al crecer habrá que pasar a un proveedor B2B de música o vídeo con licencia para locales (p. ej. LoopTV).

Las exigencias de ADR-0008 siguen vigentes: búsqueda en menos de 2 s (Q1) con 5000 clientes (Q2), cuota por defecto de la YouTube Data API de unas 100 búsquedas al día, y menos de 3 s de silencio entre canciones (Q5).

## Decisión

En el piloto, YouTube es la única plataforma que suena en el local. La búsqueda (C3) usa la YouTube Data API v3 desde el monolito, con caché de resultados en Redis y una solicitud de ampliación de cuota a Google. La reproducción (C4) usa el YouTube IFrame Player API. Búsqueda y reproducción quedan detrás de un adaptador de proveedor (catálogo + reproductor), para poder sustituir YouTube por un proveedor B2B con licencia sin tocar la cola (C2). Spotify no se integra en el reproductor del local.

## Alternativas descartadas

- Mantener ADR-0008 con Spotify mezclado en la cola: lo impiden los términos de Spotify para uso comercial.
- Spotify solo como fuente para el cliente con su propia cuenta Premium, escuchando su música personal: es otro caso de uso, que no está en el brief ni en el backlog y no pone música en el local. Si se quiere, se define primero en discovery.
- Pasar ya a un proveedor B2B (LoopTV u otro): tiene licencia para locales, pero añade un coste y una negociación que el piloto no justifica todavía; queda como salida prevista.
- Bibliotecas no oficiales o scraping (yt-dlp, ytmusicapi): incumplen los términos de servicio y se rompen sin aviso (S7 sigue vigente).

## Consecuencias

- La cola deja de ser mixta: B08 y la restricción del brief «YouTube y Spotify, mezclables en la misma cola» quedan sin soporte y hay que revisarlos en discovery (descartar o redefinir B08).
- Riesgo asumido: la reproducción de YouTube en locales comerciales puede incumplir sus términos. Si Google lo objeta o el producto supera la escala del piloto, se activa la migración a un proveedor B2B.
- El adaptador de proveedor es obligatorio desde la primera feature de búsqueda o reproducción: C2 y los frontales no dependen de identificadores ni formatos propios de YouTube más allá del adaptador.
- Sin la ampliación de cuota de Google, Q1 y Q2 no se cumplen: sigue siendo un riesgo del piloto, como en ADR-0008.
- La publicidad de YouTube no se controla (D1§4) y puede alargar los huecos; Q5 se mide entre canciones, no dentro de un anuncio.
- Los componentes C3 y C4 y los estándares S4, S6 y S7 citan Spotify: hay que ajustar su texto cuando esta decisión se acepte y el producto se actualice.
