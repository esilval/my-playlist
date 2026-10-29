# Spec: Pedir canciones desde el QR

| Campo  | Valor        |
| ------ | ------------ |
| ID     | `003-pedir-canciones-desde-qr`     |
| Fecha  | 2026-10-27     |
| Estado | Approved · 3c7d68505f6d        |
| Issue  | —            |
| Origen | B03 · G1 · D1§1, D1§2, D1§3 · C2, C3, C5 |

> Este documento describe **qué** y **por qué**, nunca **cómo**.
> Toda decisión de implementación (librerías, esquemas, servicios) va en `plan.md`.
>
> Sustituye todo texto en cursiva; si una sección no aplica, escribe
> «No aplica.». Solo el usuario cambia el Estado, con `/sdd:approve`.

## Problema

Los clientes no tienen cómo influir en la música del local. Hoy solo suena lo que el propietario pone; la página a la que lleva el QR muestra el nombre del establecimiento y nada más.

## Contexto

Feature creada desde la candidata B03 «Pedir canciones desde el QR» de `product/backlog.md`, con el producto de discovery aprobado.

- **G1 — Los clientes ponen su música en el local desde el móvil:** el cliente de un establecimiento escanea el QR del local, busca canciones y las pone en la cola sin instalar nada ni registrarse; ve qué suena y qué viene. Se nota en que las canciones pedidas suenan en el orden en que se pidieron, con un reparto justo entre clientes.
- **Origen D1§1** «Descripción»: `product/sources/D1-overview.md`. Los clientes piden sus canciones con un buscador al que se llega por el QR, hasta 5 por cliente, y suenan en el orden en que se pidieron.
- **Origen D1§2** «Propuesta»: `product/sources/D1-overview.md`. Toda búsqueda va asociada a un establecimiento, se busca por nombre, artista o álbum, y el límite de 5 canciones por cliente garantiza que todos tengan su oportunidad.
- **Origen D1§3** «Alcance»: `product/sources/D1-overview.md`.
- **Lo que ya existe:**
  - La página del QR, que muestra el nombre del establecimiento (feature 001, R012).
  - La sesión de música con su cola y el reproductor del local, que reproduce la cola en orden (feature 002). La cola solo recibía canciones de una herramienta de desarrollo; con esta feature las piden los clientes.
- **Decisiones del brief que esta feature aplica:**
  - El cliente es anónimo, identificado solo por su dispositivo.
  - El límite es de 5 canciones pendientes a la vez; al sonar una, se libera un cupo.
  - No se controla si el cliente está físicamente en el local.

## Alcance

### Dentro

- Desde la página del QR, un cliente anónimo busca canciones por nombre, artista o álbum en el proveedor de música.
- Agrega canciones al final de la cola de la sesión abierta, con un cupo de 5 pendientes a la vez por dispositivo, que recupera cuando una de las suyas empieza a sonar.
- Ve lo que suena, sus canciones pendientes y su cupo libre, actualizados en tiempo real.
- Recibe un aviso cuando no puede pedir: sesión cerrada, cupo lleno o canción que ya está en la cola.

### Fuera (non-goals)

