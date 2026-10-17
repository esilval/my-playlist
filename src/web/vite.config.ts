import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// En local, la SPA y la API comparten origen: Vite reenvía /api al backend (plan D10).
// Sin changeOrigin, la API recibe el Origin de la SPA y la cookie es de primera parte.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
