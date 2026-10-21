# Spec: Sesión de música y reproductor del local

| Campo  | Valor        |
| ------ | ------------ |
| ID     | `002-sesion-musica-reproductor-local`     |
| Fecha  | 2026-10-21     |
| Estado | Approved · 9c08996de1d3        |
| Issue  | —            |
| Origen | B02 · G2, G3 · D1§1, D1§2 · C2, C4, C6, C7 |

> Este documento describe **qué** y **por qué**, nunca **cómo**.
> Toda decisión de implementación (librerías, esquemas, servicios) va en `plan.md`.
>
> Sustituye todo texto en cursiva; si una sección no aplica, escribe
> «No aplica.». Solo el usuario cambia el Estado, con `/sdd:approve`.

## Problema

Sin un reproductor en el local, las canciones pedidas no llegan a sonar.

## Contexto

Feature creada desde la candidata B02 «Sesión de música y reproductor del local» de `product/backlog.md`, con el producto de discovery aprobado.

- **G2 — El propietario controla la música de su local:** el propietario decide qué suena: abre y cierra la sesión, ve la cola, la reordena, elimina canciones y agrega las suyas. Se nota en que nada suena en el local sin que él pueda quitarlo.
- **G3 — La música no se detiene mientras el local está abierto:** si la cola se vacía o una canción falla, la música sigue sin que el propietario intervenga. Se nota en que no hay silencios mientras la sesión está abierta.
- **Origen D1§1** «Descripción»: `product/sources/D1-overview.md`
- **Origen D1§2** «Propuesta»: `product/sources/D1-overview.md`

## Alcance

### Dentro

- El propietario abre la sesión de música desde su panel, pone en marcha el reproductor en un navegador del local, y las canciones de la cola suenan una tras otra en el orden de la cola. Si una no se puede reproducir, se salta y se avisa al propietario. Al cerrar la sesión de música, la música se detiene.
- Abrir y cerrar la sesión de música, con el correo verificado.
- Reproducción en orden de la cola con la plataforma del piloto (YouTube), con un único reproductor activo por establecimiento.
- Salto y aviso ante canciones que fallan.
- Espera con la cola vacía y recuperación tras un corte de conexión del reproductor.
- La canción que suena, visible en el panel.

### Fuera (non-goals)

- Que los clientes pidan canciones (B03): con solo esta feature no hay forma de que una canción entre en la cola, y las pruebas parten de una cola ya cargada.
- Que el propietario vea la cola, la reordene, elimine canciones o agregue las suyas (B05).
- El relleno cuando la cola se vacía (B07): con la cola vacía, el reproductor espera en silencio.
- La pantalla pública de la cola (B06).
- Otras plataformas de música; Spotify está descartada (B08).
- Bloquear la sesión de música por la prueba gratuita o la suscripción (B09): cualquier establecimiento con el correo verificado puede abrirla.
- Pausar, cambiar el volumen, adelantar dentro de una canción o saltarla a mano desde el panel.
- Cerrar la sesión de música de forma automática, por horario o por inactividad: solo la cierra el propietario.
- Detectar pantallas o altavoces conectados al equipo del local.
- Controlar la publicidad que imponga la plataforma de música.

## Requisitos

Notación EARS. Cada requisito lleva un ID estable que se referencia después en
`plan.md`, `tasks.md` y en los tests.

Patrones:

| Patrón      | Forma                                                       |
| ----------- | ----------------------------------------------------------- |
| Ubicuo      | El sistema DEBERÁ \<respuesta\>                             |
| Evento      | CUANDO \<disparador\>, el sistema DEBERÁ \<respuesta\>      |
| Estado      | MIENTRAS \<estado\>, el sistema DEBERÁ \<respuesta\>        |
| Opcional    | DONDE \<característica\>, el sistema DEBERÁ \<respuesta\>   |
| No deseado  | SI \<condición\>, ENTONCES el sistema DEBERÁ \<respuesta\>  |

