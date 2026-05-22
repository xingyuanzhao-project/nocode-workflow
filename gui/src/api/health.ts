/**
 * API client for the ``GET /api/health`` endpoint.
 */

import { requestJson } from "./client";
import { healthResponseSchema, type HealthResponse } from "@/schemas/health";

/**
 * Fetch the backend's dependency health summary.
 *
 * @returns Parsed :class:`HealthResponse`.
 */
export function getHealth(): Promise<HealthResponse> {
  return requestJson({
    method: "GET",
    path: "/api/health",
    responseSchema: healthResponseSchema,
  });
}
