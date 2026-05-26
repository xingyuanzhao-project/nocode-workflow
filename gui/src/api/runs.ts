/**
 * API client for run-results preview, output download, and run listing.
 */

import { buildApiUrl, requestJson } from "./client";
import {
  resultsPreviewResponseSchema,
  type ResultsPreviewResponse,
} from "@/schemas/results";
import { runListSchema, type RunList } from "@/schemas/run";

/** Fetch the list of all runs, most recent first. */
export function listRuns(): Promise<RunList> {
  return requestJson({
    method: "GET",
    path: "/api/flow/runs",
    responseSchema: runListSchema,
  });
}

/**
 * Fetch the first ``limit`` rows of a run's output as JSON.
 */
export function previewRunOutput(
  runId: string,
  limit: number,
): Promise<ResultsPreviewResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return requestJson({
    method: "GET",
    path: `/api/flow/runs/${encodeURIComponent(runId)}/preview?${params.toString()}`,
    responseSchema: resultsPreviewResponseSchema,
  });
}

/**
 * Build the URL for downloading a run's output file.
 */
export function outputDownloadUrl(runId: string, filename?: string): string {
  const base = `/api/flow/runs/${encodeURIComponent(runId)}/output`;
  if (filename) {
    const params = new URLSearchParams({ filename });
    return buildApiUrl(`${base}?${params.toString()}`);
  }
  return buildApiUrl(base);
}
