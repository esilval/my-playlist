// El canario de disponibilidad (feature 004, ADR-0020, plan D12): cada minuto, desde
// us-east-2, recorre tres pasos contra el dominio público, a través de CloudFront, como un
// usuario. Si uno falla, el canario falla y la alarma de SG3 lo cuenta (R013).
//
// Corre en el entorno `syn-nodejs-puppeteer` de CloudWatch Synthetics, que da los módulos
// `Synthetics`. La lógica no depende de ellos, para que canary.test.js la pruebe con Node.
"use strict";

// Sin cabeceras ni cuerpos en los artefactos: no hace falta guardarlos, y así no queda
// nada de lo que responde la API (R016).
const STEP_CONFIG = {
  includeRequestHeaders: false,
  includeResponseHeaders: false,
  includeRequestBody: false,
  includeResponseBody: false,
  // Se comprueban los tres pasos aunque falle uno: así el registro dice cuáles fallan.
  continueOnHttpStepFailure: true,
};

// Los tres pasos: la API, el tiempo real y lo que pide la página pública de un
// establecimiento de prueba, que tiene que existir en el entorno.
function steps(establishmentCode) {
  return [
    { name: "api", path: "/api/health" },
    { name: "tiempo-real", path: "/socket.io/health" },
    { name: "establecimiento", path: `/api/public/establishments/${encodeURIComponent(establishmentCode)}` },
  ];
}

function request(hostname, path) {
  return {
    hostname,
    method: "GET",
    path,
    port: 443,
    protocol: "https:",
    headers: { "User-Agent": "MyPlaylist-canario" },
  };
}

// Un paso es bueno con un 2xx. El cuerpo se lee y se descarta.
function validate(response) {
  return new Promise((resolve, reject) => {
    if (response.statusCode < 200 || response.statusCode > 299) {
      reject(new Error(`HTTP ${response.statusCode}`));
      return;
    }
    response.on("data", () => {});
    response.on("end", () => resolve());
    response.on("error", reject);
  });
}

async function run(executeHttpStep, environment) {
  const hostname = environment.CANARY_HOSTNAME;
  const code = environment.ESTABLISHMENT_CODE;
  if (!hostname || !code) {
    throw new Error("faltan CANARY_HOSTNAME o ESTABLISHMENT_CODE");
  }
  for (const step of steps(code)) {
    await executeHttpStep(step.name, request(hostname, step.path), validate, STEP_CONFIG);
  }
}

async function handler() {
  // Solo existen dentro de CloudWatch Synthetics.
  const synthetics = require("Synthetics");
  synthetics.getConfiguration().setConfig({
    screenshotOnStepStart: false,
    screenshotOnStepSuccess: false,
    screenshotOnStepFailure: false,
  });
  return run((...args) => synthetics.executeHttpStep(...args), process.env);
}

module.exports = { handler, run, steps, validate, STEP_CONFIG };
