/**
 * Application shell.
 *
 * Wraps the router in a TanStack Query client, so every page can
 * consume server state through React Query hooks, and the Toaster
 * so UI layers can raise notifications.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { useMemo } from "react";

import { router } from "@/routing";

/**
 * Default TanStack Query options tuned for the GUI.
 *
 * - `refetchOnWindowFocus: false` keeps the flow editor stable when
 *   users switch between tabs during a long run.
 * - `retry: 1` — the backend returns typed errors, so one auto-retry
 *   is sufficient for transient network hiccups.
 * - `staleTime: 30_000` — flows / taxonomies / templates change
 *   rarely; 30 seconds avoids re-fetching across route changes.
 */
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

/**
 * Root application component.
 *
 * Instantiates one :class:`QueryClient` per component-tree mount so
 * tests can remount the app in isolation. The router itself is a
 * module-level singleton defined in `@/routing`.
 */
export function App(): JSX.Element {
  const queryClient = useMemo(buildQueryClient, []);
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
