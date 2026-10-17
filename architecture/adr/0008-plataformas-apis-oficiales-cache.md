# ADR-0008 — APIs oficiales de YouTube y Spotify con caché de búsquedas

| Campo     | Valor |
| --------- | ----- |
| Estado    | Superseded by ADR-0010 |
| Fecha     | 2026-10-16 |
| Motivo    | Q1, Q2, Q5, D1§2 |
| Sustituye | — |

> Una decisión que afecta a más de una feature o es cara de revertir. Si no lo
> es, va al `plan.md` de la feature. Sustituye todo texto en cursiva. Solo el
> usuario aprueba (`/architecture:approve`) o decide una propuesta
> (`/architecture:review`).

## Contexto

La cola mezcla YouTube y Spotify (D1§2). La búsqueda debe responder en menos de 2 s (Q1) con 5000 clientes (Q2), y la reproducción no debe dejar silencios de más de 3 s (Q5). La cuota por defecto de la YouTube Data API (10 000 unidades al día, 100 por búsqueda) da unas 100 búsquedas diarias.

## Decisión

La búsqueda (C3) usa la YouTube Data API v3 y la Spotify Web API desde el monolito, con caché de resultados en Redis y una solicitud de ampliación de cuota a Google. La reproducción (C4) usa el YouTube IFrame Player API y el Spotify Web Playback SDK en el navegador del local. Cada plataforma va tras un adaptador común, para poder añadir otras.

## Alternativas descartadas

- Búsqueda primero en un catálogo propio de canciones ya pedidas: gasta menos cuota, pero es más trabajo; queda como mejora si la caché no basta.
- Bibliotecas no oficiales o scraping (yt-dlp, ytmusicapi): no tienen cuota, pero incumplen los términos de servicio y se rompen sin aviso.

## Consecuencias

- Sin ampliación de cuota de Google, Q1 y Q2 no se cumplen: es un riesgo del piloto.
- Spotify Web Playback SDK exige que el local tenga una cuenta Spotify Premium conectada (B08).
- La publicidad de las plataformas no se controla (D1§4) y puede alargar los huecos; Q5 se mide entre canciones, no dentro de un anuncio.
- El uso en un local comercial según los términos de YouTube y Spotify está sin resolver: es la pregunta abierta de este ADR.
