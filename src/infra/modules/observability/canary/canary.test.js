// Pruebas del canario de disponibilidad (feature 004, T016, ADR-0020), con `node --test`.
// `executeHttpStep` se simula: cada prueba decide qué responde cada ruta.
"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { test } = require("node:test");

const { run, steps, validate, STEP_CONFIG } = require("./canary.js");

const ENVIRONMENT = { CANARY_HOSTNAME: "myplaylist.200oklabs.com", ESTABLISHMENT_CODE: "PRUEBA01" };

function response(statusCode) {
  const emitter = new EventEmitter();
  emitter.statusCode = statusCode;
  setImmediate(() => {
    emitter.emit("data", "{}");
    emitter.emit("end");
  });
  return emitter;
}

// Como Synthetics: ejecuta el paso, y si la validación falla lo anota y sigue
// (continueOnHttpStepFailure). Al final, el canario falla si falló algún paso.
function synthetics(statusByPath) {
  const calls = [];
  const failures = [];
  const executeHttpStep = async (name, options, callback, config) => {
    calls.push({ name, options, config });
    try {
      await callback(response(statusByPath[options.path] ?? 200));
    } catch (error) {
      failures.push(name);
      if (!config.continueOnHttpStepFailure) throw error;
    }
  };
  return { calls, failures, executeHttpStep };
}

test("F004_R013 el canario recorre las tres rutas por HTTPS contra el dominio público", async () => {
  const fake = synthetics({});

  await run(fake.executeHttpStep, ENVIRONMENT);

  assert.deepEqual(
    fake.calls.map((call) => call.options.path),
    ["/api/health", "/socket.io/health", "/api/public/establishments/PRUEBA01"],
  );
  for (const call of fake.calls) {
    assert.equal(call.options.hostname, "myplaylist.200oklabs.com");
    assert.equal(call.options.protocol, "https:");
    assert.equal(call.options.port, 443);
    assert.equal(call.options.method, "GET");
  }
  assert.deepEqual(fake.failures, []);
});

test("F004_R013 un paso que no responde 2xx falla, y se comprueban los demás", async () => {
  const fake = synthetics({ "/socket.io/health": 502 });

  await run(fake.executeHttpStep, ENVIRONMENT);

  assert.deepEqual(fake.failures, ["tiempo-real"]);
  assert.equal(fake.calls.length, 3);
});

test("F004_R013 validate rechaza 4xx y 5xx y acepta 2xx", async () => {
  await validate(response(200));
  await validate(response(204));
  await assert.rejects(validate(response(404)), /HTTP 404/);
  await assert.rejects(validate(response(503)), /HTTP 503/);
});

test("F004_R016 el canario no guarda cabeceras ni cuerpos", () => {
  assert.equal(STEP_CONFIG.includeRequestHeaders, false);
  assert.equal(STEP_CONFIG.includeResponseHeaders, false);
  assert.equal(STEP_CONFIG.includeRequestBody, false);
  assert.equal(STEP_CONFIG.includeResponseBody, false);
});

test("F004_R013 el código del establecimiento va escapado en la ruta", () => {
  assert.equal(steps("A B/1")[2].path, "/api/public/establishments/A%20B%2F1");
});

test("F004_R013 sin anfitrión o código, el canario falla en lugar de no comprobar nada", async () => {
  const fake = synthetics({});
  await assert.rejects(run(fake.executeHttpStep, { CANARY_HOSTNAME: "myplaylist.200oklabs.com" }), /faltan/);
  assert.equal(fake.calls.length, 0);
});
