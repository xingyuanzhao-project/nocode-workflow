/**
 * Page listing all past runs with status, timestamps, and navigation.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listRuns } from "@/api/runs";
import type { RunListItem, RunStatus } from "@/schemas/run";

const RUNS_QUERY_KEY = ["runs-list"] as const;

function StatusBadge({ status }: { status: RunStatus }): JSX.Element {
  const styles: Record<RunStatus, string> = {
    queued: "bg-slate-100 text-slate-700",
    running: "bg-blue-100 text-blue-700",
    succeeded: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-amber-100 text-amber-700",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      {status}
    </span>
  );
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function truncateId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) + "…" : id;
}

export default function RunsListPage(): JSX.Element {
  const runs_query = useQuery({
    queryKey: RUNS_QUERY_KEY,
    queryFn: listRuns,
    staleTime: 10_000,
  });

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <h1 className="text-lg font-semibold">Runs</h1>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {runs_query.isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : runs_query.isError ? (
          <div className="text-sm text-destructive">
            Could not load runs: {String(runs_query.error)}
          </div>
        ) : (runs_query.data ?? []).length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No runs yet. Start a flow to see runs here.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Run ID</th>
                <th className="py-2 pr-3 font-medium">Flow Name</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Started At</th>
                <th className="py-2 pr-3 font-medium">Finished At</th>
              </tr>
            </thead>
            <tbody>
              {(runs_query.data ?? []).map((run: RunListItem) => (
                <tr key={run.run_id} className="border-b last:border-0">
                  <td className="py-2 pr-3">
                    <Link
                      to={`/runs/${encodeURIComponent(run.run_id)}`}
                      className="font-mono text-xs text-blue-600 hover:underline"
                      title={run.run_id}
                    >
                      {truncateId(run.run_id)}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 text-muted-foreground">
                    {run.flow_name ?? "—"}
                  </td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {formatTimestamp(run.started_at)}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {formatTimestamp(run.finished_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
