// Pruebas de la función de CloudFront (feature 004, T014, plan D1, D10), con `node --test`.
// La función es JavaScript de CloudFront Functions: se carga como texto, sin su `import`, y
// se ejecuta con un `cf` simulado cuyo almacén de claves controla cada prueba.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("./edge.js", import.meta.url), "utf8").replace(
  /^import cf from "cloudfront";$/m,
  "",
);

function load(store) {
  const context = {
    cf: {
      kvs: () => ({
        get: async (key) => {
          if (store instanceof Error) throw store;
          if (!(key in store)) throw new Error(`no existe la clave ${key}`);
          return store[key];
        },
      }),
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}\nglobalThis.handler = handler;`, context);
  return context.handler;
}

function event(uri) {
  return { request: { method: "GET", uri, querystring: {}, headers: {}, cookies: {} } };
}

test("F004_R014 con maintenance=on devuelve 503 y la página de mantenimiento", async () => {
  const handler = load({ maintenance: "on" });

  for (const uri of ["/", "/l/ABC123", "/panel", "/assets/app-1a2b.js"]) {
    const response = await handler(event(uri));
    assert.equal(response.statusCode, 503, uri);
    assert.equal(response.headers["content-type"].value, "text/html; charset=utf-8");
    assert.equal(response.headers["cache-control"].value, "no-store");
    assert.match(response.body.data, /mantenimiento/);
  }
});

test("F004_R014 en /api/* devuelve 503 con error maintenance", async () => {
  const handler = load({ maintenance: "on" });

  const api = await handler(event("/api/public/establishments/ABC123/search"));
  assert.equal(api.statusCode, 503);
  assert.equal(api.headers["content-type"].value, "application/json");
  assert.deepEqual(JSON.parse(api.body.data), { error: "maintenance" });

  const realtime = await handler(event("/socket.io/"));
  assert.equal(realtime.statusCode, 503);
  assert.doesNotMatch(realtime.body.data, /<html/);
});

test("F004_R014 con maintenance=off deja pasar la petición", async () => {
  for (const store of [{ maintenance: "off" }, {}, new Error("el almacén no responde")]) {
    const handler = load(store);

    const api = await handler(event("/api/health"));
    assert.equal(api.uri, "/api/health");
    assert.equal(api.statusCode, undefined);

    const spa = await handler(event("/l/ABC123"));
    assert.equal(spa.uri, "/index.html");
  }
});

test("F004_R003 reescribe a /index.html las rutas de la SPA sin extensión", async () => {
  const handler = load({ maintenance: "off" });

  for (const uri of ["/", "/l/ABC123", "/panel", "/panel/", "/verificar-correo"]) {
    const request = await handler(event(uri));
    assert.equal(request.uri, "/index.html", uri);
  }
});

test("F004_R003 no reescribe /api/*, /socket.io/* ni los archivos con extensión", async () => {
  const handler = load({ maintenance: "off" });

  for (const uri of [
    "/api/public/establishments/NOEXISTE",
    "/api/owner/session",
    "/socket.io/",
    "/socket.io/health",
    "/assets/app-1a2b.js",
    "/favicon.ico",
    "/index.html",
  ]) {
    const request = await handler(event(uri));
    assert.equal(request.uri, uri, uri);
    assert.equal(request.statusCode, undefined, uri);
  }
});
