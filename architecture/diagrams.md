# Diagramas de arquitectura

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · 6fb18dd48fe8 |

> Vistas C4 de contexto, contenedores y componentes, en Mermaid. Los nodos
> de componente se llaman por su ID (C1) y la comprobación los contrasta con
> components.md y standards.md. Solo el usuario cambia el Estado, con
> /architecture:approve.

## Contexto

Quién usa el sistema y con qué sistemas externos habla.

```mermaid
flowchart LR
  U1["Cliente del establecimiento<br/>[Persona]"]:::persona
  U2["Propietario del establecimiento<br/>[Persona]"]:::persona
  U1 -->|escanea el QR y pide canciones| SYS
  U2 -->|administra su local y su cola| SYS
  SYS["MyPlaylist<br/>[Sistema: SaaS web en AWS · ADR-0006]<br/>cola de canciones por establecimiento, pedida desde el QR"]:::sistema
  XYouTube["YouTube<br/>[Sistema externo]<br/>búsqueda (Data API) y reproductor IFrame"]:::externo
  XSES["Amazon SES<br/>[Sistema externo]<br/>correo transaccional"]:::externo
  XPasarela["Pasarela de pago colombiana<br/>[Sistema externo]<br/>cobro mensual en COP"]:::externo
  SYS -->|busca y reproduce · ADR-0010| XYouTube
  SYS -->|envía correos · ADR-0011| XSES
  XSES -. verificación y recuperación .-> U2
  SYS -->|cobra la suscripción · brief, sin ADR| XPasarela
  classDef persona fill:#08427b,stroke:#052e56,color:#fff
  classDef sistema fill:#1168bd,stroke:#0b4884,color:#fff
  classDef contenedor fill:#438dd5,stroke:#2e6295,color:#fff
  classDef externo fill:#999999,stroke:#6b6b6b,color:#fff
```

## Contenedores

Las piezas desplegables o almacenes del sistema y quién las usa.

```mermaid
flowchart LR
  U1["Cliente del establecimiento<br/>[Persona]"]:::persona
  U2["Propietario del establecimiento<br/>[Persona]"]:::persona
  subgraph SYS["MyPlaylist<br/>[Sistema: AWS us-east-1 · ADR-0006]"]
    C1["Cuentas y establecimientos<br/>[Contenedor: módulo del monolito FastAPI · PostgreSQL · ADR-0001, ADR-0002, ADR-0004]<br/>registra al propietario, gestiona su inicio de sesión y los datos de su único establecimiento, y genera el QR fijo de cada local. Es la fuente de la identidad del establecimiento que usan los demás para aislar los datos (Q6). No decide si el establecimiento puede abrir sesión: eso lo dice C8."]:::contenedor
    C2["Sesión y cola<br/>[Contenedor: módulo del monolito FastAPI · PostgreSQL y Redis · ADR-0001, ADR-0004]<br/>mantiene la sesión de música de cada establecimiento y su cola: abrir y cerrar, orden de pedidos, cupo de pendientes por dispositivo, ventana anti-repetición, reorden y eliminación por el propietario, límites por plan y tandas de relleno cuando la cola se vacía. Es la única que modifica la cola; no busca canciones (C3), no reproduce (C4) ni difunde los cambios (C6)."]:::contenedor
    C3["Catálogo de plataformas<br/>[Contenedor: módulo del monolito FastAPI · adaptador de YouTube · ADR-0001, ADR-0010]<br/>busca canciones en el proveedor de música (YouTube en el piloto) a través de un adaptador y las normaliza a un formato común, para poder cambiar a un proveedor B2B sin tocar la cola. No decide qué entra en la cola (C2) ni reproduce (C4)."]:::contenedor
    C4["Reproductor del local<br/>[Contenedor: SPA React en el navegador del local · reproductor de YouTube · ADR-0003, ADR-0010]<br/>corre en un navegador del local, reproduce en orden la canción que le indica C2 con el reproductor del proveedor (YouTube en el piloto) tras el mismo adaptador, precarga la siguiente, detecta las que fallan y las salta avisando a C2. No decide el orden de la cola."]:::contenedor
    C5["Aplicación del cliente<br/>[Contenedor: SPA React, web móvil · ADR-0003]<br/>web móvil a la que lleva el QR: identifica anónimamente el dispositivo, permite buscar y pedir canciones, y muestra la cola, el cupo disponible y por qué se rechaza un pedido (sesión cerrada, cupo lleno, anti-repetición). Las reglas las aplica C2."]:::contenedor
    C6["Difusión en tiempo real<br/>[Contenedor: servicio Node + Socket.IO · Redis pub/sub · ADR-0005]<br/>hace llegar a cada pantalla conectada de un establecimiento (clientes, panel, reproductor, pantalla de cola) los cambios de su cola y los avisos, como canciones que fallaron, sin mezclar establecimientos. No genera los cambios: los recibe de C2 y C4."]:::contenedor
    C7["Panel del propietario<br/>[Contenedor: SPA React · ADR-0003]<br/>interfaz web del propietario para abrir y cerrar la sesión, ver y administrar la cola, agregar sus canciones, configurar la ventana anti-repetición, la lista de artistas de relleno, el cupo Premium y la pantalla de cola y gestionar su plan. Delega cada regla en el componente que la tiene."]:::contenedor
    C8["Suscripciones y cobro<br/>[Contenedor: módulo del monolito FastAPI · PostgreSQL · ADR-0001]<br/>lleva la prueba gratuita de 30 días, el plan de cada establecimiento (Básico o Premium) y el cobro mensual en COP con la pasarela colombiana; responde si un establecimiento puede abrir sesión y qué límites le tocan. No aplica los límites a la cola (C2)."]:::contenedor
    C9["Pantalla de cola<br/>[Contenedor: SPA React · ADR-0003]<br/>página web por establecimiento, sin interacción, que muestra la canción actual y las siguientes con la configuración guardada por el propietario. Recibe los cambios de C6."]:::contenedor
  end
  U1 -->|escanea el QR y pide canciones| C5
  U1 -. mira lo que suena .-> C9
  U2 -->|administra su local y su cola| C7
  U2 -->|abre el reproductor en el local| C4
  XYouTube["YouTube<br/>[Sistema externo]<br/>búsqueda (Data API) y reproductor IFrame"]:::externo
  XSES["Amazon SES<br/>[Sistema externo]<br/>correo transaccional"]:::externo
  XPasarela["Pasarela de pago colombiana<br/>[Sistema externo]<br/>cobro mensual en COP"]:::externo
  C3 -->|busca canciones · ADR-0010| XYouTube
  C4 -->|reproduce · ADR-0010| XYouTube
  C1 -->|envía correos · ADR-0011| XSES
  XSES -. verificación y recuperación .-> U2
  C8 -->|cobra · brief, sin ADR| XPasarela
  classDef persona fill:#08427b,stroke:#052e56,color:#fff
  classDef sistema fill:#1168bd,stroke:#0b4884,color:#fff
  classDef contenedor fill:#438dd5,stroke:#2e6295,color:#fff
  classDef externo fill:#999999,stroke:#6b6b6b,color:#fff
```

