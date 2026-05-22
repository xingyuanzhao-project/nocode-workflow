/**
 * Playwright configuration for the GUI end-to-end tests.
 *
 * Tests live under tests/e2e/. The ``globalSetup`` hook starts the
 * docker compose stack (redis, celery worker, FastAPI web) before
 * any spec runs, and the built-in ``webServer`` block starts the
 * Vite dev server. Both the backend and the Vite proxy must be
 * reachable before any spec is allowed to run, which is what
 * guarantees ``/api/flow/templates`` and friends return real data
 * instead of a hanging dialog.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  globalSetup: "./tests/e2e/global_setup.ts",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