| ID   | Prioridad | Requisito |
| ---- | --------- | --------- |
| R001 | MUST      | CUANDO el propietario con el correo verificado abre la sesión de música desde su panel, el sistema DEBERÁ dejarla abierta con una cola sin canciones e indicar en el panel que la sesión está abierta. |
| R002 | MUST      | SI el propietario con el correo sin verificar intenta abrir la sesión de música, ENTONCES el sistema DEBERÁ impedirlo, indicar que debe verificar su correo y ofrecer reenviar el enlace de verificación. |
| R003 | MUST      | SI el propietario pide abrir la sesión de música cuando ya hay una abierta en su establecimiento, ENTONCES el sistema DEBERÁ mantener la sesión abierta, sin crear otra ni vaciar su cola. |
| R004 | MUST      | CUANDO el propietario pone en marcha el reproductor en un navegador del local con la sesión de música abierta, el sistema DEBERÁ empezar a reproducir la primera canción pendiente de la cola. |
| R005 | MUST      | MIENTRAS la sesión de música está abierta y el reproductor está en marcha, el sistema DEBERÁ reproducir las canciones de la cola una tras otra, en el orden de la cola, y empezar cada una en menos de 3 s desde que termina la anterior. |
| R006 | MUST      | El sistema DEBERÁ reproducir cada canción de la cola como mucho una vez en la misma sesión de música, y dejar de contarla como pendiente cuando termina de sonar o se salta. |
| R007 | MUST      | SI una canción de la cola no se puede reproducir, ENTONCES el sistema DEBERÁ saltarla, empezar la siguiente pendiente en menos de 3 s y avisar en el panel del propietario de qué canción falló. |
| R008 | MUST      | MIENTRAS la sesión de música está abierta y la cola no tiene canciones pendientes, el sistema DEBERÁ mantener el reproductor en espera sin sonar, indicarlo en el reproductor, y empezar en menos de 3 s la siguiente canción que entre en la cola. |
| R009 | MUST      | SI se abre el reproductor sin una sesión de música abierta en el establecimiento, ENTONCES el sistema DEBERÁ indicar que no hay sesión abierta y no reproducir nada. |
| R010 | MUST      | CUANDO el propietario pone en marcha el reproductor en otro navegador mientras ya hay uno activo, el sistema DEBERÁ hacer de este el único reproductor activo del establecimiento: el anterior deja de sonar en menos de 3 s e indica que la música sigue en otro dispositivo, y el nuevo reproduce la canción que estaba sonando, desde el principio. |
| R011 | MUST      | CUANDO el propietario cierra la sesión de música, el sistema DEBERÁ detener la música en el reproductor en menos de 3 s, descartar las canciones pendientes de la cola y conservar las que ya sonaron. |
| R012 | MUST      | SI el reproductor pierde la conexión mientras suena una canción, ENTONCES el sistema DEBERÁ continuar en orden al recuperarla: sin repetir canciones que ya sonaron ni saltar pendientes, y aplicando lo que haya pasado durante el corte (un cierre de la sesión de música o el cambio a otro reproductor). |
| R013 | MUST      | SI una persona sin sesión iniciada, o con la sesión de otro propietario, intenta abrir o cerrar la sesión de música de un establecimiento, poner en marcha su reproductor o ver lo que suena en él, ENTONCES el sistema DEBERÁ denegarlo sin mostrar datos de ese establecimiento. |
| R014 | SHOULD    | MIENTRAS la sesión de música está abierta, el sistema DEBERÁ mostrar en el panel del propietario la canción que suena y si hay un reproductor activo, y actualizarlo en menos de 1 s cuando cambie. |
| R015 | MUST      | SI la sesión iniciada del equipo del reproductor se cierra mientras suena una canción (por ejemplo, al restablecer la contraseña desde otro equipo), ENTONCES el sistema DEBERÁ dejar que esa canción termine, detener el reproductor indicando que hay que volver a iniciar sesión, y mantener abierta la sesión de música con sus canciones pendientes; al volver a iniciar sesión y poner en marcha el reproductor, DEBERÁ continuar en orden sin repetir la canción que terminó. |

