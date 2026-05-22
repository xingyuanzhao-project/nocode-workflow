/**
 * Scrolling log viewer consumed by the run page.
 *
 * Renders the lines delivered by :func:`use_run_log_stream` as a
 * virtualised-ish list (``overflow-y: auto`` with monospaced font).
 * Each JSON payload is parsed best-effort so known structured fields
 * (``timestamp``, ``level``, ``message``) render with extra chrome.
 */

import { useEffect, useMemo, useRef } from "react";

import { cn } from "@/lib/utils";
import type { RunLogLine } from "@/hooks/use_run_log_stream";

export interface LogStreamViewerProps {
  lines: RunLogLine[];
  terminal_status: string | null;
  connection_error: string | null;
}

interface ParsedLogRecord {
  timestamp: string | null;
  level: string | null;
  message: string;
  raw: string;
}

function parseLogRecord(payload: string): ParsedLogRecord {
  try {
    const parsed = JSON.parse(payload);
    if (parsed && typeof parsed === "object") {
      const record = parsed as Record<string, unknown>;
      return {
        timestamp:
          typeof record.timestamp === "string" ? record.timestamp : null,
        level: typeof record.level === "string" ? record.level : null,
        message:
          typeof record.message === "string" ? record.message : payload,
        raw: payload,
      };
    }
  } catch {
    // fall through to raw
  }
  return {
    timestamp: null,
    level: null,
    message: payload,
    raw: payload,
  };
}

function classForLevel(level: string | null): string {
  switch (level) {
    case "ERROR":
    case "CRITICAL":
      return "text-destructive";
    case "WARNING":
      return "text-yellow-700";
    case "INFO":
      return "text-foreground";
    case "DEBUG":
      return "text-muted-foreground";
    default:
      return "text-foreground";
  }
}

export function LogStreamViewer({
  lines,
  terminal_status,
  connection_error,
}: LogStreamViewerProps): JSX.Element {
  const scroll_container_ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = scroll_container_ref.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [lines, terminal_status]);

  const parsed_lines = useMemo(
    () =>
      lines.map((line) => ({
        sequence_number: line.sequence_number,
        ...parseLogRecord(line.payload),
      })),
    [lines],
  );

  return (
    <div className="flex h-full flex-col rounded-md border bg-card">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs">
        <span className="font-medium">Live log</span>
        <span className="text-muted-foreground">
          {terminal_status
            ? `Finished (${terminal_status})`
            : connection_error
              ? `Disconnected: ${connection_error}`
              : `Streaming — ${lines.length} lines`}
        </span>
      </div>
      <div
        ref={scroll_container_ref}
        className="flex-1 overflow-y-auto p-2 font-mono text-xs"
      >
        {parsed_lines.length === 0 ? (
          <div className="italic text-muted-foreground">
            Waiting for first log line...
          </div>
        ) : (
          parsed_lines.map((line) => (
            <div
              key={line.sequence_number}
              className={cn("whitespace-pre-wrap", classForLevel(line.level))}
            >
              {line.timestamp ? (
                <span className="mr-2 text-muted-foreground">
                  {line.timestamp}
                </span>
              ) : null}
              {line.level ? (
                <span className="mr-2 font-semibold">{line.level}</span>
              ) : null}
              <span>{line.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
