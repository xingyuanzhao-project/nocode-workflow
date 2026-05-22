/**
 * SSE helper for the ``GET /api/flow/runs/{run_id}/logs/stream`` endpoint.
 *
 * Wraps ``EventSource`` so the hook in :mod:`@/hooks/use_run_log_stream`
 * stays focused on React lifecycle concerns and this module owns the
 * URL construction.
 */

import { buildApiUrl } from "./client";

/**
 * Construct an :class:`EventSource` subscribed to ``run_id``'s log
 * channel.
 *
 * Callers are responsible for closing the returned handle in their
 * effect cleanup (:meth:`EventSource.close`). The browser's
 * EventSource follows a fresh cookie jar for every connection, so
 * this works behind HTTP sessions without extra wiring.
 *
 * @param runId - The run identifier whose logs to stream.
 */
export function openRunLogStream(runId: string): EventSource {
  const url = buildApiUrl(
    `/api/flow/runs/${encodeURIComponent(runId)}/logs/stream`,
  );
  return new EventSource(url);
}
