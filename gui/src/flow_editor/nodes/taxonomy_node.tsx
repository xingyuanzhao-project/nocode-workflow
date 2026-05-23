/**
 * Canvas node for the codebook (taxonomy) resource reference.
 *
 * In hosted mode the node carries a server-managed codebook id; in
 * local-file mode it carries a project-root-relative POSIX path. The
 * runtime resolves whichever is set via the codebook_inquiry edge that
 * lands on this node.
 *
 * Renders one default target handle on the left edge (the
 * codebook_inquiry edge's target endpoint) and no source handle — the
 * codebook is a leaf consumer in the graph.
 */

import type { NodeProps } from "reactflow";
import { Position } from "reactflow";

import { NodeCard } from "./node_card";

export interface TaxonomyNodeData {
  node_type_id: "codebook";
  label: string;
  category: "resource";
  /** Saved codebook id (hosted mode) or ``null`` when using a file. */
  codebook_id: string | null;
  /** Local-file path (used when ``codebook_id`` is ``null``). */
  codebook_path: string | null;
}

export function TaxonomyNode({
  data,
  selected,
}: NodeProps<TaxonomyNodeData>): JSX.Element {
  const display_name =
    data.codebook_id || data.codebook_path || "— not selected —";
  return (
    <NodeCard
      category="Resource"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_input_handle={true}
      input_handle_position={Position.Top}
      has_output_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        <span className="truncate font-mono" title={display_name}>
          {display_name}
        </span>
      </div>
    </NodeCard>
  );
}
