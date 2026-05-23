/**
 * Edge representing "this processor calls this LLM".
 *
 * Drawn from a processor's top handle (``llm-out`` source id) to the
 * default unnamed target handle on the LLM Call node's left edge. The
 * runtime resolves the per-processor LLM client by following this edge
 * from the processor to the target ``llm_call`` node and reading its
 * provider / model / api_base / temperature / max_tokens config.
 */

import { BaseEdge } from "../base_edge";
import type { BaseNode } from "../base_node";
import { LLMCallNode } from "../nodes/llm_call_node";
import { ProcessorNode } from "../nodes/processor_node";

export class LLMCallEdge extends BaseEdge {
  readonly edge_type = "llm_call";
  readonly source_handle: string | null = "llm-out";
  readonly target_handle: string | null = "data-in";
  readonly has_arrow = true;

  constructor(source_node_id: string, target_node_id: string) {
    super("llm_call", source_node_id, target_node_id);
  }

  validate(source_node: BaseNode, target_node: BaseNode): string | null {
    if (!(source_node instanceof ProcessorNode)) {
      return (
        `LLM Call edge must start from a processor, ` +
        `not ${source_node.label} (${source_node.node_type}).`
      );
    }
    if (!(target_node instanceof LLMCallNode)) {
      return (
        `LLM Call edge must end at an LLM Call node, ` +
        `not ${target_node.label} (${target_node.node_type}).`
      );
    }
    return null;
  }
}
