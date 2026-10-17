# Brief del producto

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · 0cb192594661 |

> Qué es el producto y para qué, según los documentos de `product/sources/`.
> Cada elemento cita su origen (`D2§4.2`). Aquí no se redactan requisitos
> («el sistema DEBERÁ…»): eso es trabajo de `/sdd:specify`.
>
> Sustituye todo texto en cursiva. Solo el usuario cambia el Estado, con
> `/discovery:approve`.

## Objetivos

### G1 — Los clientes ponen su música en el local desde el móvil

- **Origen:** D1§1, D1§2, D1§3
- **Descripción:** el cliente de un establecimiento escanea el QR del local, busca canciones y las pone en la cola sin instalar nada ni registrarse; ve qué suena y qué viene. Se nota en que las canciones pedidas suenan en el orden en que se pidieron, con un reparto justo entre clientes.

### G2 — El propietario controla la música de su local

- **Origen:** D1§2, D1§3, D1§4
- **Descripción:** el propietario decide qué suena: abre y cierra la sesión, ve la cola, la reordena, elimina canciones y agrega las suyas. Se nota en que nada suena en el local sin que él pueda quitarlo.

### G3 — La música no se detiene mientras el local está abierto

- **Origen:** D1§2
- **Descripción:** si la cola se vacía o una canción falla, la música sigue sin que el propietario intervenga. Se nota en que no hay silencios mientras la sesión está abierta.

### G4 — MyPlaylist se sostiene como SaaS por suscripción

- **Origen:** D1§5, D1§6, D1§6.1
- **Descripción:** los establecimientos se dan de alta solos por la web, prueban gratis y luego pagan un plan (Básico o Premium) para seguir usándolo. Se nota en establecimientos que pasan de la prueba a un plan de pago.

## Usuarios

- Cliente del establecimiento: anónimo, identificado solo por su dispositivo; quiere pedir canciones desde el móvil y ver la cola (D1§1, D1§2).
- Propietario del establecimiento: una cuenta por establecimiento, sin empleados; quiere controlar la música del local y que no se detenga (D1§2, D1§6).

## Glosario

- **Establecimiento:** local (bar, restaurante…) con su propio QR y su propia cola; las búsquedas y pedidos de un establecimiento no se mezclan con los de otro (D1§2).
- **Sesión:** periodo entre que el propietario abre y cierra manualmente la música del local; delimita la cola y el relleno (D1§2).
- **Cola (playlist de la sesión):** canciones pendientes de la sesión, reproducidas en el orden en que se pidieron salvo que el propietario la reordene (D1§1, D1§2).
- **Cupo:** canciones pendientes que un cliente puede tener a la vez en la cola; 5 en el Plan Básico (D1§1, D1§6.1).
- **Relleno:** tanda de hasta 10 canciones, una por artista al azar, que entra cuando la cola se vacía con la sesión abierta (D1§2).
- **Ventana anti-repetición:** horas durante las que una canción que ya sonó no puede volver a pedirse; 3 por defecto, configurable (D1§2).
- **Pantalla de cola:** página web aparte que muestra en tiempo real qué suena y qué viene, para abrir en cualquier pantalla del local (D1§2).

## Restricciones

- Lanzamiento inicial en Bogotá (D1§1).
- Producto web SaaS, sin instalación para clientes ni propietarios (D1§5).
- Plataforma de la primera versión: solo YouTube. Spotify no se usa porque sus términos no permiten reproducirlo en un local comercial con fines de lucro; al crecer, la música pasará a un proveedor B2B con licencia para locales (p. ej. LoopTV) (D1§2, D1§3, respuesta en Preguntas).
- Reproducir YouTube en los locales del piloto (menos de 50) es un riesgo de licencia asumido, no un permiso de sus términos (D1§2, D1§4, respuesta en Preguntas).
- La publicidad que imponga la plataforma de streaming se reproduce y no se controla (D1§4).
- Fuera de alcance: subir contenido, eventos en vivo, crear playlists en las plataformas, gestionar suscripciones a las plataformas (D1§4).
- Tratamiento de datos personales conforme a la Ley 1581 de 2012 de Colombia (D1§7, respuesta en Preguntas).
- Objetivos de calidad del piloto: búsqueda en menos de 2 s; hasta 50 locales y 100 clientes por local a la vez; 99,5 % de disponibilidad (D1§7, respuesta en Preguntas).
- Prueba gratuita de 30 días; cobro mensual en COP con una pasarela de pago colombiana (D1§6, respuesta en Preguntas).
- El Plan Premium de la primera versión solo amplía límites; la «personalización de la experiencia musical» queda fuera por ahora (D1§6.1, respuesta en Preguntas).

