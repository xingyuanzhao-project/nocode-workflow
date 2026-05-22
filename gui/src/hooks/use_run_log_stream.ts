/**
 * Hook that subscribes to the ``/api/flow/runs/:run_id/logs/stream``
 * SSE endpoint and feeds a bounded in-memory buffer.
 *
 * Owns an :class:`EventSource` whose lifecycle is tied to the hook's
 * useEffect; closing happens on unmount, on a new ``run_id``, or when
 * the server emits a terminal ``status`` event.
 */

import { useEffect, useState } from "react";

import { openRunLogStream } from "@/api/logs";

export interface RunLogLine {
  /** Monotonically increasing sequence number assigned client-side. */
  sequence_number: number;
  /** Raw JSON payload delivered by the worker's logging pipeline. */
  payload: string;
}

interface UseRunLogStreamResult {
  /** Last ``max_buffered_lines`` lines, newest last. */
  lines: RunLogLine[];
  /** Terminal status once the stream closes, ``null`` while streaming. */
  terminal_status: string | null;
  /** Stream error observed on the EventSource. */
  connection_error: string | null;
}

const DEFAULT_MAX_BUFFERED_LINES = 2000;

/**
 * Open a log stream for ``run_id`` and yield a live buffer of lines.
 *
 * Passing ``null`` as the ``run_id`` disables the subscription (for
 * example while the route is still resolving its params).
 */
export function useRunLogStream(
  run_id: string | null,
  max_buffered_lines: number = DEFAULT_MAX_BUFFERED_LINES,
): UseRunLogStreamResult {
  const [lines, set_lines] = useState<RunLogLine[]>([]);
  const [terminal_status, set_terminal_status] = useState<string | null>(null);
  const [connection_error, set_connection_error] = useState<string | null>(
    null,
  );

  useEffect(() => {
    if (run_id === null) {
      return;
    }
    set_lines([]);
    set_terminal_status(null);
    set_connection_error(null);
    let sequence_counter = 0;
    const event_source = openRunLogStream(run_id);
    const handle_log_event = (event: MessageEvent) => {
      sequence_counter += 1;
      const new_line: RunLogLine = {
        sequence_number: sequence_counter,
        payload: event.data,
      };
      set_lines((previous_lines) => {
        const next_lines = [...previous_lines, new_line];
        if (next_lines.length > max_buffered_lines) {
          return next_lines.slice(-max_buffered_lines);
        }
        return next_lines;
      });
    };
    const handle_status_event = (event: MessageEvent) => {
      set_terminal_status(event.data);
      event_source.close();
    };
    const handle_error = () => {
      set_connection_error("Log stream connection lost.");
      event_source.close();
    };
    event_source.addEventListener("log", handle_log_event as EventListener);
    event_source.addEventListener("status", handle_status_event as EventListener);
    event_source.addEventListener("error", handle_error);
    return () => {
      event_source.removeEventListener("log", handle_log_event as EventListener);
      event_source.removeEventListener("status", handle_status_event as EventListener);
      event_source.removeEventListener("error", handle_error);
      event_source.close();
    };
  }, [run_id, max_buffered_lines]);

  return { lines, terminal_status, connection_error };
}
