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
