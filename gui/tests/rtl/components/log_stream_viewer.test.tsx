/**
 * DOM assertions for :class:`LogStreamViewer`.
 */

import { describe, expect, it } from "vitest";

import { LogStreamViewer } from "@/components/LogStreamViewer";
import type { RunLogLine } from "@/hooks/use_run_log_stream";

import { renderForUser } from "../_helpers";

describe("LogStreamViewer", () => {
  it("shows the waiting caption when no lines arrived", () => {
    const { getByText } = renderForUser(
      <LogStreamViewer lines={[]} terminal_status={null} connection_error={null} />,
    );
    expect(getByText(/Waiting for first log line/i)).toBeInTheDocument();
  });

  it("renders a structured JSON line with timestamp, level, and message", () => {
    const lines: RunLogLine[] = [
      {
        sequence_number: 1,
        payload: JSON.stringify({
          timestamp: "2026-04-21T22:00:00+00:00",
          level: "INFO",
          message: "hello world",
        }),
      },
    ];
    const { getByText } = renderForUser(
      <LogStreamViewer
        lines={lines}
        terminal_status={null}
        connection_error={null}
      />,
    );
    expect(getByText("hello world")).toBeInTheDocument();
    expect(getByText("INFO")).toBeInTheDocument();
  });

  it("shows the 'Finished (succeeded)' caption after a terminal status", () => {
    const { getByText } = renderForUser(
      <LogStreamViewer
        lines={[]}
        terminal_status="succeeded"
        connection_error={null}
      />,
    );
    expect(getByText(/Finished \(succeeded\)/i)).toBeInTheDocument();
  });

  it("renders a raw line unchanged when it is not JSON", () => {
    const lines: RunLogLine[] = [
      { sequence_number: 1, payload: "plain text line" },
    ];
    const { getByText } = renderForUser(
      <LogStreamViewer lines={lines} terminal_status={null} connection_error={null} />,
    );
    expect(getByText("plain text line")).toBeInTheDocument();
  });
});
