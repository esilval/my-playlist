# Estándares

| Campo  | Valor |
| ------ | ----- |
| Estado | Approved · 3f462a2e26ee |

> Reglas comprobables que se derivan de las decisiones: capas, dirección de
> dependencias entre componentes, dependencias prohibidas. Cada estándar cita
> la decisión de la que sale.
>
> Sustituye todo texto en cursiva. Solo el usuario cambia el Estado, con
> `/architecture:approve`.

## Estándares

### S1 — Capas del monolito: API → aplicación → dominio, y la infraestructura implementa los puertos del dominio

- **Tipo:** capas
- **Detalle:** API (routers FastAPI) → aplicación (casos de uso) → dominio (reglas de cola, cupo, planes); infraestructura (Postgres, Redis, APIs de plataformas) → dominio. El dominio no importa FastAPI, SQLAlchemy ni clientes HTTP.
- **Decisión:** ADR-0001

### S2 — Solo Sesión y cola modifica la cola

- **Tipo:** dependencia
- **Detalle:** C7 → C2, C5 → C2, C4 → C2: el panel, la app del cliente y el reproductor cambian la cola solo por los casos de uso de C2; ningún otro módulo escribe en sus tablas.
- **Decisión:** ADR-0001

### S3 — Sesión y cola consulta plan y límites a Suscripciones

- **Tipo:** dependencia
- **Detalle:** C2 → C8: C2 pregunta a C8 si se puede abrir sesión y qué límites aplican; C8 no depende de C2.
- **Decisión:** ADR-0001

### S4 — Sesión y cola obtiene canciones solo a través del Catálogo

- **Tipo:** dependencia
- **Detalle:** C2 → C3: el relleno y la validación de pedidos usan la interfaz de C3; C2 no llama a la API del proveedor de música (YouTube en el piloto) ni conoce sus identificadores o formatos.
- **Decisión:** ADR-0010

### S5 — La difusión solo escucha: el monolito publica y el tiempo real reenvía

- **Tipo:** dependencia
- **Detalle:** C2 → C6 (eventos por Redis pub/sub); C6 → C9, C6 → C5, C6 → C7. C6 no escribe en PostgreSQL ni llama a la API del monolito para cambiar datos.
- **Decisión:** ADR-0005

### S6 — Los frontales no acceden a los almacenes ni a las APIs de plataformas

- **Tipo:** prohibida
- **Detalle:** La SPA (C4, C5, C7, C9) no conecta con PostgreSQL ni Redis, ni con la API de búsqueda del proveedor de música (YouTube Data API); solo usa la API del monolito, el servicio de tiempo real y el reproductor del proveedor en C4, tras su adaptador.
- **Decisión:** ADR-0003

### S7 — Sin bibliotecas no oficiales de plataformas

- **Tipo:** prohibida
- **Detalle:** yt-dlp, youtube-dl, ytmusicapi, pytube, scraping de YouTube, reproducir Spotify en el local, y claves de API embebidas en el frontal.
- **Decisión:** ADR-0010

### S8 — Toda tabla de negocio tiene establishment_id y política RLS

- **Tipo:** prohibida
- **Detalle:** Roles con BYPASSRLS en la API, tablas de negocio sin política RLS, y claves o canales de Redis y salas de Socket.IO sin prefijo de establecimiento.
- **Decisión:** ADR-0009

### S9 — Sin datos personales de clientes ni proveedores externos de identidad

- **Tipo:** prohibida
- **Detalle:** Campos de nombre, correo, teléfono o ubicación del cliente; SDK de Auth0, Clerk, Firebase Auth u otros proveedores de identidad.
- **Decisión:** ADR-0007

### S10 — Redis nunca es la única copia de un dato de negocio

- **Tipo:** prohibida
- **Detalle:** Escribir colas, cupos persistentes, historial o suscripciones solo en Redis; las reglas de la cola no se aplican fuera de transacciones de PostgreSQL.
- **Decisión:** ADR-0004
