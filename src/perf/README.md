# Pruebas de carga

Pruebas de carga con [k6](https://k6.io/) para comprobar los requisitos de rendimiento. No hace falta instalar k6: se usa su imagen oficial dentro de la red de docker-compose.

## `accounts.js` — feature 001

Comprueba el requisito de rendimiento de la feature 001: registro, inicio de sesión y descarga del QR deben responder en menos de 2 s en el percentil 95, con 50 establecimientos a la vez.

Cada usuario virtual (50, con 2 iteraciones cada uno):
1. se registra;
2. espera el correo de verificación en Mailpit y abre el enlace;
3. inicia sesión;
4. descarga el QR.

**Umbrales:**
- `p(95) < 2000 ms` para `register`, `login` y `qr`;
- el 100 % de los `checks` tiene que pasar.

La espera del correo y la verificación se ejecutan pero no tienen umbral.

### Cómo correrla

Desde `src/`, con el entorno levantado:

```bash
docker compose up -d --build
docker run --rm -i --network myplaylist_default -v "$PWD/perf:/perf" \
  grafana/k6 run /perf/accounts.js
```

Variables opcionales (`-e NOMBRE=valor` en `docker run`):

| Variable | Por defecto | Para qué |
| -------- | ----------- | -------- |
| `API_URL` | `http://api:8000` | API |
| `MAILPIT_URL` | `http://mailpit:8025` | Mailpit, para leer el enlace de verificación |
| `ORIGIN` | `http://localhost:5173` | `Origin` de las peticiones; la API rechaza cualquier otro |

### Resultados

La cabecera de `accounts.js` guarda la tabla de medidas que fijó los parámetros de Argon2id (plan D3). Con la configuración elegida (19 MiB, t=2, p=1), en local con 8 CPU, el p95 queda en 0,89 s para el registro, 0,24 s para el inicio de sesión y 0,35 s para el QR.

Hay que repetir la prueba si cambian los parámetros de Argon2 (`ARGON2_*`) o la CPU de las tareas, y anotar el resultado en la cabecera.

## `client.js` — feature 003

Comprueba el rendimiento del cliente que pide canciones desde el QR (spec de la feature 003, Q1, Q2 y Q4; plan D10). Es la hora pico de varios establecimientos con la sesión de música abierta y 100 clientes conectados en cada uno.

**Preparación, sin medir:** cada establecimiento se registra, verifica el correo y abre su sesión de música. Sus 100 móviles abren la página del QR y reciben la cookie de su dispositivo.

**Escenario:** 1 minuto de subida y 10 minutos a ritmo constante:
- cada cliente busca de media 1 vez cada 5 minutos, la mitad de las veces algo popular, que sale de la caché;
- cada cliente pide 1 canción cada 10 minutos;
- tras cada pedido, los 100 clientes de ese establecimiento vuelven a pedir su estado, como hace el tiempo real: en 3 tandas que salen a los 0, 100 y 200 ms, cada una sin esperar a la anterior.

No suena nada: el escenario no incluye los cambios de canción ni su reparto, solo el de los pedidos (plan D10).

**Umbrales:**
- `p(95) < 2000 ms` para la búsqueda (Q1);
- `p(95) < 1000 ms` para el estado del cliente (Q4, en el servidor);
- ninguna respuesta 5xx ni sin respuesta;
- el 100 % de los `checks`: búsquedas con resultados, pedidos aceptados y estados abiertos. Un pedido rechazado porque el cliente elegido al azar ya tenía 5 pendientes cuenta como correcto, porque lo provoca el escenario;
- menos de 10 de esos rechazos (`quota_rejections`): un pedido rechazado no reparte nada, así que con muchos la prueba mediría menos carga de la anunciada;
- alguna búsqueda y algún estado medidos: un p95 sin muestras no mide nada.

### A escala en local, Q2 completo en la infraestructura

Por defecto corre **a escala**, con 20 establecimientos y 2000 clientes, unas 345 peticiones por segundo. Es la prueba de regresión en local. Con 50 establecimientos, la carga completa de Q2 (unas 870 peticiones por segundo) no cabe en un portátil junto con la API, PostgreSQL y el propio k6. **Q2 completo se mide en la feature de infraestructura**, contra un entorno parecido al de producción, con `ESTABLISHMENTS=50`.

### Cómo correrla

Desde `src/`, con el entorno levantado (la API arranca con 4 procesos, ADR-0015):

```bash
docker compose up -d --build
caffeinate -i docker run --rm -i --network myplaylist_default -v "$PWD/perf:/perf" \
  grafana/k6 run /perf/client.js
```

`caffeinate -i` (macOS) impide que el equipo se suspenda durante la prueba, que dura unos 13 minutos. Si se suspende, las duraciones salen falseadas.

Variables opcionales (`-e NOMBRE=valor` en `docker run`), además de `API_URL`, `MAILPIT_URL` y `ORIGIN`:

| Variable | Por defecto | Para qué |
| -------- | ----------- | -------- |
| `ESTABLISHMENTS` | `20` | Establecimientos; `50` es Q2 completo |
| `CLIENTS_PER_ESTABLISHMENT` | `100` | Clientes conectados por establecimiento |
| `STEADY` | `10m` | Duración del tramo a ritmo constante |

### Resultados

La cabecera de `client.js` guarda la tabla de corridas, también las que no cumplieron y por qué. Hay que repetir la prueba si cambian las rutas del cliente, la lectura de su estado, los procesos de la API (`API_WORKERS`) o el pool de conexiones, y anotar el resultado en la cabecera.