- **Anti-repetición** de canciones que ya sonaron (B04). Aquí solo se rechaza una canción que ya está pendiente.
- **Cambiar el cupo de 5** (B10, Plan Premium).
- **Controlar que el cliente esté en el local.** Decidido: no se controla.
- **Ver la cola completa del local** (B06, pantalla pública). El cliente solo ve lo que suena y sus propios pedidos.
- **Retirar o reordenar canciones.** El cliente no puede retirar las suyas; solo el propietario administra la cola (B05).
- **Que el propietario agregue canciones** desde el panel (B05).
- **Relleno automático** cuando la cola se vacía (B07).
- **Otras plataformas,** como Spotify (B08 y ADR-0010).
- **Filtros de contenido.** Decidido: sin filtro.

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
| R001 | MUST      | CUANDO un cliente abre la página de un establecimiento desde su QR con la sesión de música abierta, el sistema DEBERÁ ofrecerle buscar canciones, sin pedirle registrarse ni ningún dato personal. |
| R002 | MUST      | El sistema DEBERÁ reconocer el mismo dispositivo en sus visitas sucesivas a la página de un establecimiento, sin guardar ningún dato personal del cliente, para aplicarle su cupo. |
| R003 | MUST      | CUANDO el cliente busca un texto, el sistema DEBERÁ mostrarle las canciones del proveedor de música que coinciden por nombre, artista o álbum, con su título y su autor. |
| R004 | SHOULD    | El sistema DEBERÁ mostrar en los resultados de la búsqueda solo canciones que se pueden reproducir en el local. |
| R005 | MUST      | CUANDO el cliente agrega una canción de los resultados, con la sesión de música abierta y cupo libre, el sistema DEBERÁ ponerla al final de la cola de la sesión y mostrarle que quedó pedida y su cupo actualizado. |
| R006 | MUST      | SI el cliente intenta agregar una canción con 5 canciones suyas pendientes en la cola, ENTONCES el sistema DEBERÁ rechazar el pedido sin cambiar la cola, e indicarle que llegó al máximo y que recuperará un cupo cuando empiece a sonar una de las suyas. |
| R007 | MUST      | CUANDO una canción pedida por el cliente empieza a sonar, se salta porque no se puede reproducir o se descarta al cerrar la sesión de música, el sistema DEBERÁ dejar de contarla en su cupo. |
| R008 | MUST      | SI la sesión de música del establecimiento está cerrada cuando el cliente abre su página o cuando intenta agregar una canción, ENTONCES el sistema DEBERÁ indicarle que en este momento no se pueden pedir canciones y no agregar nada. |
| R009 | MUST      | SI el cliente intenta agregar una canción que ya está pendiente en la cola de la sesión, la haya pedido él u otra persona, ENTONCES el sistema DEBERÁ rechazar el pedido sin cambiar la cola ni gastar su cupo, e indicarle que esa canción ya está en la cola. |
| R010 | MUST      | MIENTRAS el cliente tiene abierta la página del establecimiento con la sesión de música abierta, el sistema DEBERÁ mostrarle la canción que suena, sus canciones pendientes en el orden en que sonarán y su cupo libre, y actualizarlos cuando cambian sin que tenga que recargar la página. |
| R011 | MUST      | SI un cliente usa en un establecimiento la identificación de dispositivo que obtuvo en otro, ENTONCES el sistema DEBERÁ no reconocerla en ese establecimiento, tratarlo como un dispositivo nuevo, y no cambiar la cola del otro ni revelar los pedidos de ningún dispositivo distinto del suyo. |
| R012 | MUST      | SI el proveedor de música no puede atender una búsqueda, ENTONCES el sistema DEBERÁ indicarle al cliente que la búsqueda no está disponible en este momento y que lo intente de nuevo, sin afectar a la cola ni a su cupo. |
| R013 | SHOULD    | SI un mismo dispositivo hace más de 10 búsquedas en un minuto, ENTONCES el sistema DEBERÁ rechazar las siguientes hasta que pase el minuto, indicándole que espere. |
| R014 | MUST      | SI la canción que el cliente pide ya no existe o ya no se puede reproducir en el local, ENTONCES el sistema DEBERÁ rechazar el pedido sin cambiar la cola ni gastar su cupo, e indicarle que esa canción no está disponible y que elija otra. |

## Criterios de aceptación

### R001

- **Dado** un establecimiento con la sesión de música abierta **cuando** un cliente escanea su QR **entonces** la página muestra el nombre del establecimiento y un buscador de canciones, sin pedir registro, correo, teléfono ni instalar nada.

### R002

- **Dado** un cliente que pidió 2 canciones **cuando** cierra la página y vuelve a abrirla desde el QR en el mismo navegador **entonces** ve sus 2 canciones pendientes y un cupo libre de 3.
- **Dado** un cliente que usa la página **cuando** se revisa lo que el sistema guardó de él **entonces** no hay nombre, correo, teléfono ni ubicación: solo un identificador anónimo del dispositivo.

### R003

