/**
 * Application shell with a startup readiness gate.
 *
 * On first load the app polls ``GET /api/health`` and shows a minimal
 * loading screen until the backend, Redis, and the Celery worker are
 * all reachable. Once every check passes the normal router mounts.
 *
 * The startup screen uses plain ``fetch`` (no React Query dependency)
 * so it works before ``QueryClientProvider`` is mounted.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { router } from "@/routing";

/* ------------------------------------------------------------------ */
/*  Query client                                                       */
/* ------------------------------------------------------------------ */

function buildQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
}

/* ------------------------------------------------------------------ */
/*  Startup readiness gate                                             */
/* ------------------------------------------------------------------ */

interface HealthPayload {
  status: string;
  redis_ok: boolean;
  worker_ok: boolean;
}

type CheckStatus = "pending" | "ok" | "fail";

interface StartupChecks {
  backend: CheckStatus;
  redis: CheckStatus;
  worker: CheckStatus;
}

const POLL_MS = 1_500;
const TIMEOUT_MS = 60_000;

const CHECK_LABELS: readonly (readonly [keyof StartupChecks, string])[] = [
  ["backend", "Backend"],
  ["redis", "Redis"],
  ["worker", "Worker"],
] as const;

function statusIcon(s: CheckStatus): string {
  if (s === "ok") return "✓";
  if (s === "fail") return "✗";
  return "○";
}

function statusColor(s: CheckStatus): string {
  if (s === "ok") return "text-green-500";
  if (s === "fail") return "text-red-400";
  return "text-muted-foreground animate-pulse";
}

function statusText(s: CheckStatus, name: string): string {
  if (s === "ok") return `${name} ready`;
  if (s === "fail") return `${name} unavailable`;
  return `Waiting for ${name}…`;
}

function StartupScreen({ onReady }: { onReady: () => void }): JSX.Element {
  const [checks, setChecks] = useState<StartupChecks>({
    backend: "pending",
    redis: "pending",
    worker: "pending",
  });
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const start = useRef(Date.now());

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      while (!cancelled) {
        try {
          const res = await fetch("/api/health");
          if (!res.ok) {
            setChecks({ backend: "fail", redis: "pending", worker: "pending" });
            setError(`Backend returned HTTP ${res.status}`);
          } else {
            const data: HealthPayload = await res.json();
            setError(null);
            const next: StartupChecks = {
              backend: "ok",
              redis: data.redis_ok ? "ok" : "fail",
              worker: data.worker_ok ? "ok" : "fail",
            };
            setChecks(next);
            if (data.status === "ok") {
              await new Promise((r) => setTimeout(r, 400));
              if (!cancelled) onReady();
              return;
            }
          }
        } catch {
          setChecks({ backend: "pending", redis: "pending", worker: "pending" });
          setError(null);
        }

        if (Date.now() - start.current > TIMEOUT_MS) {
          setTimedOut(true);
        }

        await new Promise((r) => setTimeout(r, POLL_MS));
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [onReady]);

  return (
    <div className="flex h-screen flex-col items-center justify-center bg-background text-foreground">
      <h1 className="mb-8 text-2xl font-semibold tracking-tight">
        Flow Editor
      </h1>

      <div className="w-64 space-y-3 text-sm">
        {CHECK_LABELS.map(([key, name]) => (
          <div key={key} className="flex items-center gap-3">
            <span className={`font-mono text-base ${statusColor(checks[key])}`}>
              {statusIcon(checks[key])}
            </span>
            <span className={statusColor(checks[key])}>
              {statusText(checks[key], name)}
            </span>
          </div>
        ))}
      </div>

      {error && (
        <p className="mt-6 max-w-sm text-center text-xs text-red-400">
          {error}
        </p>
      )}

      {timedOut && (
        <button
          onClick={onReady}
          className="mt-6 rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent"
        >
          Continue anyway
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Root component                                                     */
/* ------------------------------------------------------------------ */

export function App(): JSX.Element {
  const [ready, setReady] = useState(false);
  const queryClient = useMemo(buildQueryClient, []);
  const handleReady = useCallback(() => setReady(true), []);

  if (!ready) {
    return <StartupScreen onReady={handleReady} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
