import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Sin los globales de Vitest, Testing Library no desmonta solo entre pruebas.
afterEach(cleanup);

// Ninguna prueba abre una conexión de tiempo real de verdad: las que la necesitan pasan
// un socket falso, y las demás (como las del panel) reciben este, que nunca conecta.
vi.mock("socket.io-client", () => ({
  io: () => ({ active: false, on() {}, connect() {}, disconnect() {} }),
}));