- **Dado** un cliente en la página de un establecimiento con la sesión abierta **cuando** busca el nombre de una canción, de un artista o de un álbum **entonces** ve una lista de canciones que coinciden, cada una con su título y su autor.
- **Dado** una búsqueda sin coincidencias **cuando** el cliente la hace **entonces** se le indica que no se encontraron canciones.

### R005

- **Dado** un cliente con 0 canciones pendientes y la cola con A pendiente **cuando** agrega B de los resultados **entonces** B queda en la cola después de A, el cliente ve B entre sus pendientes y su cupo libre pasa de 5 a 4.
- **Dado** el reproductor del local en espera, con la cola vacía **cuando** un cliente agrega una canción **entonces** esa canción empieza a sonar en el local.

### R006

- **Dado** un cliente con 5 canciones suyas pendientes **cuando** intenta agregar otra **entonces** el pedido se rechaza, la cola no cambia y el cliente ve que llegó al máximo y que recuperará un cupo cuando empiece a sonar una de las suyas.
- **Dado** dos clientes de un mismo establecimiento, uno con 5 pendientes **cuando** el otro agrega una canción **entonces** su pedido se acepta: el cupo es de cada dispositivo.

### R007

- **Dado** un cliente con 5 canciones pendientes **cuando** empieza a sonar una de ellas **entonces** su cupo libre pasa a 1 y puede agregar otra canción.
- **Dado** un cliente con una canción pendiente que no se puede reproducir **cuando** el reproductor la salta **entonces** deja de contar en su cupo.
- **Dado** un cliente con canciones pendientes **cuando** el propietario cierra la sesión de música y la vuelve a abrir **entonces** el cliente tiene su cupo completo de 5.

### R008

- **Dado** un establecimiento con la sesión de música cerrada **cuando** un cliente abre su página desde el QR **entonces** ve el nombre del establecimiento y un aviso de que en este momento no se pueden pedir canciones, sin buscador.
- **Dado** un cliente con la página abierta **cuando** el propietario cierra la sesión de música y el cliente intenta agregar una canción **entonces** el pedido se rechaza con el mismo aviso y la cola no cambia.

### R009

- **Dado** la canción A pendiente en la cola, pedida por otro cliente **cuando** un cliente intenta agregar A **entonces** el pedido se rechaza indicando que A ya está en la cola, y su cupo no cambia.
- **Dado** la canción A, que ya sonó en esta sesión y no está pendiente **cuando** un cliente la agrega **entonces** se acepta: las canciones que ya sonaron son cosa de B04.

### R010

- **Dado** un cliente con la página abierta y 2 canciones pendientes, B y C **cuando** termina la canción que sonaba y empieza B **entonces** el cliente ve B como la que suena, solo C entre sus pendientes y su cupo libre en 4, sin recargar la página.
- **Dado** un cliente con la página abierta **cuando** otro cliente agrega una canción **entonces** el primero no ve esa canción entre sus pendientes, porque no es suya.

### R011

- **Dado** un cliente que se identificó desde la página del establecimiento A, con 2 canciones pendientes allí **cuando** abre la página del establecimiento B **entonces** B lo trata como un dispositivo nuevo, con su cupo completo de 5 y sin pendientes, y no ve nada de sus pedidos en A.
- **Dado** ese mismo cliente **cuando** intenta pedir una canción en B con la identificación que obtuvo en A **entonces** la identificación no vale en B, la cola de A no cambia y la de B solo cambia si el pedido se acepta con su identificación de B.
- **Dado** dos clientes en el mismo establecimiento **cuando** cada uno consulta su estado **entonces** ninguno ve los pedidos del otro.

### R012

- **Dado** el proveedor de música caído o sin capacidad para atender **cuando** un cliente busca **entonces** ve que la búsqueda no está disponible en este momento y que lo intente de nuevo, y la cola y su cupo no cambian.

### R014

- **Dado** una canción que apareció en una búsqueda y después dejó de existir o de poder reproducirse fuera de su plataforma **cuando** el cliente la pide **entonces** el pedido se rechaza, la cola y su cupo no cambian, y el cliente ve que esa canción no está disponible y que elija otra.