## Criterios de aceptación

### R001

- **Dado** un propietario con el correo verificado y sin sesión de música abierta **cuando** abre la sesión de música desde su panel **entonces** el panel indica que la sesión está abierta y la cola no tiene canciones.

### R002

- **Dado** un propietario con el correo sin verificar **cuando** intenta abrir la sesión de música **entonces** la sesión sigue cerrada, ve que debe verificar su correo y puede pedir que se le reenvíe el enlace.

### R003

- **Dado** una sesión de música abierta con 2 canciones pendientes **cuando** el propietario vuelve a pedir abrirla, por ejemplo desde otra pestaña **entonces** sigue habiendo una sola sesión abierta y las 2 canciones siguen pendientes.

### R004

- **Dado** una sesión de música abierta con las canciones A, B y C pendientes, en ese orden **cuando** el propietario pone en marcha el reproductor **entonces** empieza a sonar A.

### R005

- **Dado** el reproductor sonando A, con B y C pendientes **cuando** termina A **entonces** B empieza a sonar en menos de 3 s, y al terminar B empieza C.

### R006

- **Dado** una sesión de música en la que A ya sonó y B se saltó, con C pendiente **cuando** se pone en marcha el reproductor otra vez, por ejemplo tras recargar la página **entonces** suena C, y A y B no vuelven a sonar en esa sesión.

### R007

- **Dado** el reproductor con B pendiente después de A, y B no se puede reproducir (por ejemplo, el video fue retirado o no admite reproducirse fuera de su plataforma) **cuando** termina A **entonces** C empieza a sonar en menos de 3 s y el panel del propietario avisa de que B no se pudo reproducir.
- **Dado** B como única canción pendiente, y B no se puede reproducir **cuando** le toca a B **entonces** se salta, el reproductor queda en espera y el panel avisa del fallo.

### R008

- **Dado** una sesión de música abierta, con la cola sin canciones pendientes **cuando** se pone en marcha el reproductor **entonces** no suena nada y el reproductor indica que espera canciones.
- **Dado** el reproductor en espera **cuando** entra una canción en la cola **entonces** empieza a sonar en menos de 3 s.

### R009

- **Dado** un establecimiento sin sesión de música abierta **cuando** el propietario abre el reproductor **entonces** el reproductor indica que no hay sesión abierta y no suena nada.

### R010

- **Dado** el reproductor del portátil sonando A **cuando** el propietario pone en marcha el reproductor en la tableta del local **entonces** el portátil deja de sonar en menos de 3 s e indica que la música sigue en otro dispositivo, y la tableta reproduce A desde el principio.

### R011

- **Dado** el reproductor sonando A, con B y C pendientes **cuando** el propietario cierra la sesión de música **entonces** la música se detiene en menos de 3 s, el reproductor indica que no hay sesión abierta, y al abrir una sesión nueva su cola no tiene canciones.
- **Dado** el reproductor sin conexión mientras el propietario cierra la sesión de música **cuando** el reproductor recupera la conexión **entonces** deja de sonar en menos de 3 s.

### R012

- **Dado** el reproductor sonando A, con B pendiente **cuando** se corta la conexión durante A y vuelve antes de que A termine **entonces** al terminar A suena B.
- **Dado** el reproductor sin conexión cuando termina A, con B pendiente **cuando** recupera la conexión **entonces** B empieza a sonar en menos de 3 s, y A no vuelve a sonar.
- **Dado** el reproductor del portátil sin conexión mientras suena A **cuando** el propietario pone en marcha el reproductor en la tableta y después el portátil recupera la conexión **entonces** el portátil deja de sonar en menos de 3 s e indica que la música sigue en otro dispositivo, y la tableta sigue reproduciendo.

### R013