## Invariantes propuestos para la constitución

> Reglas transversales que los documentos exigen. Son propuestas: la
> constitución solo la cambia el usuario, con `/sdd:constitution`.

- Aislamiento por establecimiento: ninguna búsqueda, pedido ni cola de un establecimiento es visible ni modificable desde otro (D1§2).
- Solo el propietario de un establecimiento modifica el orden o el contenido de su cola (D1§2).
- Datos mínimos: los clientes son anónimos; del propietario solo se guardan cuenta y facturación; cumplimiento de la Ley 1581 (D1§7).
- Ninguna funcionalidad exige instalar software en los dispositivos del local ni de los clientes (D1§5).

## Secciones descartadas

> Secciones de los documentos que no dan lugar a objetivos ni candidatas, con
> el motivo.

- D1§7 — atributos de calidad transversales (rendimiento, disponibilidad, seguridad, usabilidad): pasan a restricciones (con las cifras del piloto) e invariantes propuestos.

## Preguntas

> Cada pregunta cita entre paréntesis su origen y, si lo hay, el objetivo al
> que afecta: `- [ ] (D1§2; G1) ¿…?`. Al responderla se marca `[x]` y se
> añade la respuesta debajo. Una pregunta abierta sobre un objetivo impide
> aprobar el producto.

- [x] (D1§1; D1§2) ¿Cómo se identifica a un cliente para aplicar el límite de canciones: anónimo por dispositivo/navegador, con registro (correo, teléfono), o con login social?
  - **Respuesta:** Anónimo por dispositivo.
- [x] (D1§1; D1§2) ¿El límite de 5 canciones es por visita, por día o por sesión del establecimiento? ¿Se libera un cupo cuando una de sus canciones ya sonó?
  - **Respuesta:** Simultáneas en cola: máximo 5 pendientes a la vez; al sonar una, se libera un cupo.
- [x] (D1§1 contra D1§6.1) §1 dice que el límite es parametrizable, pero §6.1 fija 5 en el Plan Básico. ¿Quién lo parametriza (propietario o plataforma) y depende del plan?
  - **Respuesta:** Propietario, según plan: Básico fijo en 5; Premium permite al propietario cambiarlo.
- [x] (D1§2 contra D1§6.1) §2 da al propietario agregar canciones sin límite en cualquier caso; §6.1 reserva «agregar canciones sin límite» al Plan Premium. ¿A quién se refiere el «sin límite» del Premium: al propietario o a los clientes?
  - **Respuesta:** Al propietario: en el Plan Básico el propietario también tiene límite; solo en Premium es ilimitado.
- [x] (D1§2) ¿Qué es la «sesión actual» de la playlist? ¿Cuándo empieza y termina (apertura/cierre manual, horario configurado, cada día)?
  - **Respuesta:** Apertura/cierre manual: el propietario abre la sesión al abrir el local y la cierra al cerrar.
- [x] (D1§2) ¿Cómo sabe la aplicación que «aún hay funcionamiento del establecimiento» para el relleno automático: horario configurado, playlist abierta manualmente u otro?
  - **Respuesta:** Apertura/cierre manual: hay funcionamiento mientras la sesión esté abierta.
