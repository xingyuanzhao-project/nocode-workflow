/**
 * Auto-layout helper used when a saved YAML omits per-node positions.
 *
 * Layout strategy (left-to-right flow):
 *
 *              LLM Call (above)
 *                  |
 *  Data Source → Processor → Output
 *                  |
 *              Codebook (below)
 */

import type { BaseNode, NodePosition } from "./base_node";

const COLUMN_GAP = 280;
const ROW_GAP = 140;

export function auto_layout(nodes: BaseNode[]): BaseNode[] {
  const data_sources: BaseNode[] = [];
  const processors: BaseNode[] = [];
  const outputs: BaseNode[] = [];
  const llm_nodes: BaseNode[] = [];
  const codebook_nodes: BaseNode[] = [];

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
    } else if (node.node_type === "llm_call") {
      llm_nodes.push(node);
    } else if (node.node_type === "codebook") {
      codebook_nodes.push(node);
    } else {
      processors.push(node);
    }
  }

  const processor_top_y = ROW_GAP;
  const processor_x = COLUMN_GAP;

  layout_column(data_sources, 0, processor_top_y);
  layout_column(processors, processor_x, processor_top_y);
  layout_column(outputs, COLUMN_GAP * 2, processor_top_y);

  const processor_bottom_y = processor_top_y + (processors.length - 1) * ROW_GAP;

  layout_column(llm_nodes, processor_x, processor_top_y - ROW_GAP * llm_nodes.length);
  layout_column(codebook_nodes, processor_x, processor_bottom_y + ROW_GAP);

  return nodes;
}

function node_position_is_unset(position: NodePosition): boolean {
  return position.x === 0 && position.y === 0;
}

function layout_column(column_nodes: BaseNode[], x: number, start_y: number): void {
  for (let i = 0; i < column_nodes.length; i += 1) {
    column_nodes[i]!.position = { x, y: start_y + i * ROW_GAP };
  }
}
