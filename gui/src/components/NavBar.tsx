/**
 * Top navigation bar shown on every route.
 *
 * The bar carries the app title and a compact set of links to the
 * three top-level sections (Flows, Taxonomies, Settings). Route
 * highlighting is driven by React Router's NavLink so the active
 * page gets a foreground-coloured pill.
 */

import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

interface NavEntry {
  to: string;
  label: string;
}

const PRIMARY_NAV_ENTRIES: NavEntry[] = [
  { to: "/flows", label: "Flows" },
  { to: "/data", label: "Data" },
  { to: "/codebook", label: "Codebook" },
  { to: "/settings", label: "API Keys" },
];

/**
 * Top navigation bar. Pure layout; owns no state.
 */
export function NavBar(): JSX.Element {
  return (
    <header className="flex h-14 items-center border-b bg-background px-6">
      <NavLink to="/flows" className="text-lg font-semibold tracking-tight">
        agent_paper
      </NavLink>
      <nav className="ml-8 flex gap-1 text-sm">
        {PRIMARY_NAV_ENTRIES.map((entry) => (
          <NavLink
            key={entry.to}
            to={entry.to}
            className={({ isActive }) =>
              cn(
                "rounded-md px-3 py-1.5 transition-colors",
                isActive
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )
            }
          >
            {entry.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