## Componentes

Las partes del sistema y sus dependencias, cada una con la decisión (ADR) de la que sale.

```mermaid
flowchart LR
  subgraph SYS["MyPlaylist<br/>[Sistema]"]
    C1["Cuentas y establecimientos<br/>[Componente]<br/>registra al propietario, gestiona su inicio de sesión y los datos de su único establecimiento, y genera el QR fijo de cada local. Es la fuente de la identidad del establecimiento que usan los demás para aislar los datos (Q6). No decide si el establecimiento puede abrir sesión: eso lo dice C8."]:::contenedor
    C2["Sesión y cola<br/>[Componente]<br/>mantiene la sesión de música de cada establecimiento y su cola: abrir y cerrar, orden de pedidos, cupo de pendientes por dispositivo, ventana anti-repetición, reorden y eliminación por el propietario, límites por plan y tandas de relleno cuando la cola se vacía. Es la única que modifica la cola; no busca canciones (C3), no reproduce (C4) ni difunde los cambios (C6)."]:::contenedor
    C3["Catálogo de plataformas<br/>[Componente]<br/>busca canciones en el proveedor de música (YouTube en el piloto) a través de un adaptador y las normaliza a un formato común, para poder cambiar a un proveedor B2B sin tocar la cola. No decide qué entra en la cola (C2) ni reproduce (C4)."]:::contenedor
    C4["Reproductor del local<br/>[Componente]<br/>corre en un navegador del local, reproduce en orden la canción que le indica C2 con el reproductor del proveedor (YouTube en el piloto) tras el mismo adaptador, precarga la siguiente, detecta las que fallan y las salta avisando a C2. No decide el orden de la cola."]:::contenedor
    C5["Aplicación del cliente<br/>[Componente]<br/>web móvil a la que lleva el QR: identifica anónimamente el dispositivo, permite buscar y pedir canciones, y muestra la cola, el cupo disponible y por qué se rechaza un pedido (sesión cerrada, cupo lleno, anti-repetición). Las reglas las aplica C2."]:::contenedor
    C6["Difusión en tiempo real<br/>[Componente]<br/>hace llegar a cada pantalla conectada de un establecimiento (clientes, panel, reproductor, pantalla de cola) los cambios de su cola y los avisos, como canciones que fallaron, sin mezclar establecimientos. No genera los cambios: los recibe de C2 y C4."]:::contenedor
    C7["Panel del propietario<br/>[Componente]<br/>interfaz web del propietario para abrir y cerrar la sesión, ver y administrar la cola, agregar sus canciones, configurar la ventana anti-repetición, la lista de artistas de relleno, el cupo Premium y la pantalla de cola y gestionar su plan. Delega cada regla en el componente que la tiene."]:::contenedor
    C8["Suscripciones y cobro<br/>[Componente]<br/>lleva la prueba gratuita de 30 días, el plan de cada establecimiento (Básico o Premium) y el cobro mensual en COP con la pasarela colombiana; responde si un establecimiento puede abrir sesión y qué límites le tocan. No aplica los límites a la cola (C2)."]:::contenedor
    C9["Pantalla de cola<br/>[Componente]<br/>página web por establecimiento, sin interacción, que muestra la canción actual y las siguientes con la configuración guardada por el propietario. Recibe los cambios de C6."]:::contenedor
  end
  C7 -->|usa · ADR-0001| C2
  C5 -->|usa · ADR-0001| C2
  C4 -->|usa · ADR-0001| C2
  C2 -->|usa · ADR-0001| C8
  C2 -->|usa · ADR-0010| C3
  C2 -->|usa · ADR-0005| C6
  C6 -->|usa · ADR-0005| C9
  C6 -->|usa · ADR-0005| C5
  C6 -->|usa · ADR-0005| C7
  C7 -->|inicia sesión y edita el local · ADR-0007| C1
  C5 -->|resuelve el QR y el token anónimo · ADR-0007| C1
  C2 -->|resuelve el establecimiento · ADR-0009| C1
  C6 -->|usa · ADR-0005| C4
  classDef persona fill:#08427b,stroke:#052e56,color:#fff
  classDef sistema fill:#1168bd,stroke:#0b4884,color:#fff
  classDef contenedor fill:#438dd5,stroke:#2e6295,color:#fff
  classDef externo fill:#999999,stroke:#6b6b6b,color:#fff
```
