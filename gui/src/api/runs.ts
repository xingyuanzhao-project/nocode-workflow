/**
 * API client for the run-results preview and artifact download
 * endpoints.
 *
 * Both endpoints live under ``/api/flow/runs/{run_id}/...``; the
 * status endpoint is exposed from :mod:`@/api/flows` because it
 * shares a closer lifecycle with the run submission endpoints.
 */

import { buildApiUrl, requestBlob, requestJson } from "./client";
import {
  resultsPreviewResponseSchema,
  type ArtifactName,
  type ResultsPreviewResponse,
} from "@/schemas/results";

/**
 * Fetch the first ``limit`` rows of one artifact as JSON.
 */
export function previewRunArtifact(
  runId: string,
  artifact: ArtifactName,
  limit: number,
): Promise<ResultsPreviewResponse> {
  const params = new URLSearchParams({
    artifact,
    limit: String(limit),
  });
  return requestJson({
    method: "GET",
    path: `/api/flow/runs/${encodeURIComponent(runId)}/preview?${params.toString()}`,
    responseSchema: resultsPreviewResponseSchema,
  });
}

/**
 * Build the URL the GUI uses as the ``href`` of a download link.
 *
 * Clicking an anchor pointing at this URL lets the browser stream
 * the CSV straight to disk with the ``Content-Disposition`` filename
 * chosen by the backend.
 */
export function artifactDownloadUrl(
  runId: string,
  artifact: ArtifactName,
): string {
  return buildApiUrl(
    `/api/flow/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
      artifact,
    )}`,
  );
}

/**
 * Download an artifact as a :class:`Blob`.
 *
 * Used when the GUI needs to inspect the bytes (for example to
 * compute a local diff); the download button uses
 * :func:`artifactDownloadUrl` instead so the browser streams the
 * file straight to disk.
 */
export function downloadArtifactBlob(
  runId: string,
  artifact: ArtifactName,
): Promise<Blob> {
  return requestBlob(
    `/api/flow/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
      artifact,
    )}`,
  );
}
