/**
 * Auto-layout helper used when a saved YAML omits per-node positions.
 *
 * The strategy is intentionally simple: column-by-category. Data sources
 * sit on the left, processors in the middle, outputs on the right, and
 * resource nodes (LLM Call, Codebook) drop above and below the processor
 * column. The user can drag any node freely after the auto-layout has
 * placed it; on save, the user's positions are persisted so a reload
 * skips the auto-layout entirely.
 */

import type { BaseNode, NodePosition } from "./base_node";

const COLUMN_GAP = 280;
const ROW_GAP = 140;

/**
 * Assign reasonable default ``position`` values to every node whose
 * position has not been set by the YAML or by user interaction.
 *
 * Mutates the input nodes in place. Returns the same array for chaining.
 */
export function auto_layout(nodes: BaseNode[]): BaseNode[] {
  const data_sources: BaseNode[] = [];
  const processors: BaseNode[] = [];
  const outputs: BaseNode[] = [];
  const resources: BaseNode[] = [];

  for (const node of nodes) {
    if (!node_position_is_unset(node.position)) {
      continue;
    }
    if (node.node_type === "csv_input" || node.node_type === "json_input") {
      data_sources.push(node);
    } else if (node.node_type === "csv_output" || node.node_type === "json_output") {
      outputs.push(node);
    } else if (node.node_type === "processor") {
      processors.push(node);
    } else {
      resources.push(node);
    }
  }

  layout_column(data_sources, 0);
  layout_column(processors, COLUMN_GAP);
  layout_column(outputs, COLUMN_GAP * 2);
  layout_column_split(resources, COLUMN_GAP, processors.length);

  return nodes;
}

function node_position_is_unset(position: NodePosition): boolean {
  return position.x === 0 && position.y === 0;
}

function layout_column(column_nodes: BaseNode[], x: number): void {
  for (let row_index = 0; row_index < column_nodes.length; row_index += 1) {
    const node = column_nodes[row_index]!;
    node.position = { x, y: row_index * ROW_GAP };
  }
}

function layout_column_split(
  resource_nodes: BaseNode[],
  processor_x: number,
  processor_count: number,
): void {
  const middle_y = ((processor_count - 1) * ROW_GAP) / 2;
  for (let index = 0; index < resource_nodes.length; index += 1) {
    const node = resource_nodes[index]!;
    const offset_y = (index % 2 === 0 ? -1 : 1) * (Math.floor(index / 2) + 1) * ROW_GAP;
    node.position = { x: processor_x, y: middle_y + offset_y };
  }
}
