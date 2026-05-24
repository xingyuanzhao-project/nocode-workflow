/**
 * Human-readable captions shown on flow-editor edges.
 *
 * Most edge captions are semantic verbs rather than raw category/unit
 * pairs so the canvas reads like an action graph:
 *
 * - data source -> processor: "Feed Forward"
 * - processor -> resource: "Call"
 * - processor -> processor: "Feed Forward"
 * - processor -> any output node: "Save"
 *
 * Unknown combinations fall back to the original "source -> target"
 * badge text built from the endpoint unit/category summaries.
 */

import type { UnitValue } from "@/lib/unit_compatibility";

export interface EdgeEndpointSummary {
  node_type_id: string | null;
  category: string | null;
  unit: UnitValue | null;
}

function describeEndpoint(endpoint: EdgeEndpointSummary): string {
  return endpoint.unit ?? endpoint.category ?? "?";
}

function isOutputNode(endpoint: EdgeEndpointSummary): boolean {
  return (
    typeof endpoint.node_type_id === "string" &&
    endpoint.node_type_id.endsWith("_output")
  );
}

export function buildEdgeBadgeText(
  source: EdgeEndpointSummary | null,
  target: EdgeEndpointSummary | null,
): string {
  if (!source || !target) {
    return "";
  }

  if (source.category === "data" && target.category === "processor") {
    return "Feed Forward";
  }

  if (source.category === "processor" && target.category === "resource") {
    return "Call";
  }

  if (source.category === "processor" && target.category === "processor") {
    return "Feed Forward";
  }

  if (source.category === "processor" && isOutputNode(target)) {
    return "Save";
  }

  return `${describeEndpoint(source)} \u2192 ${describeEndpoint(target)}`;
}
