// Vite builds the single-page app that FastAPI serves from the same origin.
// In development the dev server forwards /api to the local backend, so the
// page talks to the real API exactly as it will in production.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
    // Tests read their fixtures from the captured PokéAPI data in ../samples.
    fs: { allow: [".", "../samples"] },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
