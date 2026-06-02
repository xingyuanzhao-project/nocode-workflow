/**
 * Vitest configuration for the nocode-workflow GUI.
 *
 * Three independently-runnable test tiers, each under its own
 * directory:
 *
 * - ``tests/data/**`` — pure-data tests (codec, Zod, truth tables).
 *   No DOM.
 * - ``tests/rtl/**`` — React Testing Library component tests that
 *   assert on the rendered DOM. No store reads; enforced by
 *   ``scripts/test_all.*``.
 * - ``tests/contract/**`` — contract tests fetching ``/openapi.json``
 *   from the live backend and validating every Zod mirror against it.
 *
 * The default ``npm run test`` runs the fast tiers (data + rtl). The
 * contract tier is opt-in via ``npm run test:contract`` because it
 * requires the Docker stack.
 */

import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const TEST_SCOPE = process.env.VITEST_SCOPE ?? "fast";

const SCOPE_INCLUDE_PATTERNS: Record<string, string[]> = {
  data: ["tests/data/**/*.test.{ts,tsx}"],
  rtl: ["tests/rtl/**/*.test.{ts,tsx}"],
  contract: ["tests/contract/**/*.test.{ts,tsx}"],
  fast: ["tests/data/**/*.test.{ts,tsx}", "tests/rtl/**/*.test.{ts,tsx}"],
  all: ["tests/**/*.test.{ts,tsx}"],
};

const includeGlobs =
  SCOPE_INCLUDE_PATTERNS[TEST_SCOPE] ?? SCOPE_INCLUDE_PATTERNS.fast;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: includeGlobs,
  },
});
