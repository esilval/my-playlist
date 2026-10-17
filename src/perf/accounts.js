// Prueba de carga de B01 (spec, RNF de rendimiento; plan D3): 50 establecimientos a la
// vez se registran, verifican el correo, entran y descargan el QR. Cada petición medida
// debe responder en menos de 2 s en el percentil 95.
//
// Corre dentro de la red de docker-compose, contra la API y Mailpit, desde src/:
//   docker compose up -d --build
//   docker run --rm -i --network myplaylist_default -v "$PWD/perf:/perf" \
//     grafana/k6 run /perf/accounts.js
//
// Resultado (2026-10-17, local: Docker Desktop con 8 CPU y 3,8 GiB; una API uvicorn de un
// proceso; 50 VU × 2 iteraciones; p95 por petición):
//
//   Argon2id                         registro  inicio  QR      memoria API  ¿cumple?
//   64 MiB, t=3, p=4 (librería)      3,99 s    1,28 s  1,74 s  —            no
//   64 MiB, t=3, p=1 (~150 ms)       4,87 s    3,95 s  2,03 s  510 MiB      no
//   46 MiB, t=1, p=1 (OWASP)         1,84 s    0,50 s  0,56 s  200 MiB      justo
//   19 MiB, t=2, p=1 (OWASP)         0,89 s    0,24 s  0,35 s  353 MiB      sí  ← elegido
//
// La primera fila se midió con Argon2 aún dentro del bucle de eventos. Las demás, con el
// hash en hilos y como mucho uno por núcleo (app/shared/cpu.py): sin ese tope, con
// 64 MiB llegaba a 60 s y 2,5 GiB. Los parámetros quedan en app/shared/config.py.
// La memoria es el pico de `docker stats` durante la corrida: orientativa y ruidosa (el
// asignador no devuelve la memoria al sistema); sirve para ver el salto sin tope, no para
// comparar filas entre sí.
import { check, fail, sleep } from "k6";
import http from "k6/http";
import exec from "k6/execution";

const API = __ENV.API_URL || "http://api:8000";
const MAILPIT = __ENV.MAILPIT_URL || "http://mailpit:8025";
// El origen de la SPA: la API rechaza otro (protección CSRF, plan D9).
const ORIGIN = __ENV.ORIGIN || "http://localhost:5173";
const PASSWORD = "contraseña-segura";
const HEADERS = { "Content-Type": "application/json", "X-MyPlaylist-Client": "web", Origin: ORIGIN };

export const options = {
  scenarios: {
    owners: { executor: "per-vu-iterations", vus: 50, iterations: 2, maxDuration: "5m" },
  },
  thresholds: {
    "http_req_duration{name:register}": ["p(95)<2000"],
    "http_req_duration{name:login}": ["p(95)<2000"],
    "http_req_duration{name:qr}": ["p(95)<2000"],
    checks: ["rate==1"],
  },
};

export function setup() {
  const policy = http.get(`${API}/api/public/data-policy`).json();
  return { policyVersion: policy.version };
}

// El enlace llega por el trabajador de la bandeja de salida; su espera no se mide.
function verificationToken(email) {
  for (let attempt = 0; attempt < 60; attempt++) {
    const search = http.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`, {
      tags: { name: "mailpit" },
    });
    const found = search.json("messages");
    if (found && found.length > 0) {
      const message = http.get(`${MAILPIT}/api/v1/message/${found[0].ID}`, { tags: { name: "mailpit" } });
      const match = /\/verificar\?token=([A-Za-z0-9_-]+)/.exec(message.json("Text"));
      if (match) return match[1];
    }
    sleep(1);
  }
  fail(`no llegó el correo de verificación de ${email}`);
}

// La cookie es `Secure`: el jar de k6 no la reenvía por http, así que viaja a mano.
function session(response) {
  const cookie = response.cookies.mp_session;
  return cookie && cookie.length > 0 ? cookie[0].value : null;
}

export default function (data) {
  const email = `carga-${exec.vu.idInTest}-${exec.vu.iterationInScenario}-${Date.now()}@ejemplo.com`;

  const register = http.post(
    `${API}/api/auth/register`,
    JSON.stringify({
      email,
      password: PASSWORD,
      establishment_name: `Bar ${exec.vu.idInTest}`,
      data_authorization: true,
      policy_version: data.policyVersion,
    }),
    { headers: HEADERS, tags: { name: "register" } },
  );
  check(register, { "registro 202": (r) => r.status === 202 });

  const verify = http.post(`${API}/api/auth/verify-email`, JSON.stringify({ token: verificationToken(email) }), {
    headers: HEADERS,
    tags: { name: "verify" },
  });
  check(verify, { "verificación 200": (r) => r.status === 200 });

  const login = http.post(`${API}/api/auth/login`, JSON.stringify({ email, password: PASSWORD }), {
    headers: HEADERS,
    tags: { name: "login" },
  });
  check(login, { "inicio de sesión 200": (r) => r.status === 200 });

  const qr = http.get(`${API}/api/owner/establishment/qr.png`, {
    headers: HEADERS,
    cookies: { mp_session: session(login) },
    tags: { name: "qr" },
  });
  check(qr, {
    "QR 200": (r) => r.status === 200,
    "QR es PNG": (r) => r.headers["Content-Type"] === "image/png",
  });
}