## Requisitos no funcionales

- **Búsqueda rápida (Q1):** los resultados de una búsqueda aparecen en la pantalla del cliente en menos de 2 s, también con la carga de Q2.
- **Carga (Q2):** con 50 establecimientos con la sesión abierta y 100 clientes conectados en cada uno (5000 clientes), el sistema atiende búsquedas, pedidos y actualizaciones cumpliendo Q1 y Q4, sin rechazar peticiones salvo por el límite de R013. Es la hora pico: cada cliente hace de media 1 búsqueda cada 5 minutos y 1 pedido cada 10 minutos, así que en cada establecimiento entran unos 10 pedidos por minuto, y cada uno es un cambio que ven sus 100 clientes.
- **Tiempo real (Q4):** un pedido aceptado, o un cambio de la canción que suena, se ve en el móvil de los clientes conectados y en el panel del propietario en menos de 1 s.
- **Aislamiento (Q6):** el 100 % de los intentos de usar en un establecimiento la identificación de otro se rechaza, y 0 pedidos de otros dispositivos u otros establecimientos quedan expuestos.
- **Datos mínimos (Q7):** se guardan 0 datos personales del cliente, solo un identificador anónimo del dispositivo.
- **Sin instalación (Q8):** todo funciona en el navegador de un móvil actual, sin instalar nada.

## Supuestos

- El cliente usa un navegador de móvil actual, con el almacenamiento del sitio permitido.
- Si el cliente borra los datos del navegador, usa el modo privado o cambia de navegador, el sistema lo trata como un dispositivo nuevo, con su cupo completo. Se acepta, igual que no controlar si está en el local: el cupo reparte, no blinda.
- La búsqueda es de texto libre. El proveedor de música decide qué resultados coinciden por nombre, artista o álbum.
- La publicidad de la plataforma se reproduce y no se controla (brief, D1§4).
- El proveedor de música limita cuántas búsquedas se pueden hacer al día. Las búsquedas repetidas se pueden servir sin volver a preguntar al proveedor, y el límite de R013 evita que un dispositivo gaste la capacidad de todos.

## Preguntas abiertas

> Cita entre paréntesis el requisito al que afecta cada pregunta:
> `- [ ] (R002) ¿Cuánto dura la sesión?`. Una pregunta abierta sobre un MUST
> impide aprobar la spec. Al resolverla, conviértela en requisito o criterio y
> borra la línea.

- [ ] (R013) ¿Es razonable el límite de 10 búsquedas por minuto y dispositivo, o se ajusta tras medir el uso real en el piloto?

## Historial de cambios

> Lo rellena `/sdd:amend` cuando cambian los requisitos después de aprobar la
> spec: fecha, qué cambió, por qué y los IDs afectados.

- **2026-10-27 — Enmienda tras `/sdd:analyze`:**
  - **Aclaración de R011, sin cambio de comportamiento:** el criterio decía que el cliente con la identificación de A «no ve nada de B». Pero la página de B es pública: la ve cualquiera que abra su QR. Lo que se aísla es la identificación del dispositivo y los pedidos: en B, la identificación de A no vale y el cliente es un dispositivo nuevo, y nadie ve los pedidos de otro dispositivo. El requisito, sus criterios y Q6 quedan redactados así. Todavía no hay código ni pruebas de R011.
  - **Requisito nuevo R014:** qué pasa si la canción que el cliente pide ya no existe o ya no se puede reproducir. Motivo: el plan lo rechazaba sin que la spec dijera qué ve el cliente.
  - IDs afectados: R011 (aclarado), R014 (nuevo).

- **2026-10-28 — Aclaración de Q2, sin cambio de comportamiento:**
  - Q2 no decía cuánto pide cada cliente, y la prueba de carga hacía actuar a los 5000 clientes en unos 25 s (unas 2000 peticiones por segundo). Ahora fija el ritmo de la hora pico: de media, 1 búsqueda cada 5 minutos y 1 pedido cada 10 minutos por cliente.
  - IDs afectados: ninguno (Q2 es un requisito no funcional). Ninguna prueba que hoy pasa tiene que cambiar.
