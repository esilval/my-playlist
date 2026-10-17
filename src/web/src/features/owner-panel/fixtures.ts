import type { OwnerMe } from "./types";

export function ownerMe(overrides: { verified?: boolean; name?: string } = {}): OwnerMe {
  return {
    account: { email: "dueno@ejemplo.com", email_verified: overrides.verified ?? true },
    establishment: {
      name: overrides.name ?? "Bar La Esquina",
      address: null,
      phone: null,
      public_url: "http://localhost:5173/l/ABCDEFGHJK",
    },
  };
}

// Cabecera PNG mínima: basta para que la pantalla la trate como imagen.
export const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