- [x] (D1§2) Relleno automático: ¿de qué conjunto salen los 10 artistas al azar (historial del establecimiento, lista definida por el propietario, géneros)? ¿Qué pasa al terminar esas 10 canciones?
  - **Respuesta:** Historial + lista: lista de artistas del propietario si existe; si no, historial del establecimiento. (Qué pasa al terminar las 10 canciones queda como pregunta aparte.)
- [x] (D1§2 contra D1§6.1) Si en el Plan Básico el propietario también tiene límite, ¿cuál es ese límite y sobre qué cuenta (canciones en cola, por sesión)?
  - **Respuesta:** Por sesión: N canciones por sesión. (El valor de N queda como pregunta aparte.)
- [x] (D1§2) Relleno automático: ¿qué pasa al terminar las hasta 10 canciones de relleno si la sesión sigue abierta (otra tanda, silencio)?
  - **Respuesta:** Otra tanda: se generan otras hasta 10, indefinidamente.
- [x] (D1§2) ¿Dónde suena la música: un navegador abierto en un equipo del local que reproduce la playlist? ¿Qué significa exactamente «detectar pantallas conectadas al sistema de audio»? Una web no puede detectar hardware por sí sola: ¿basta con que el propietario abra una vista de pantalla en otro dispositivo?
  - **Respuesta:** Navegador + vista aparte: un navegador del local reproduce; la pantalla de cola es una URL que el propietario abre en cualquier pantalla. La configuración se guarda.
- [x] (D1§2) El QR es fijo por establecimiento: ¿cómo se evita que alguien fuera del local (con una foto del QR) pida canciones? (QR rotativo, geolocalización, código en pantalla, nada)
  - **Respuesta:** No se controla en la primera versión; el propietario puede eliminar canciones.
- [x] (D1§2) ¿Se permiten canciones repetidas en la cola? ¿Hay filtro de contenido (explícito, duración máxima, géneros vetados por el propietario)?
  - **Respuesta:** Ventana de tiempo: una canción no se repite si sonó en las últimas N horas/canciones. (El valor de N y el filtro de contenido quedan como preguntas aparte.)
- [x] (D1§2) Ventana anti-repetición: ¿cuánto vale N (horas o número de canciones) y lo configura el propietario?
  - **Respuesta:** Propietario, en horas: configurable por el propietario. (Valor por defecto sin definir.)
- [x] (D1§6.1) ¿Cuántas canciones por sesión puede agregar el propietario en el Plan Básico? ¿Y cuál es el valor por defecto de la ventana anti-repetición en horas?
  - **Respuesta:** 50 por sesión / 3 h: el propietario puede agregar 50 canciones por sesión en el Plan Básico; ventana anti-repetición por defecto de 3 horas.
- [x] (D1§2) ¿Hay filtro de contenido (explícito, duración máxima, géneros o artistas vetados por el propietario)?
  - **Respuesta:** Sin filtro: el propietario elimina lo que no quiera.
- [x] (D1§2) «Sólamente él» (el propietario) administra la playlist: ¿pueden existir empleados u otros administradores con permisos, y un propietario con varios establecimientos?
  - **Respuesta:** Solo propietario: una cuenta por establecimiento, sin empleados.
- [x] (D1§2) ¿Qué pasa si una canción no se puede reproducir (no disponible, bloqueada por región, error de red)?
  - **Respuesta:** Saltar y avisar: se salta a la siguiente y se avisa al propietario (y al cliente).
- [x] (D1§4) «Los usuarios deberán tener una cuenta activa en la plataforma»: ¿quién necesita cuenta, el establecimiento o también los clientes? (YouTube no exige cuenta para reproducir.)
  - **Respuesta:** Nadie al inicio: con YouTube no hace falta cuenta; aplica a futuras plataformas (p. ej. Spotify).
- [x] (D1§1 contra D1§4) La introducción del documento habla de «crear y gestionar tus listas… organizarlas en diferentes listas», pero el resto describe una única playlist por establecimiento. ¿Hay varias listas por establecimiento o solo la cola de la sesión?
  - **Respuesta:** Solo la cola: una cola por sesión; la introducción es solo texto de bienvenida.
