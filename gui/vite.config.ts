/**
 * Vite configuration for the academic_pipeline GUI.
 *
 * Dev server proxy: requests to /api/** and /openapi.json are forwarded
 * to the backend at http://127.0.0.1:8000 so browser-side URLs stay
 * path-relative in both development and production.
 *
 * Path aliases: `@/...` resolves to `src/...`, matching the `paths`
 * entry in tsconfig.json.
 *
 * The build output lives in gui/dist/, which is what the Render
 * static site (see render.yaml) serves.
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const BACKEND_URL =
  process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: BACKEND_URL,
        changeOrigin: true,
        ws: false,
        timeout: 0,
        proxyTimeout: 0,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            const contentType = proxyRes.headers["content-type"] ?? "";
            if (contentType.startsWith("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
              delete proxyRes.headers["content-length"];
            }
          });
        },
      },
      "/openapi.json": {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
