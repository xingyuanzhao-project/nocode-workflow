/**
 * Render smoke for every palette-dropped node.
 *
 * Takes the same default-data payload the canvas builds at drop time
 * and renders the matching component. Fails loudly if a node
 * component throws when it reads its data payload — the exact
 * failure mode of the DataSource crash that kicked this plan off.
 */

import { describe, expect, it } from "vitest";

import { buildDefaultNodeData } from "@/flow_editor/nodes/default_node_data";
import {
  KNOWN_NODE_TYPE_IDS,
  buildNodeTypesRegistry,
} from "@/flow_editor/nodes/node_types_registry";
import type { NodeTypeEntry } from "@/schemas/node_types";

import { renderForUser } from "../_helpers";

function fakeEntry(entry_id: string): NodeTypeEntry {
  const data_ids: ReadonlySet<string> = new Set([
    "csv_input",
    "csv_output",
    "group_by",
  ]);
  const resource_ids: ReadonlySet<string> = new Set([
    "llm_provider",
    "taxonomy",
    "prompts",
  ]);
  const category: NodeTypeEntry["category"] = data_ids.has(entry_id)
    ? "data"
    : resource_ids.has(entry_id)
      ? "resource"
      : "processor";
  return {
    id: entry_id,
    category,
    label: entry_id,
    description: "",
    default_unit: category === "processor" ? "row" : null,
    consumes: [],
    produces: [],
    llm_backed: category === "processor",
    requires_resources: category === "processor" ? ["llm_provider"] : [],
    default_io_schema: null,
    default_prompt_ref: null,
    default_group_by: null,
  };
}

describe("every palette-dropped node renders without crashing", () => {
  const node_components = buildNodeTypesRegistry();
  for (const node_type_id of KNOWN_NODE_TYPE_IDS) {
    it(`renders a ${node_type_id} node with the default drop payload`, () => {
      const entry = fakeEntry(node_type_id);
      const default_data = buildDefaultNodeData(entry);
      const NodeComponent = node_components[node_type_id];
      expect(NodeComponent).toBeDefined();
      // Mimic React Flow's NodeProps shape for the minimal surface
      // the per-type components actually read.
      const node_props = {
        id: `${node_type_id}_test`,
        type: node_type_id,
        data: default_data,
        selected: false,
        isConnectable: true,
        xPos: 0,
        yPos: 0,
        dragging: false,
        zIndex: 0,
      } as Record<string, unknown>;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { container } = renderForUser(<NodeComponent {...(node_props as any)} />);
      expect(container.textContent?.trim().length ?? 0).toBeGreaterThan(0);
    });
  }
});
