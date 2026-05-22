/**
 * Run viewer page.
 *
 * Responsibilities:
 *
 * - Poll ``/api/flow/status/{run_id}`` every two seconds until the
 *   run reaches a terminal state.
 * - Show live logs via :func:`use_run_log_stream` +
 *   :class:`LogStreamViewer`.
 * - When the run succeeds, fetch the summary preview via
 *   :func:`previewRunArtifact` and render it with
 *   :class:`ResultsPreviewTable`; expose artifact-download buttons.
 * - Offer a Resume button for failed / cancelled runs.
 */

import { useMemo } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getRunStatus, resumeRun } from "@/api/flows";
import {
  artifactDownloadUrl,
  previewRunArtifact,
} from "@/api/runs";
import { Button } from "@/components/ui/button";
import { LogStreamViewer } from "@/components/LogStreamViewer";
import { ResultsPreviewTable } from "@/components/ResultsPreviewTable";
import { useRunLogStream } from "@/hooks/use_run_log_stream";
import {
  ARTIFACT_NAMES,
  type ArtifactName,
} from "@/schemas/results";
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
    queryFn: () =>
      previewRunArtifact(run_id as string, "summary", PREVIEW_ROW_LIMIT),
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
        completed_entity_count: 0,
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
        <span className="text-xs text-muted-foreground">
          {status_query.data?.completed_entity_count
            ? `${status_query.data.completed_entity_count.toLocaleString()} entities completed`
            : null}
        </span>
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

      {status_query.data?.error ? (
        <div className="rounded-md border border-destructive bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {status_query.data.error}
        </div>
      ) : null}

      <section className="flex min-h-0 flex-1 gap-4">
        <div className="flex w-[45%] min-w-[24rem] flex-col gap-3">
          <div className="flex min-h-0 flex-1">
            <LogStreamViewer
              lines={log_stream.lines}
              terminal_status={log_stream.terminal_status}
              connection_error={log_stream.connection_error}
            />
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">Artifacts</h2>
            {ARTIFACT_NAMES.map((artifact_name: ArtifactName) => (
              <a
                key={artifact_name}
                href={
                  run_id ? artifactDownloadUrl(run_id, artifact_name) : "#"
                }
              >
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!is_terminal || status_query.data?.status !== "succeeded"}
                >
                  Download {artifact_name}.csv
                </Button>
              </a>
            ))}
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
