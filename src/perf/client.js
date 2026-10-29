// Prueba de carga de B03 (spec Q1, Q2, Q4; plan D10): la hora pico de establecimientos con
// la sesión de música abierta y 100 clientes conectados en cada uno.
//
// En local corre a escala, con 20 establecimientos (2000 clientes), como prueba de
// regresión: un portátil no aloja a la vez la carga completa, la API, PostgreSQL y k6. Q2
// completo son 50 establecimientos (5000 clientes, ESTABLISHMENTS=50) y se mide en la
// feature de infraestructura, contra un entorno parecido al de producción.
//
// Cada cliente busca de media 1 vez cada 5 minutos y pide 1 canción cada 10 minutos (Q2).
// Cada pedido cambia la cola, y los 100 clientes de ese establecimiento vuelven a pedir
// su estado, como hace el tiempo real (D6), repartidos en 300 ms. Umbrales: p95 de la
// búsqueda < 2 s (Q1), p95 del estado < 1 s (Q4) y ninguna respuesta 5xx.
//
// Corre dentro de la red de docker-compose, contra la API con el catálogo falso y 4
// procesos (ADR-0015), desde src/:
//   docker compose up -d --build
//   docker run --rm -i --network myplaylist_default -v "$PWD/perf:/perf" \
//     grafana/k6 run /perf/client.js
// En macOS, con `caffeinate -i` delante, para que el equipo no se suspenda a mitad.
//
// Resultados (local: Docker Desktop con 8 CPU y 3,8 GiB). Hasta el 2026-10-28, el pool de
// cada proceso era el de SQLAlchemy por defecto (5 + 10 de desborde); desde la última fila,
// es fijo, de 15 (plan D11):
//
//   fecha       escenario                                 procesos  p95 búsqueda  p95 estado  5xx     ¿cumple?
//   2026-10-28  5000 clientes a la vez, recorrido entero  1         59,6 s        —           11 827  no
//   2026-10-28  1000 clientes a la vez, recorrido entero  1         3,07 s        —           0       no
//   2026-10-28  hora pico, 50 establecimientos            4         16 min        60 s        38 020  no
//   2026-10-28  hora pico, 20 establecimientos            4         5 s           3,39 s      2       no
//   2026-10-29  hora pico, 20 establecimientos, pool fijo 4         39 ms         51 ms       0       sí (*)
//   2026-10-29  hora pico, 20 establecimientos, pool fijo 4         44 ms         83 ms       0       sí
//
// Las dos primeras filas son la versión anterior de esta prueba: cada cliente hacía su
// recorrido entero en unos 25 s, unas 2000 peticiones por segundo con 5000. La API quedaba
// en un núcleo al 100 %, y los 5xx eran esperas de más de 30 s por una conexión del pool.
// De ahí la aclaración de Q2, la lectura propia de ClientView (D4) y ADR-0015.
//
// Con 50 establecimientos y el pool anterior, la máquina no daba más: con 1000 peticiones por segundo, la API
// ocupaba 3,8 núcleos, PostgreSQL 1,6 y k6 1,1. Con 20 (unas 320 peticiones por segundo),
// tampoco cumplió, y PostgreSQL llegaba a 3,7 núcleos. Una corrida anterior con 20 cumplió
// (0,99 s y 0,62 s), pero el equipo se suspendió a mitad y repartió la carga: no cuenta.
//
// (*) Con un reparto más suave que el de D10: k6 limitaba a 20 las peticiones en paralelo
// de cada tanda, y cada tanda esperaba a la anterior. No cuenta.
//
// La última fila es la que cierra T014: el pool fijo de 15 conexiones por proceso (plan
// D11), el equipo enchufado y `caffeinate`, y el reparto en 3 tandas que salen a los 0, 100
// y 200 ms sin esperarse. 218 222 peticiones a unas 328 por segundo: 4200 búsquedas,
// 2100 pedidos (2 rechazados por el cupo) y 209 800 estados, todas correctas, con un
// máximo de 2,55 s. Sin el desborde del pool, PostgreSQL ya no repite la consulta
// de tipos de asyncpg en cada conexión nueva. Q2 completo (ESTABLISHMENTS=50) queda para
// la feature de infraestructura.
import { check, fail, sleep } from "k6";
import exec from "k6/execution";
import http from "k6/http";
import { Counter } from "k6/metrics";
import { setTimeout } from "k6/timers";

