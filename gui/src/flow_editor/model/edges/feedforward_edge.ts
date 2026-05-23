/**
 * Feedforward data-flow edge between two pipeline stages.
 *
 * Drawn from the ``right`` side (default unnamed source handle) of the
 * source node to the ``left`` side (default unnamed target handle) of
 * the target node. Allowed pairs:
 *
 * - DataSource    → Processor
 * - Processor     → Processor (subject to unit compatibility)
 * - Processor     → Output
 *
 * The runtime walks ``feedforward`` edges to derive processor execution
 * order via topological sort.
 */

import { BaseEdge } from "../base_edge";
import type { BaseNode } from "../base_node";
import {
  ProcessorNode,
  is_valid_unit_transition,
} from "../nodes/processor_node";
import { DataSourceNode } from "../nodes/data_source_node";
import { OutputNode } from "../nodes/output_node";

export class FeedforwardEdge extends BaseEdge {
  readonly edge_type = "feedforward";
  readonly source_handle: string | null = "data-out";
  readonly target_handle: string | null = "data-in";
  readonly has_arrow = true;

  constructor(source_node_id: string, target_node_id: string) {
    super("feedforward", source_node_id, target_node_id);
  }

  validate(source_node: BaseNode, target_node: BaseNode): string | null {
    const source_is_valid =
      source_node instanceof DataSourceNode || source_node instanceof ProcessorNode;
    const target_is_valid =
      target_node instanceof ProcessorNode || target_node instanceof OutputNode;
    if (!source_is_valid) {
      return (
        `Feedforward edge cannot start at ${source_node.label} ` +
        `(${source_node.node_type}); only data sources and processors emit data.`
      );
    }
    if (!target_is_valid) {
      return (
        `Feedforward edge cannot end at ${target_node.label} ` +
        `(${target_node.node_type}); only processors and outputs accept data.`
      );
    }
    if (
      source_node instanceof ProcessorNode &&
      target_node instanceof ProcessorNode
    ) {
      if (!is_valid_unit_transition(source_node.unit, target_node.unit)) {
        return (
          `Invalid unit transition: "${source_node.label}" (${source_node.unit}) ` +
          `cannot feed "${target_node.label}" (${target_node.unit}).`
        );
      }
    }
    return null;
  }
}
