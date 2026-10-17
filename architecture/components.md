# Componentes

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · c9fb391b1a56 |
| Producto | brief 0cb192594661 · backlog e312222e8aed |

> De qué partes está hecho el sistema. Cada componente dice qué hace y qué
> candidatas del backlog viven en él; toda candidata vigente tiene que estar
> en alguno. La aprobación añade aquí la fila `Producto` con la huella del
> brief y del backlog en que se apoya.
>
> Sustituye todo texto en cursiva. Solo el usuario cambia el Estado, con
> `/architecture:approve`.

## Componentes

### C1 — Cuentas y establecimientos

- **Responsabilidad:** registra al propietario, gestiona su inicio de sesión y los datos de su único establecimiento, y genera el QR fijo de cada local. Es la fuente de la identidad del establecimiento que usan los demás para aislar los datos (Q6). No decide si el establecimiento puede abrir sesión: eso lo dice C8.
- **Candidatas:** B01

### C2 — Sesión y cola

- **Responsabilidad:** mantiene la sesión de música de cada establecimiento y su cola: abrir y cerrar, orden de pedidos, cupo de pendientes por dispositivo, ventana anti-repetición, reorden y eliminación por el propietario, límites por plan y tandas de relleno cuando la cola se vacía. Es la única que modifica la cola; no busca canciones (C3), no reproduce (C4) ni difunde los cambios (C6).
- **Candidatas:** B02, B03, B04, B05, B07, B10

### C3 — Catálogo de plataformas

- **Responsabilidad:** busca canciones en el proveedor de música (YouTube en el piloto) a través de un adaptador y las normaliza a un formato común, para poder cambiar a un proveedor B2B sin tocar la cola. No decide qué entra en la cola (C2) ni reproduce (C4).
- **Candidatas:** B03, B05, B07

### C4 — Reproductor del local

- **Responsabilidad:** corre en un navegador del local, reproduce en orden la canción que le indica C2 con el reproductor del proveedor (YouTube en el piloto) tras el mismo adaptador, precarga la siguiente, detecta las que fallan y las salta avisando a C2. No decide el orden de la cola.
- **Candidatas:** B02

### C5 — Aplicación del cliente

- **Responsabilidad:** web móvil a la que lleva el QR: identifica anónimamente el dispositivo, permite buscar y pedir canciones, y muestra la cola, el cupo disponible y por qué se rechaza un pedido (sesión cerrada, cupo lleno, anti-repetición). Las reglas las aplica C2.
- **Candidatas:** B03, B04

### C6 — Difusión en tiempo real

- **Responsabilidad:** hace llegar a cada pantalla conectada de un establecimiento (clientes, panel, reproductor, pantalla de cola) los cambios de su cola y los avisos, como canciones que fallaron, sin mezclar establecimientos. No genera los cambios: los recibe de C2 y C4.
- **Candidatas:** B02, B06

### C7 — Panel del propietario

- **Responsabilidad:** interfaz web del propietario para abrir y cerrar la sesión, ver y administrar la cola, agregar sus canciones, configurar la ventana anti-repetición, la lista de artistas de relleno, el cupo Premium y la pantalla de cola y gestionar su plan. Delega cada regla en el componente que la tiene.
- **Candidatas:** B01, B02, B04, B05, B07, B09, B10

### C8 — Suscripciones y cobro

- **Responsabilidad:** lleva la prueba gratuita de 30 días, el plan de cada establecimiento (Básico o Premium) y el cobro mensual en COP con la pasarela colombiana; responde si un establecimiento puede abrir sesión y qué límites le tocan. No aplica los límites a la cola (C2).
- **Candidatas:** B09, B10

### C9 — Pantalla de cola

- **Responsabilidad:** página web por establecimiento, sin interacción, que muestra la canción actual y las siguientes con la configuración guardada por el propietario. Recibe los cambios de C6.
- **Candidatas:** B06