const API = __ENV.API_URL || "http://api:8000";
const MAILPIT = __ENV.MAILPIT_URL || "http://mailpit:8025";
// El origen de la SPA: la API rechaza otro (protección CSRF).
const ORIGIN = __ENV.ORIGIN || "http://localhost:5173";
const ESTABLISHMENTS = Number(__ENV.ESTABLISHMENTS || 20);
const CLIENTS_PER_ESTABLISHMENT = Number(__ENV.CLIENTS_PER_ESTABLISHMENT || 100);
const CLIENTS = ESTABLISHMENTS * CLIENTS_PER_ESTABLISHMENT;
// Duración del tramo estable, tras 1 minuto de subida.
const STEADY = __ENV.STEADY || "10m";
const PASSWORD = "contraseña-segura";
const HEADERS = { "Content-Type": "application/json", "X-MyPlaylist-Client": "web", Origin: ORIGIN };
// Lo que más se busca en un bar: repetidas entre clientes, salen de la caché (D2).
const POPULAR = ["salsa", "vallenato", "reggaeton", "rock en español", "bachata"];
// El estado de los clientes del establecimiento tras un pedido: en 3 tandas que salen a
// los 0, 100 y 200 ms, sin esperar a la anterior (D6, D10).
const FANOUT_WAVES = 3;
const FANOUT_GAP_MS = 100;

// Por minuto (Q2): una búsqueda cada 5 minutos y un pedido cada 10 por cliente.
const SEARCHES_PER_MINUTE = Math.round(CLIENTS / 5);
const REQUESTS_PER_MINUTE = Math.round(CLIENTS / 10);

function arrivals(perMinute, scenario) {
  return {
    executor: "ramping-arrival-rate",
    exec: scenario,
    startRate: 0,
    timeUnit: "1m",
    stages: [
      { target: perMinute, duration: "1m" },
      { target: perMinute, duration: STEADY },
    ],
    preAllocatedVUs: 50,
    maxVUs: 500,
  };
}

export const options = {
  setupTimeout: "10m",
  // La preparación abre a la vez la página de los 100 móviles de cada establecimiento.
  batch: CLIENTS_PER_ESTABLISHMENT,
  batchPerHost: CLIENTS_PER_ESTABLISHMENT,
  scenarios: {
    searches: arrivals(SEARCHES_PER_MINUTE, "searchSong"),
    requests: arrivals(REQUESTS_PER_MINUTE, "requestSong"),
  },
  thresholds: {
    "http_req_duration{name:search}": ["p(95)<2000"],
    "http_req_duration{name:state}": ["p(95)<1000"],
    server_errors: ["count==0"],
    checks: ["rate==1"],
    // Sin estos, la prueba podría pasar con menos carga de la anunciada: un pedido
    // rechazado por el cupo no reparte nada, y un p95 sin muestras no mide nada.
    quota_rejections: ["count<10"],
    "http_reqs{name:state}": ["count>0"],
    "http_reqs{name:search}": ["count>0"],
  },
};

// Respuestas 5xx, o ninguna respuesta (una espera agotada).
const serverErrors = new Counter("server_errors");
// Pedidos de un cliente que ya tenía 5 pendientes: lo provoca el azar del escenario.
const quotaRejections = new Counter("quota_rejections");

function track(response) {
  if (response.status >= 500 || response.status === 0) serverErrors.add(1);
  return response;
}

// La cookie es `Secure`: el jar de k6 no la reenvía por http, así que viaja a mano.
function cookie(response, name) {
  const found = response.cookies[name];
  return found && found.length > 0 ? found[0].value : null;
}

