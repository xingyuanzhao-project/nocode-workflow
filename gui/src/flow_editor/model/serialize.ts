/**
 * Serialise the typed flow model into the YAML-ready JS object.
 *
 * Output shape mirrors the new ``flow:`` envelope defined in
 * :class:`src.flow_loader.FlowDocument`. Node and edge order matches the
 * order of the typed arrays passed in, so a stable diff is preserved
 * across save/load round-trips.
 */

import type { BaseEdge } from "./base_edge";
import type { BaseNode } from "./base_node";

/** Serialised node entry, matching :class:`src.flow_loader.NodeEntry`. */
export interface SerializedNodeEntry {
  id: string;
  type: string;
  position?: { x: number; y: number };
  config: Record<string, unknown>;
}

/** Serialised edge entry, matching :class:`src.flow_loader.EdgeEntry`. */
export interface SerializedEdgeEntry {
  type: string;
  source: string;
  target: string;
}

/** Settings block serialised verbatim from :class:`useFlowSettingsStore`. */
export interface SerializedFlowSettings {
  processing_limit: number | null;
  async: {
    enabled: boolean;
    max_concurrent_rows: number;
    max_concurrent_llm_calls: number;
    max_retries: number;
  };
  logging: {
    file: string;
    log_progress: boolean;
    log_prompts: boolean;
    log_response: boolean;
  };
  display: {
    use_progress_bar: boolean;
  };
}

/**
 * Top-level shape produced by :func:`serialize_flow_document`. Wrapped in
 * ``{ flow: ... }`` envelope on disk.
 */
export interface SerializedFlowDocument {
  name: string;
  description: string;
  nodes: SerializedNodeEntry[];
  edges: SerializedEdgeEntry[];
  settings: SerializedFlowSettings;
}

export interface SerializeArgs {
  name: string;
  description: string;
  nodes: BaseNode[];
  edges: BaseEdge[];
  settings: SerializedFlowSettings;
  /** When ``true``, persist each node's canvas position; otherwise omit. */
  include_positions?: boolean;
}

/**
 * Build the JS object that is then YAML-dumped under the ``flow:`` key.
 *
 * Position persistence is on by default so what the user sees on the
 * canvas survives the round-trip. Pass ``include_positions: false`` only
 * when you need a position-free document (e.g. for a portable template).
 */
export function serialize_flow_document(args: SerializeArgs): SerializedFlowDocument {
  const include_positions = args.include_positions !== false;
  const nodes: SerializedNodeEntry[] = args.nodes.map((typed_node) => {
    const entry: SerializedNodeEntry = {
      id: typed_node.id,
      type: typed_node.node_type,
      config: typed_node.emit_config(),
    };
    if (include_positions) {
      entry.position = {
        x: typed_node.position.x,
        y: typed_node.position.y,
      };
    }
    return entry;
  });
  const edges: SerializedEdgeEntry[] = args.edges.map((typed_edge) => ({
    type: typed_edge.edge_type,
    source: typed_edge.source_node_id,
    target: typed_edge.target_node_id,
  }));
  return {
    name: args.name,
    description: args.description,
    nodes,
    edges,
    settings: args.settings,
  };
}
