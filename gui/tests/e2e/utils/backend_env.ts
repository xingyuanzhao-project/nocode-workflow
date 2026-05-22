/**
 * Shared Playwright helpers that talk to the backend over HTTP.
 */

import type { APIRequestContext } from "@playwright/test";

export const BACKEND_BASE_URL: string =
  process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

/**
 * Poll the backend's ``GET /api/flow/status/{run_id}`` until a
 * terminal status arrives or the deadline fires.
 *
 * Used by run-page specs as a network-level sanity check that is
 * independent of the GUI's polling behaviour.
 */
export async function pollRunTerminal(
  request: APIRequestContext,
  run_id: string,
  timeout_ms = 900_000,
): Promise<string> {
  const terminals = new Set(["succeeded", "failed", "cancelled"]);
  const deadline = Date.now() + timeout_ms;
  while (Date.now() < deadline) {
    const response = await request.get(
      `${BACKEND_BASE_URL}/api/flow/status/${run_id}`,
    );
    if (response.ok()) {
      const body = await response.json();
      if (terminals.has(body.status)) {
        return body.status;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(`Run ${run_id} did not reach a terminal status in time.`);
}
