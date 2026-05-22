/**
 * Browser entry point for the agent_paper GUI.
 *
 * Mounts `<App />` into the `#root` element declared in index.html.
 * React strict mode is enabled so development catches
 * double-effect / legacy-lifecycle bugs early.
 */

import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "@/App";
import "@/styles/globals.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root mount node in index.html");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
