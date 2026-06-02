/**
 * React Router configuration for the nocode-workflow GUI.
 *
 * One route per top-level page. Page components are imported lazily
 * so the initial bundle stays small; only the landing route is
 * eager-loaded.
 *
 * The layout route renders the shared NavBar and an `<Outlet />` so
 * every page shares the same chrome.
 */

import { Suspense, lazy } from "react";
import {
  Navigate,
  Outlet,
  createBrowserRouter,
  type RouteObject,
} from "react-router-dom";

import { NavBar } from "@/components/NavBar";

const LandingPage = lazy(() => import("@/pages/LandingPage"));
const MyFlowsPage = lazy(() => import("@/pages/MyFlowsPage"));
const FlowEditorPage = lazy(() => import("@/pages/FlowEditorPage"));
const RunsListPage = lazy(() => import("@/pages/RunsListPage"));
const RunPage = lazy(() => import("@/pages/RunPage"));
const DataPage = lazy(() => import("@/pages/DataPage"));
const CodebookListPage = lazy(() => import("@/pages/CodebookListPage"));
const CodebookEditorPage = lazy(() => import("@/pages/CodebookEditorPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));

/**
 * Shared layout shown around every route: NavBar on top, route body
 * below, and a Suspense boundary so lazy-loaded pages show a short
 * fallback while their chunk loads.
 */
function AppLayout(): JSX.Element {
  return (
    <div className="flex h-screen flex-col">
      <NavBar />
      <main className="flex-1 overflow-auto">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center text-muted-foreground">
              Loading...
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}

const ROUTES: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "flows", element: <MyFlowsPage /> },
      { path: "flows/new", element: <FlowEditorPage mode="new" /> },
      { path: "flows/:flow_id/edit", element: <FlowEditorPage mode="edit" /> },
      { path: "runs", element: <RunsListPage /> },
      { path: "runs/:run_id", element: <RunPage /> },
      { path: "data", element: <DataPage /> },
      { path: "codebook", element: <CodebookListPage /> },
      {
        path: "codebook/:codebook_id",
        element: <CodebookEditorPage />,
      },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/flows" replace /> },
    ],
  },
];

/** Module-level router singleton imported by `App`. */
export const router = createBrowserRouter(ROUTES);
