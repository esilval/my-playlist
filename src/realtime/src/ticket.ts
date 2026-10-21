// Validación del ticket de tiempo real (ADR-0014). Lo emite el monolito
// (src/backend/app/shared/realtime_ticket.py) y este servicio solo comprueba la firma
// y la caducidad con el secreto que comparten: no lee la base de datos ni llama a la
// API (S5).
//
// Formato: base64url(payload) "." base64url(HMAC-SHA256(secreto, base64url(payload))).
// La firma va sobre el segmento tal como viaja, así que no hace falta reproducir el
// JSON del monolito. Los vectores de test/fixtures/ticket-vectors.json lo comprueban.
//
// Con el contenido es algo más estricto que el monolito: exige `est` como UUID con
// guiones y `exp` entero. Es justo lo que emite el monolito, así que no cambia nada
// para un ticket legítimo; solo rechaza antes uno fabricado.
import { createHmac, timingSafeEqual } from "node:crypto";

export type TicketRole = "owner" | "player";
export type InvalidReason = "signature" | "malformed" | "expired";

export class InvalidTicket extends Error {
  constructor(readonly reason: InvalidReason) {
    super(`ticket no válido: ${reason}`);
    this.name = "InvalidTicket";
  }
}

export interface TicketClaims {
  establishmentId: string;
  role: TicketRole;
  expiresAt: number;
  ticketId: string;
}

const ROLES: ReadonlySet<string> = new Set(["owner", "player"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function signature(secret: string, segment: string): string {
  return createHmac("sha256", secret).update(segment).digest("base64url");
}

function sameSignature(received: string, expected: string): boolean {
  const a = Buffer.from(received, "utf8");
  const b = Buffer.from(expected, "utf8");
  // timingSafeEqual exige la misma longitud; una firma de otra longitud ya no vale.
  return a.length === b.length && timingSafeEqual(a, b);
}

function parsePayload(segment: string): TicketClaims {
  let payload: unknown;
  try {
    payload = JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));
  } catch {
    throw new InvalidTicket("malformed");
  }
  if (typeof payload !== "object" || payload === null) throw new InvalidTicket("malformed");
  const { est, role, exp, jti } = payload as Record<string, unknown>;
  if (
    typeof est !== "string" ||
    !UUID.test(est) ||
    typeof role !== "string" ||
    !ROLES.has(role) ||
    typeof exp !== "number" ||
    !Number.isInteger(exp) ||
    typeof jti !== "string"
  ) {
    throw new InvalidTicket("malformed");
  }
  return { establishmentId: est.toLowerCase(), role: role as TicketRole, expiresAt: exp, ticketId: jti };
}

/** La misma comprobación que el monolito: firma, formato y caducidad, en ese orden. */
export function verifyTicket(secret: string, ticket: string, nowSeconds: number): TicketClaims {
  const dot = ticket.indexOf(".");
  if (dot < 0) throw new InvalidTicket("signature");
  const segment = ticket.slice(0, dot);
  if (!sameSignature(ticket.slice(dot + 1), signature(secret, segment))) {
    throw new InvalidTicket("signature");
  }
  const claims = parsePayload(segment);
  if (nowSeconds >= claims.expiresAt) throw new InvalidTicket("expired");
  return claims;
}
