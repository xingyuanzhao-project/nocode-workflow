/**
 * Shared helpers for the RTL tier.
 *
 * Every RTL test renders via ``renderForUser`` so the same
 * ``QueryClientProvider`` + ``MemoryRouter`` + ``ReactFlowProvider``
 * wrapper is used in every file. Zustand stores are reset before
 * each render so tests observe only the DOM their component
 * produced.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { ReactFlowProvider } from "reactflow";

import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useFlowSettingsStore } from "@/stores/flow_settings_store";
import { useGraphStore } from "@/stores/graph_store";
import { useRunStore } from "@/stores/run_store";

/**
 * Options accepted by :func:`renderForUser`, on top of RTL's own.
 */
export interface RenderForUserOptions extends RenderOptions {
  /** Initial router entry; defaults to ``/``. */
  initial_route?: string;
  /** Optional pre-built :class:`QueryClient` to share across renders. */
  query_client?: QueryClient;
  /** Seed function invoked after stores are reset and before render. */
  seed_store?: () => void;
}

/**
 * Reset every Zustand store owned by the GUI.
 *
 * Called by :func:`renderForUser` before every render so tests
 * start from a known blank state and can never see residue from a
 * prior test.
 */
export function resetAllStores(): void {
  useGraphStore.getState().clear_graph();
  useGraphStore.temporal.getState().clear();
  useFlowMetadataStore.getState().reset();
  useFlowSettingsStore.getState().reset_settings();
  const run_store = useRunStore.getState();
  for (const run_id of Object.keys(run_store.active_runs)) {
    run_store.remove_run(run_id);
  }
}

/**
 * Render ``ui`` for a user-behaviour test.
 *
 * Wraps the element in the same providers the real app uses so
 * React Flow, TanStack Query, and React Router all behave
 * naturally during the test.
 *
 * @param ui - The element under test.
 * @param options - Router entry, query client, or store seed.
 * @returns The :func:`render` result for further RTL queries.
 */
export function renderForUser(
  ui: ReactElement,
  options: RenderForUserOptions = {},
): ReturnType<typeof render> {
  resetAllStores();
  if (options.seed_store) {
    options.seed_store();
  }
  const query_client =
    options.query_client ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false, staleTime: Infinity },
      },
    });

  function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={query_client}>
        <MemoryRouter initialEntries={[options.initial_route ?? "/"]}>
          <ReactFlowProvider>{children}</ReactFlowProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}
