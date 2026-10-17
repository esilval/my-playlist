# Backlog del producto

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · e312222e8aed |

> Features candidatas: unidades de valor observable que salen de los objetivos
> del brief. Una candidata no lleva requisitos («el sistema DEBERÁ…»); los
> redacta `/sdd:specify` cuando la feature arranca.
>
> Una candidata nunca se borra: si deja de tener sentido, su Estado pasa a
> `descartada`. Así su ID no se reutiliza. Sustituye todo texto en cursiva.
> Solo el usuario cambia el Estado de la cabecera, con `/discovery:approve`.

## Candidatas

### B01 — Alta del establecimiento y su QR

- **Estado:** candidata
- **Objetivos:** G2, G4
- **Origen:** D1§2, D1§5
- **Problema:** El propietario no tiene forma de poner su local en MyPlaylist ni de dar a sus clientes un punto de entrada.
- **Resultado observable:** El propietario crea su cuenta y su establecimiento desde la web, inicia sesión y descarga o imprime el QR único de su local.
- **Dentro:** Registro e inicio de sesión del propietario, datos del establecimiento, generación del QR por establecimiento.
- **Fuera:** Pagos y planes (B09), empleados, varios establecimientos por cuenta.
- **Depende de:** —

### B02 — Sesión de música y reproductor del local

- **Estado:** candidata
- **Objetivos:** G2, G3
- **Origen:** D1§1, D1§2
- **Problema:** Sin un reproductor en el local, las canciones pedidas no llegan a sonar.
- **Resultado observable:** El propietario abre la sesión en un navegador del local y las canciones de la cola suenan una tras otra en el orden pedido; si una no se puede reproducir, se salta y se avisa al propietario; al cerrar la sesión la música se detiene.
- **Dentro:** Abrir y cerrar sesión, reproducción en orden de la cola con YouTube, salto y aviso ante canciones que fallan.
- **Fuera:** Pedidos de clientes (B03), otras plataformas (Spotify descartada, B08), relleno (B07).
- **Depende de:** B01

### B03 — Pedir canciones desde el QR

- **Estado:** candidata
- **Objetivos:** G1
- **Origen:** D1§1, D1§2, D1§3
- **Problema:** Los clientes no tienen cómo influir en la música del local.
- **Resultado observable:** Un cliente escanea el QR, busca en YouTube por nombre, artista o álbum y agrega canciones a la cola de la sesión abierta, hasta 5 pendientes a la vez por dispositivo; al sonar una recupera el cupo.
- **Dentro:** Buscador para clientes anónimos, agregar a la cola, cupo de 5 simultáneas por dispositivo, aviso si la sesión está cerrada.
- **Fuera:** Anti-repetición (B04), cambio del cupo (B10), control de acceso fuera del local (decidido: no se controla).
- **Depende de:** B02

### B04 — Ventana anti-repetición

- **Estado:** candidata
- **Objetivos:** G1, G2
- **Origen:** D1§2
- **Problema:** La misma canción puede pedirse una y otra vez y cansar al local.
- **Resultado observable:** Una canción que sonó en las últimas horas no puede volver a pedirse; el cliente ve por qué, y el propietario ajusta las horas (3 por defecto).
- **Dentro:** Bloqueo de pedidos repetidos dentro de la ventana, configuración de la ventana por el propietario.
- **Fuera:** Filtros de contenido (decidido: sin filtro).
- **Depende de:** B03

### B05 — Administrar la cola de la sesión

- **Estado:** candidata
- **Objetivos:** G2
- **Origen:** D1§2, D1§3
- **Problema:** El propietario no puede corregir lo que suena en su local.
- **Resultado observable:** El propietario ve la cola de la sesión actual, reordena y elimina canciones, y agrega las suyas con su propio buscador, hasta 50 por sesión en el Plan Básico.
- **Dentro:** Vista de la cola para el propietario, reordenar, eliminar, agregar canciones del propietario con límite por sesión.
- **Fuera:** Agregado sin límite del Premium (B10).
- **Depende de:** B03

### B06 — Pantalla pública de la cola

- **Estado:** candidata
- **Objetivos:** G1
- **Origen:** D1§2
- **Problema:** Los clientes no saben qué suena ni cuándo llega su canción.
- **Resultado observable:** El propietario abre una URL de pantalla en cualquier pantalla del local y esta muestra en tiempo real la canción actual y las siguientes; su configuración queda guardada.
- **Dentro:** Página de pantalla por establecimiento, actualización en tiempo real, configuración guardada de la pantalla.
- **Fuera:** Detección de hardware de pantallas (decidido: no aplica en una web).
- **Depende de:** B02

### B07 — Relleno automático cuando la cola se vacía

- **Estado:** candidata
- **Objetivos:** G3
- **Origen:** D1§2
- **Problema:** Cuando nadie pide canciones, el local queda en silencio.
- **Resultado observable:** Con la sesión abierta y la cola vacía, entra una tanda de hasta 10 canciones, una por artista al azar, tomados de la lista de artistas del propietario o, si no la hay, del historial del local; las tandas se repiten mientras la sesión siga abierta.
- **Dentro:** Lista de artistas de relleno del propietario, selección al azar, tandas sucesivas.
- **Fuera:** Elección por géneros o ambientes.
- **Depende de:** B02

### B08 — Canciones de Spotify en la cola

- **Estado:** descartada (los términos de Spotify no permiten reproducirlo en un local comercial con fines de lucro; el piloto usa solo YouTube y, al crecer, un proveedor B2B con licencia — respuesta en Preguntas del brief, ADR-0010)
- **Objetivos:** G1, G2
- **Origen:** D1§2, D1§3, D1§4
- **Problema:** Solo hay música de YouTube y parte del catálogo que quieren los clientes está en Spotify.
- **Resultado observable:** El propietario conecta la cuenta de Spotify del local y clientes y propietario pueden buscar y agregar canciones de Spotify, que suenan mezcladas con las de YouTube en la misma cola.
- **Dentro:** Conexión de la cuenta de Spotify del establecimiento, búsqueda y reproducción de Spotify en la cola mixta.
- **Fuera:** Gestión de la suscripción de Spotify del local (D1§4), otras plataformas.
- **Depende de:** B03

### B09 — Prueba gratuita y suscripción

- **Estado:** candidata
- **Objetivos:** G4
- **Origen:** D1§6, D1§6.1
- **Problema:** MyPlaylist no tiene ingresos si los establecimientos pueden usarlo sin pagar.
- **Resultado observable:** Un establecimiento nuevo arranca con 30 días de prueba gratuita, elige y paga el Plan Básico o el Premium, y si la prueba o la suscripción vence no puede abrir sesión hasta pagar.
- **Dentro:** Prueba de 30 días, elección de plan, cobro mensual en COP con pasarela colombiana, bloqueo al vencer.
- **Fuera:** Funciones exclusivas del Premium (B10); precios y pasarela concreta siguen abiertos en el brief.
- **Depende de:** B01, B02

### B10 — Límites ampliados del Plan Premium

- **Estado:** candidata
- **Objetivos:** G2, G4
- **Origen:** D1§1, D1§6.1
- **Problema:** El propietario Premium no puede ajustar la música a su local más allá de los límites del Básico.
- **Resultado observable:** Un propietario con Plan Premium cambia el cupo de canciones por cliente y agrega canciones sin límite por sesión.
- **Dentro:** Cupo de clientes configurable y agregado sin límite del propietario, según plan.
- **Fuera:** «Personalización de la experiencia musical» (descartada por ahora) y soporte prioritario.
- **Depende de:** B05, B09

