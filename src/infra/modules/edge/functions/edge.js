// La función de CloudFront de los tres comportamientos, en viewer-request (feature 004,
// plan D1, D10). Primero, el mantenimiento: con la clave `maintenance` en `on` del almacén
// de claves, responde 503 a cualquier ruta. Si no, reescribe a /index.html las rutas de la
// SPA, que no tienen extensión, y deja pasar /api/*, /socket.io/* y los archivos.
//
// Es JavaScript de CloudFront Functions (cloudfront-js-2.0), no de Node. Terraform pone el
// identificador del almacén en lugar de __KVS_ID__, y edge.test.js la ejecuta con un `cf`
// simulado.
import cf from "cloudfront";

const kvs = cf.kvs("__KVS_ID__");

const MAINTENANCE_PAGE =
  '<!doctype html><html lang="es"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width,initial-scale=1">' +
  "<title>MyPlaylist en mantenimiento</title></head>" +
  '<body style="font-family:system-ui,sans-serif;text-align:center;padding:3rem 1rem">' +
  "<h1>Volvemos enseguida</h1>" +
  "<p>MyPlaylist está en mantenimiento. Tus datos están a salvo.</p>" +
  "</body></html>";

function isBackend(uri) {
  return uri.startsWith("/api/") || uri.startsWith("/socket.io/");
}

function unavailable(contentType, body) {
  return {
    statusCode: 503,
    statusDescription: "Service Unavailable",
    headers: {
      "content-type": { value: contentType },
      "cache-control": { value: "no-store" },
      "retry-after": { value: "600" },
    },
    body: { encoding: "text", data: body },
  };
}

async function handler(event) {
  const request = event.request;
  const uri = request.uri;

  // Sin la clave, o si el almacén no responde, se atiende: el mantenimiento se activa a
  // propósito, nunca por un fallo (D10).
  let maintenance = "off";
  try {
    maintenance = await kvs.get("maintenance");
  } catch (error) {
    maintenance = "off";
  }

  if (maintenance === "on") {
    if (uri.startsWith("/api/")) {
      return unavailable("application/json", '{"error": "maintenance"}');
    }
    if (uri.startsWith("/socket.io/")) {
      return unavailable("text/plain; charset=utf-8", "maintenance");
    }
    return unavailable("text/html; charset=utf-8", MAINTENANCE_PAGE);
  }

  if (isBackend(uri)) {
    return request;
  }
  // /l/ABC, /panel, / … son rutas de la SPA; /assets/app-1a2b.js, /favicon.ico, no.
  const last = uri.split("/").pop();
  if (last.indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}
