/**
 * Run viewer page.
 *
 * Responsibilities:
 *
 * - Poll ``/api/flow/status/{run_id}`` every two seconds until the
 *   run reaches a terminal state.
 * - Show live logs via :func:`use_run_log_stream` +
 *   :class:`LogStreamViewer`.
 * - When the run succeeds, fetch the output preview via
 *   :func:`previewRunOutput` and render it with
 *   :class:`ResultsPreviewTable`; expose output download button.
 * - Offer a Resume button for failed / cancelled runs.
 */

import { useEffect, useMemo, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getRunStatus, resumeRun } from "@/api/flows";
import { outputDownloadUrl, previewRunOutput } from "@/api/runs";
import { Button } from "@/components/ui/button";
import { LogStreamViewer } from "@/components/LogStreamViewer";
import { ResultsPreviewTable } from "@/components/ResultsPreviewTable";
import { useRunLogStream } from "@/hooks/use_run_log_stream";
import {
  TERMINAL_RUN_STATUSES,
  type RunStatus,
} from "@/schemas/run";
import { useRunStore } from "@/stores/run_store";

const STATUS_POLL_INTERVAL_MS = 2_000;
const PREVIEW_ROW_LIMIT = 50;

export default function RunPage(): JSX.Element {
  const { run_id } = useParams<{ run_id: string }>();
  const query_client = useQueryClient();
  const upsert_run = useRunStore((state) => state.upsert_run);

  const status_query = useQuery({
    queryKey: ["run-status", run_id],
    queryFn: async () => {
      if (!run_id) {
        throw new Error("Run id missing from URL");
      }
      const dto = await getRunStatus(run_id);
      upsert_run(dto);
      return dto;
    },
    enabled: Boolean(run_id),
    refetchInterval: (query) => {
      const current_status = query.state.data?.status as RunStatus | undefined;
      if (current_status && TERMINAL_RUN_STATUSES.has(current_status)) {
        return false;
      }
      return STATUS_POLL_INTERVAL_MS;
    },
  });

  const log_stream = useRunLogStream(run_id ?? null);

  const is_terminal = useMemo(() => {
    const status = status_query.data?.status;
    return Boolean(status && TERMINAL_RUN_STATUSES.has(status));
  }, [status_query.data]);

  const preview_query = useQuery({
    queryKey: ["run-preview", run_id],
    queryFn: () => previewRunOutput(run_id as string, PREVIEW_ROW_LIMIT),
    enabled: Boolean(run_id) && status_query.data?.status === "succeeded",
    staleTime: 30_000,
  });

  const resume_mutation = useMutation({
    mutationFn: () => {
      if (!run_id) {
        throw new Error("Run id missing from URL");
      }
      return resumeRun(run_id);
    },
    onSuccess: (response) => {
      query_client.setQueryData(["run-status", response.run_id], {
        run_id: response.run_id,
        status: response.status,
        started_at: null,
        finished_at: null,
        error: null,
      });
      query_client.invalidateQueries({ queryKey: ["run-status", response.run_id] });
    },
  });

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">
          Run <span className="font-mono text-sm">{run_id}</span>
        </h1>
        <StatusBadge status={status_query.data?.status ?? null} />
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to="/flows">Back to flows</Link>
          </Button>
          {is_terminal && status_query.data?.status !== "succeeded" ? (
            <Button
              size="sm"
              onClick={() => resume_mutation.mutate()}
              disabled={resume_mutation.isPending}
            >
              {resume_mutation.isPending ? "Resuming..." : "Resume"}
            </Button>
          ) : null}
        </div>
      </header>

      <TqdmProgress
        status={status_query.data?.status ?? null}
        completed_count={status_query.data?.completed_entity_count ?? 0}
        total_count={status_query.data?.total_row_count ?? 0}
        started_at={status_query.data?.started_at ?? null}
        finished_at={status_query.data?.finished_at ?? null}
      />

      {status_query.data?.error ? (
        <div className="rounded-md border border-destructive bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {status_query.data.error}
        </div>
      ) : null}

      <section className="flex min-h-0 flex-1 gap-4">
        <div className="flex w-1/2 flex-col gap-3">
          <div className="flex min-h-0 flex-1">
            <LogStreamViewer
              lines={log_stream.lines}
              terminal_status={log_stream.terminal_status}
              connection_error={log_stream.connection_error}
            />
          </div>
        </div>
        <div className="flex w-1/2 flex-col gap-3 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">Output</h2>
            <a href={run_id ? outputDownloadUrl(run_id) : "#"}>
              <Button
                variant="outline"
                size="sm"
                disabled={!is_terminal || status_query.data?.status !== "succeeded"}
              >
                Download output
              </Button>
            </a>
          </div>
          <ResultsPreviewTable
            preview={preview_query.data ?? null}
            is_loading={preview_query.isFetching}
            error={normalisePreviewError(preview_query.error)}
          />
        </div>
      </section>
    </div>
  );
}