- [x] (D1§3) «Extensión a diferentes plataformas de streaming» está en el alcance: ¿la primera versión solo integra YouTube y el resto es diseño extensible, o se espera más de una plataforma desde el inicio?
  - **Respuesta:** YouTube + otra: más de una desde el inicio. (Cuál es la otra queda como pregunta aparte.)
- [x] (D1§2; D1§3) Además de YouTube, ¿qué otra plataforma de streaming integra la primera versión (Spotify, YouTube Music, otra)? ¿El propietario elige una por establecimiento?
  - **Respuesta:** Spotify. (Si el propietario elige una por establecimiento queda como pregunta aparte.)
- [x] (D1§6) ¿Duración del periodo de prueba? ¿Qué pasa al vencer la prueba o la suscripción (bloqueo total, modo limitado)? ¿Moneda y medio de pago (p. ej. COP con pasarela local)?
  - **Respuesta:** Bloqueo total: no se puede abrir sesión hasta pagar. (Duración de la prueba, moneda y medio de pago quedan como pregunta aparte.)
- [x] (D1§6.1) ¿Qué incluye «personalización de la experiencia musical» del Plan Premium? ¿Precios de cada plan?
  - **Respuesta:** Quitarla por ahora: la primera versión del Premium solo amplía los límites (B10); los precios se definen después.
- [x] (D1§7) ¿Hay cifras objetivo para rendimiento y disponibilidad (tiempo de respuesta de búsqueda, establecimientos y clientes simultáneos, % de disponibilidad)?
  - **Respuesta:** Piloto modesto: búsqueda en menos de 2 s; hasta 50 locales y 100 clientes por local a la vez; 99,5 % de disponibilidad.
- [x] (D1§7) ¿Qué datos personales de clientes y propietarios se guardan? ¿Debe cumplirse explícitamente la Ley 1581 de 2012 (protección de datos en Colombia)?
  - **Respuesta:** Mínimos + Ley 1581: clientes anónimos; del propietario solo cuenta y facturación; cumplir Ley 1581.
- [x] (D1§2; D1§3) ¿El propietario elige una sola plataforma (YouTube o Spotify) por establecimiento, o pueden mezclarse en la misma cola?
  - **Respuesta:** Mezcladas: la cola puede tener canciones de ambas plataformas.
- [x] (D1§6) ¿Duración del periodo de prueba? ¿Moneda y medio de pago (p. ej. COP con pasarela local)?
  - **Respuesta:** 30 días, COP, pasarela local: prueba de 30 días; cobro mensual en COP con una pasarela colombiana.
- [ ] (D1§6; D1§6.1) ¿Precio mensual en COP de los planes Básico y Premium, y qué pasarela colombiana concreta se usa (p. ej. Wompi, PayU, Mercado Pago)?
- [x] (D1§2; D1§3; D1§4) ¿Permiten los términos de servicio de YouTube y de Spotify reproducir su contenido en un local comercial a través de MyPlaylist? (Viene de la pregunta de ADR-0008 en architecture/questions.md; sustituye a las respuestas anteriores que incluían Spotify en la cola.)
  - **Respuesta:** Al tratarse de un SaaS de escala menos (menos de 50 clientes) y no ser un servicio de streaming, no hay problema en reproducir contenido de Youtube. Pero cuando esa escala crezca, se debe optar por proveedores de Video B2B (Como LoopTV que cuenta con una API robusta para integrarse con otros sistemas) o Spotify for Business (que es un servicio de pago y no tiene API pública). Con respecto a Spotify existen dos limitantes: 1) Legalmente no se puede usar en un local comercial para fines de lucro y 2) Spotify no permite la integración de su reproductor en un navegador web, por lo que no se puede usar el reproductor de Spotify en el navegador del local (C4). Por lo tanto, se recomienda usar Youtube como fuente principal de música y Spotify solo como fuente secundaria para los clientes que tengan una cuenta premium y quieran escuchar su música personal.
