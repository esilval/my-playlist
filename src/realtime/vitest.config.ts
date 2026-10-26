import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
    // Cobertura (constitución, «Pruebas»): `npm run test:coverage`, en el CI. El suelo
    // es el valor del primer registro y solo puede subir.
    coverage: {
      provider: "v8",
      include: ["src/**"],
      thresholds: { lines: 85 },
    },
  },
});