- **Dado** una persona sin sesión iniciada **cuando** intenta abrir el reproductor o abrir la sesión de música de un establecimiento **entonces** se le pide iniciar sesión y no ve datos de ese establecimiento.
- **Dado** el propietario A con sesión iniciada **cuando** intenta abrir o cerrar la sesión de música del establecimiento de B, o poner en marcha su reproductor **entonces** se le deniega, y la sesión de música de B no cambia.

### R014

- **Dado** el reproductor sonando A **cuando** empieza B **entonces** el panel del propietario muestra B como la canción que suena en menos de 1 s.
- **Dado** una sesión de música abierta sin ningún reproductor en marcha **cuando** el propietario mira su panel **entonces** ve que no hay ningún reproductor activo.

### R015

- **Dado** el reproductor sonando A, con B pendiente **cuando** el propietario restablece la contraseña desde otro equipo **entonces** A suena hasta el final, el reproductor indica que hay que volver a iniciar sesión, B no empieza y la sesión de música sigue abierta.
- **Dado** el caso anterior **cuando** el propietario vuelve a iniciar sesión en el equipo del reproductor y lo pone en marcha **entonces** suena B, y A no vuelve a sonar.

## Requisitos no funcionales

- **Música sin silencios (Q5):** entre el final de una canción, o el fallo de una que se salta, y el inicio de la siguiente pendiente pasan menos de 3 s. Se mide entre canciones, no dentro de la publicidad que imponga la plataforma.
- **Tiempo real (Q4):** la canción que suena y los avisos de fallo se ven en el panel del propietario en menos de 1 s desde que cambian.
- **Aislamiento (Q6):** el 100 % de los intentos de leer o cambiar la sesión de música o el reproductor de otro establecimiento se rechaza.
- **Sin instalación (Q8):** el reproductor funciona en un navegador web de escritorio estándar, sin instalar nada.
- **Disponibilidad (Q3):** el reproductor y la sesión de música entran en el 99,5 % mensual del servicio.

## Supuestos

- El reproductor funciona en un navegador de escritorio actual (Chrome, Edge, Firefox o Safari) de un equipo del local conectado al sistema de sonido.
- Los navegadores exigen que una persona interactúe con la página antes de reproducir sonido. Por eso el reproductor se «pone en marcha» con una acción del propietario y no empieza a sonar solo al abrirse.
- El propietario inicia sesión en el equipo del reproductor con su cuenta. Mientras el reproductor suena, ese uso cuenta como actividad para la caducidad de la sesión iniciada (R020 de la feature 001).
- La sesión de música solo se cierra a mano. Si el propietario no la cierra, sigue abierta.
- La publicidad de la plataforma se reproduce y no se controla (brief, D1§4).
- Las canciones que ya sonaron se conservan porque las usarán B04 (ventana anti-repetición) y B07 (relleno desde el historial del local).

## Preguntas abiertas

> Cita entre paréntesis el requisito al que afecta cada pregunta:
> `- [ ] (R002) ¿Cuánto dura la sesión?`. Una pregunta abierta sobre un MUST
> impide aprobar la spec. Al resolverla, conviértela en requisito o criterio y
> borra la línea.

No quedan preguntas abiertas.

## Historial de cambios

> Lo rellena `/sdd:amend` cuando cambian los requisitos después de aprobar la
> spec: fecha, qué cambió, por qué y los IDs afectados.
- **2026-10-21 — Enmienda tras `/sdd:analyze`.**
  - **Aclaración sin cambio de comportamiento en R012:** se añade un criterio para el cambio a otro reproductor durante un corte de conexión. El texto de R012 ya lo pedía, pero sin un criterio que lo hiciera comprobable.
  - **Requisito nuevo R015:** qué pasa con la música si se cierra la sesión iniciada del equipo del reproductor, por ejemplo al restablecer la contraseña, que cierra todas las sesiones (R021 de la feature 001). La canción que suena termina, el reproductor pide volver a iniciar sesión y la sesión de música sigue abierta. Al volver a entrar, continúa en orden. Motivo: sin este requisito, la música del local se paraba a mitad de la sesión sin que nada lo indicara.
  - IDs afectados: R012 (aclarado), R015 (nuevo).
