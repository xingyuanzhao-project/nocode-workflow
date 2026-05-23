/**
 * Edge representing "this processor consults this codebook".
 *
 * Drawn from a processor's bottom handle (``cb-out`` source id) to the
 * default unnamed target handle on the Codebook node's left edge. The
 * runtime resolves the per-processor codebook by following this edge
 * from the processor to the target ``codebook`` node and reading its
 * codebook_id / codebook_path config.
 */

import { BaseEdge } from "../base_edge";
import type { BaseNode } from "../base_node";
import { CodebookNode } from "../nodes/codebook_node";
import { ProcessorNode } from "../nodes/processor_node";

export class CodebookInquiryEdge extends BaseEdge {
  readonly edge_type = "codebook_inquiry";
  readonly source_handle: string | null = "cb-out";
  readonly target_handle: string | null = "data-in";
  readonly has_arrow = true;

  constructor(source_node_id: string, target_node_id: string) {
    super("codebook_inquiry", source_node_id, target_node_id);
  }

  validate(source_node: BaseNode, target_node: BaseNode): string | null {
    if (!(source_node instanceof ProcessorNode)) {
      return (
        `Codebook Inquiry edge must start from a processor, ` +
        `not ${source_node.label} (${source_node.node_type}).`
      );
    }
    if (!(target_node instanceof CodebookNode)) {
      return (
        `Codebook Inquiry edge must end at a Codebook node, ` +
        `not ${target_node.label} (${target_node.node_type}).`
      );
    }
    return null;
  }
}
