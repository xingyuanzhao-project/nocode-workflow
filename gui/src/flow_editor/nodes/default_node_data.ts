/**
 * Default ``data`` payloads for every palette-dropped node.
 *
 * Separated from ``FlowCanvas`` so the same function can be reused
 * by RTL tests that want to assert "the canvas's drop produces a
 * payload that every node component renders without crashing" and
 * by the codec tests that assemble a palette-built graph.
 *
 * Per-type defaults mirror the fields each node component reads in
 * its render body. The DataSource crash of 2026-04 originated here
 * — the canvas shipped an empty payload and ``DataSourceNode`` called
 * ``Object.values(undefined)``. Every subsequent type now has a
 * sensible default so no component has to defend against missing
 * keys at render time.
 */

import type { NodeTypeEntry } from "@/schemas/node_types";

/**
 * Return the default ``data`` payload dropped onto the canvas for
 * ``entry``.
 *
 * @param entry - The :class:`NodeTypeEntry` the palette advertised.
 * @returns Payload assigned to the new React Flow node's ``data``.
 */
export function buildDefaultNodeData(
  entry: NodeTypeEntry,
): Record<string, unknown> {
  const shared_payload: Record<string, unknown> = {
    node_type_id: entry.id,
    label: entry.label || entry.id,
    category: entry.category,
    default_unit: entry.default_unit,
    consumes: entry.consumes,
    produces: entry.produces,
    llm_backed: entry.llm_backed,
    requires_resources: entry.requires_resources,
    default_io_schema: entry.default_io_schema,
    default_prompt_ref: entry.default_prompt_ref,
    default_group_by: entry.default_group_by,
    overrides: {},
  };
  const per_type_defaults = _per_type_default_payload(entry.id);
  return { ...shared_payload, ...per_type_defaults };
}

function _per_type_default_payload(
  node_type_id: string,
): Record<string, unknown> {
  switch (node_type_id) {
    case "csv_input":
      return { upload: null, column_roles: {} };
    case "csv_output":
      return {
        summary_csv: "results/summary.csv",
        results_csv: null,
        states_csv: null,
        spans_csv: null,
        extend: false,
      };
    case "llm_provider":
      return {
        resource_id: "default",
        provider: "openrouter",
        model: "",
        api_base: "https://openrouter.ai/api/v1",
        api_key_env: "OPENROUTER_API_KEY",
        temperature: 0,
        max_tokens_summary: 1024,
        max_tokens_classification: 256,
      };
    case "taxonomy":
      return { taxonomy_id: null, taxonomy_path: "config/taxonomy.json" };
    case "prompts":
      return { prompts_path: "config/prompts.json" };
    case "group_by":
      return {
        entity_column: "",
        sort_by_column: "",
        entity_count_estimate: null,
        avg_documents_per_entity: null,
      };
    default:
      return {};
  }
}
