/**
 * Zustand store tracking active runs across pages.
 *
 * Used by the run viewer and by any other page that needs to peek at
 * which runs are still in-flight (for example a badge on the
 * NavBar). Entries are indexed by ``run_id``.
 *
 * The store does not itself poll the backend; the Run page installs
 * a TanStack Query poll against ``/api/flow/status/{run_id}`` and
 * writes each result here through :func:`upsert_run`. That keeps
 * polling centralised where the component tree has access to the
 * React context.
 */

import { create, type StoreApi, type UseBoundStore } from "zustand";

import { TERMINAL_RUN_STATUSES, type RunStatusDTO } from "@/schemas/run";

export interface RunStoreState {
  /** Runs keyed by ``run_id``. */
  active_runs: Record<string, RunStatusDTO>;

  /** Insert or update a run's status. */
  upsert_run: (status: RunStatusDTO) => void;
  /** Remove one run entry (used after a user dismisses a toast). */
  remove_run: (run_id: string) => void;
  /** Drop every run that has already reached a terminal status. */
  prune_terminal_runs: () => void;
}

export const useRunStore: UseBoundStore<StoreApi<RunStoreState>> = create<
  RunStoreState
>((set) => ({
  active_runs: {},

  upsert_run: (status) =>
    set((state) => ({
      active_runs: { ...state.active_runs, [status.run_id]: status },
    })),
  remove_run: (run_id) =>
    set((state) => {
      const next_active_runs = { ...state.active_runs };
      delete next_active_runs[run_id];
      return { active_runs: next_active_runs };
    }),
  prune_terminal_runs: () =>
    set((state) => {
      const filtered: Record<string, RunStatusDTO> = {};
      for (const [run_id, status] of Object.entries(state.active_runs)) {
        if (!TERMINAL_RUN_STATUSES.has(status.status)) {
          filtered[run_id] = status;
        }
      }
      return { active_runs: filtered };
    }),
}));
