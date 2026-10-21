import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// En local, la SPA y la API comparten origen: Vite reenvía /api al backend (plan D10).
// Sin changeOrigin, la API recibe el Origin de la SPA y la cookie es de primera parte.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";
// El tiempo real va por el mismo origen: Vite reenvía /socket.io, también el WebSocket.
const realtimeTarget = process.env.REALTIME_PROXY_TARGET ?? "http://localhost:3001";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
      "/socket.io": { target: realtimeTarget, changeOrigin: false, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
