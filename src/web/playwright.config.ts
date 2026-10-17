import { defineConfig, devices } from "@playwright/test";

// Las pruebas e2e corren desde la máquina contra el entorno de docker-compose, bajo
// el único origen http://localhost:5173 (plan D10): `docker compose up -d --build` desde `src/`.
// Solo Chromium: trata localhost como contexto seguro y envía la cookie `Secure` por
// http, igual que el resto de navegadores actuales; con un solo navegador las pruebas
// son rápidas y estables. Desde otro contenedor (http://web:5173) la cookie no viajaría.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
