import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The console talks to the VoClyp gateway's public /v1 API. In dev, Vite
// proxies /v1 to the gateway so the browser stays same-origin and no CORS
// config is needed on the Python side. Change this if the gateway runs
// elsewhere.
const GATEWAY = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: GATEWAY, changeOrigin: true },
      "/auth": { target: GATEWAY, changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
