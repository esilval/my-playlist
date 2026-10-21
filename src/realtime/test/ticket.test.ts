import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { LOCAL_REALTIME_TICKET_SECRET, loadConfig } from "../src/server.js";
import { InvalidTicket, verifyTicket, type InvalidReason } from "../src/ticket.js";

interface Vectors {
  secret: string;
  issued_at: number;
  ttl_seconds: number;
  valid: { name: string; ticket: string; now: number; establishment_id: string; role: string; ticket_id: string }[];
  invalid: { name: string; ticket: string; now: number; reason: InvalidReason }[];
}

// Los mismos vectores que genera y comprueba el monolito (tests/unit/test_realtime_ticket.py).
const vectors = JSON.parse(
  readFileSync(new URL("./fixtures/ticket-vectors.json", import.meta.url), "utf8"),
) as Vectors;

function reasonOf(secret: string, ticket: string, now: number): InvalidReason | null {
  try {
    verifyTicket(secret, ticket, now);
    return null;
  } catch (error) {
    if (error instanceof InvalidTicket) return error.reason;
    throw error;
  }
}

describe("ticket de tiempo real", () => {
  it("F002_R013 valida los vectores de ticket del monolito", () => {
    expect(vectors.valid.length).toBeGreaterThan(0);
    for (const vector of vectors.valid) {
      const claims = verifyTicket(vectors.secret, vector.ticket, vector.now);
      expect(claims).toEqual({
        establishmentId: vector.establishment_id,
        role: vector.role,
        expiresAt: vectors.issued_at + vectors.ttl_seconds,
        ticketId: vector.ticket_id,
      });
    }
  });

  it("F002_R013 rechaza ticket caducado, mal firmado o alterado", () => {
    expect(vectors.invalid.length).toBeGreaterThan(0);
    for (const vector of vectors.invalid) {
      expect(reasonOf(vectors.secret, vector.ticket, vector.now), vector.name).toBe(vector.reason);
    }
    // Un ticket válido, con otro secreto, tampoco vale.
    const [valid] = vectors.valid;
    expect(valid).toBeDefined();
    if (valid) expect(reasonOf("otro-secreto", valid.ticket, valid.now)).toBe("signature");
  });

  it("F002_R013 rechaza un ticket bien firmado con el contenido mal formado", () => {
    const secret = "secreto-de-pruebas-del-contenido-0123456789";
    const sign = (segment: string) => `${segment}.${createHmac("sha256", secret).update(segment).digest("base64url")}`;
    const encode = (payload: unknown) => Buffer.from(JSON.stringify(payload)).toString("base64url");
    const good = { est: "6f1c2b4a-8d3e-4f5a-9b7c-1d2e3f4a5b6c", role: "owner", exp: 2_000_000_000, jti: "j" };

    const malformed: [string, string][] = [
      ["JSON roto", sign(Buffer.from("{no es json").toString("base64url"))],
      ["no es un objeto", sign(encode([1, 2, 3]))],
      ["est no es un UUID", sign(encode({ ...good, est: "otro-establecimiento" }))],
      ["rol desconocido", sign(encode({ ...good, role: "admin" }))],
      ["exp no es entero", sign(encode({ ...good, exp: 1.5 }))],
      ["exp como texto", sign(encode({ ...good, exp: "2000000000" }))],
      ["sin jti", sign(encode({ est: good.est, role: good.role, exp: good.exp }))],
    ];
    for (const [name, ticket] of malformed) {
      expect(reasonOf(secret, ticket, 1_800_000_000), name).toBe("malformed");
    }
    expect(reasonOf(secret, sign(encode(good)), 1_800_000_000)).toBeNull();
  });

  it("F002_R013 en producción no arranca sin REALTIME_TICKET_SECRET", () => {
    for (const secret of [undefined, LOCAL_REALTIME_TICKET_SECRET, "corto"]) {
      expect(() => loadConfig({ ENV: "production", REALTIME_TICKET_SECRET: secret }), String(secret)).toThrow(
        /REALTIME_TICKET_SECRET/,
      );
    }
    const strong = "x".repeat(32);
    expect(loadConfig({ ENV: "production", REALTIME_TICKET_SECRET: strong }).ticketSecret).toBe(strong);
    // En local, sin configurar nada, usa el mismo secreto de desarrollo que el monolito.
    expect(loadConfig({}).ticketSecret).toBe(LOCAL_REALTIME_TICKET_SECRET);
  });
});