function verificationToken(email) {
  for (let attempt = 0; attempt < 60; attempt++) {
    const search = http.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`);
    const found = search.json("messages");
    if (found && found.length > 0) {
      const message = http.get(`${MAILPIT}/api/v1/message/${found[0].ID}`);
      const match = /\/verificar\?token=([A-Za-z0-9_-]+)/.exec(message.json("Text"));
      if (match) return match[1];
    }
    sleep(1);
  }
  fail(`no llegó el correo de verificación de ${email}`);
}

// Sin medir: los establecimientos, verificados y con la sesión abierta, y los móviles de
// cada uno, que abren la página del QR y reciben la cookie de su dispositivo.
export function setup() {
  const { version } = http.get(`${API}/api/public/data-policy`).json();
  const run = Date.now();
  const emails = [];
  for (let n = 0; n < ESTABLISHMENTS; n++) {
    const email = `carga-cliente-${run}-${n}@ejemplo.com`;
    const register = http.post(
      `${API}/api/auth/register`,
      JSON.stringify({
        email,
        password: PASSWORD,
        establishment_name: `Bar ${n}`,
        data_authorization: true,
        policy_version: version,
      }),
      { headers: HEADERS },
    );
    if (register.status !== 202) fail(`registro ${register.status}`);
    emails.push(email);
  }
  const establishments = [];
  for (const email of emails) {
    const verify = http.post(`${API}/api/auth/verify-email`, JSON.stringify({ token: verificationToken(email) }), {
      headers: HEADERS,
    });
    const session = cookie(verify, "mp_session");
    if (verify.status !== 200 || !session) fail(`verificación ${verify.status}`);
    const owner = { headers: HEADERS, cookies: { mp_session: session } };
    const opened = http.post(`${API}/api/owner/music-session`, null, owner);
    if (opened.status !== 201) fail(`abrir la sesión ${opened.status}`);
    const url = http.get(`${API}/api/owner/me`, owner).json("establishment.public_url");
    if (!url) fail("sin URL pública");
    const code = url.split("/l/")[1];
    const pages = http.batch(
      Array.from({ length: CLIENTS_PER_ESTABLISHMENT }, () => ({
        method: "GET",
        url: `${API}/api/public/establishments/${code}/music`,
        params: { headers: HEADERS },
      })),
    );
    const devices = pages.map((page) => cookie(page, "mp_device"));
    if (devices.some((device) => !device)) fail("un móvil sin cookie");
    establishments.push({ code, devices });
  }
  return { establishments };
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

/** Un cliente cualquiera de un establecimiento cualquiera. */
function anyClient(data) {
  const establishment = pick(data.establishments);
  return {
    establishment,
    device: pick(establishment.devices),
    base: `${API}/api/public/establishments/${establishment.code}`,
  };
}

const asClient = (device, name) => ({ headers: HEADERS, cookies: { mp_device: device }, tags: { name } });

export function searchSong(data) {
  const { device, base } = anyClient(data);
  // La mitad, lo popular; la otra mitad, algo que nadie más busca.
  const query = Math.random() < 0.5 ? pick(POPULAR) : `canción ${exec.scenario.iterationInTest}`;
  const search = track(http.get(`${base}/search?q=${encodeURIComponent(query)}`, asClient(device, "search")));
  check(search, {
    "búsqueda 200 con resultados": (r) => r.status === 200 && r.json("results").length > 0,
  });
}

export async function requestSong(data) {
  const { establishment, device, base } = anyClient(data);
  // Una referencia que no pidió nadie: el catálogo falso la reconoce (D1).
  const ref = `fake:pedido${exec.scenario.iterationInTest}-1`;
  const request = track(http.post(`${base}/requests`, JSON.stringify({ ref }), asClient(device, "request")));
  const quotaFull = request.status === 409 && request.json("error") === "quota_exceeded";
  check(request, { "pedido 201, o 409 por el cupo": (r) => r.status === 201 || quotaFull });
  if (quotaFull) quotaRejections.add(1);
  if (request.status !== 201) return;

  // El cambio llega a los móviles del establecimiento, y cada uno pide su estado (D6). Cada
  // tanda sale a su hora aunque la anterior no haya terminado, como móviles independientes.
  const perWave = Math.ceil(establishment.devices.length / FANOUT_WAVES);
  const waves = [];
  for (let wave = 0; wave < FANOUT_WAVES; wave++) {
    const devices = establishment.devices.slice(wave * perWave, (wave + 1) * perWave);
    waves.push(
      new Promise((resolve) => {
        setTimeout(() => {
          resolve(
            Promise.all(devices.map((other) => http.asyncRequest("GET", `${base}/music`, null, asClient(other, "state")))),
          );
        }, wave * FANOUT_GAP_MS);
      }),
    );
  }
  for (const state of (await Promise.all(waves)).flat()) {
    track(state);
    check(state, { "estado 200 y abierto": (r) => r.status === 200 && r.json("status") === "open" });
  }
}
