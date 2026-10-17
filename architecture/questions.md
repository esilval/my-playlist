# Preguntas de arquitectura

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · 596d18108b01 |

> Lo que el producto no decide y hace falta para decidir la arquitectura. Cada
> pregunta cita entre paréntesis lo que afecta: `- [ ] (ADR-0002; Q1) ¿…?`.
> Una pregunta abierta que cita una decisión o un atributo impide aprobar. Al
> responderla, márcala `[x]` y añade debajo `- **Respuesta:** …`.
>
> Solo el usuario cambia el Estado, con `/architecture:approve`.

## Preguntas

- [x] (ADR-0008) ¿Permiten los términos de servicio de YouTube y de Spotify (Developer Terms) reproducir su contenido en un local comercial a través de MyPlaylist? Hay que revisarlo con asesoría legal antes del piloto; si no lo permiten, cambian la integración (C3, C4) o el producto.
**Respuesta**: Al tratarse de un SaaS de escala menos (menos de 50 clientes) y no ser un servicio de streaming, no hay problema en reproducir contenido de Youtube. Pero cuando esa escala crezca, se debe optar por proveedores de Video B2B (Como LoopTV que cuenta con una API robusta para integrarse con otros sistemas) o Spotify for Business (que es un servicio de pago y no tiene API pública). Con respecto a Spotify existen dos limitantes: 1) Legalmente no se puede usar en un local comercial para fines de lucro y 2) Spotify no permite la integración de su reproductor en un navegador web, por lo que no se puede usar el reproductor de Spotify en el navegador del local (C4). Por lo tanto, se recomienda usar Youtube como fuente principal de música y Spotify solo como fuente secundaria para los clientes que tengan una cuenta premium y quieran escuchar su música personal.