function normalisePreviewError(raw_error: unknown): Error | null {
  if (!raw_error) {
    return null;
  }
  if (raw_error instanceof Error) {
    return raw_error;
  }
  if (typeof raw_error === "object" && raw_error !== null) {
    const maybe_message = (raw_error as { message?: unknown }).message;
    if (typeof maybe_message === "string") {
      return new Error(maybe_message);
    }
  }
  return new Error(String(raw_error));
}

interface StatusBadgeProps {
  status: RunStatus | null;
}

const STATUS_STYLES: Record<RunStatus, string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-blue-100 text-blue-700",
  succeeded: "bg-green-100 text-green-700",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  if (!status) {
    return (
      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
        unknown
      </span>
    );
  }
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

const BAR_WIDTH = 20;
const FILLED_CHAR = "\u2588"; // █
const EMPTY_CHAR = "\u2591"; // ░

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatSpeed(rows_per_sec: number): string {
  if (rows_per_sec >= 10) return `${rows_per_sec.toFixed(0)} rows/s`;
  if (rows_per_sec >= 1) return `${rows_per_sec.toFixed(1)} rows/s`;
  return `${rows_per_sec.toFixed(2)} rows/s`;
}

interface TqdmProgressProps {
  status: RunStatus | null;
  completed_count: number;
  total_count: number;
  started_at: string | null;
  finished_at: string | null;
}

function TqdmProgress({
  status,
  completed_count,
  total_count,
  started_at,
  finished_at,
}: TqdmProgressProps): JSX.Element {
  const now = useNow(status === "running" ? 1_000 : null);

  const elapsed_seconds = useMemo(() => {
    if (!started_at) return 0;
    const start = new Date(started_at).getTime();
    const end = finished_at ? new Date(finished_at).getTime() : now;
    return Math.max(0, (end - start) / 1_000);
  }, [started_at, finished_at, now]);

  const speed = elapsed_seconds > 0 ? completed_count / elapsed_seconds : 0;

  if (status === "queued" || status === null) {
    return (
      <div className="rounded-md bg-muted px-3 py-2 font-mono text-xs text-muted-foreground">
        Queued
      </div>
    );
  }

  if (status === "succeeded") {
    const bar = FILLED_CHAR.repeat(BAR_WIDTH);
    const counts = total_count > 0
      ? `${total_count.toLocaleString()}/${total_count.toLocaleString()}`
      : `${completed_count.toLocaleString()} rows`;
    return (
      <div className="rounded-md bg-green-50 px-3 py-2 font-mono text-xs text-green-700 dark:bg-green-950/30 dark:text-green-400">
        Done: {bar}  {counts} [{formatDuration(elapsed_seconds)}]
      </div>
    );
  }

  if (status === "failed" || status === "cancelled") {
    const label = status === "failed" ? "Failed" : "Cancelled";
    return (
      <div className="rounded-md bg-destructive/10 px-3 py-2 font-mono text-xs text-destructive">
        {label} after {completed_count.toLocaleString()} rows [{formatDuration(elapsed_seconds)}]
      </div>
    );
  }

  if (total_count > 0) {
    const ratio = Math.min(completed_count / total_count, 1);
    const filled = Math.round(ratio * BAR_WIDTH);
    const bar = FILLED_CHAR.repeat(filled) + EMPTY_CHAR.repeat(BAR_WIDTH - filled);
    const remaining_seconds = speed > 0 ? (total_count - completed_count) / speed : 0;
    return (
      <div className="rounded-md bg-blue-50 px-3 py-2 font-mono text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-400">
        Processing: {bar}  {completed_count.toLocaleString()}/{total_count.toLocaleString()} [{formatDuration(elapsed_seconds)}{"<"}{formatDuration(remaining_seconds)}, {formatSpeed(speed)}]
      </div>
    );
  }

  return (
    <div className="rounded-md bg-blue-50 px-3 py-2 font-mono text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-400">
      Processing: {completed_count.toLocaleString()} rows [{formatDuration(elapsed_seconds)}, {formatSpeed(speed)}]
    </div>
  );
}

function useNow(interval_ms: number | null): number {
  const [now, set_now] = useState(Date.now());
  useEffect(() => {
    if (interval_ms === null) return;
    const id = setInterval(() => set_now(Date.now()), interval_ms);
    return () => clearInterval(id);
  }, [interval_ms]);
  return now;
}
