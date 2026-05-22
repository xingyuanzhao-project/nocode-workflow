/**
 * Canvas node for the prompts-registry reference.
 *
 * Carries the project-root-relative POSIX path of the prompts file
 * (``config/prompts.json``). Processor nodes reference individual
 * keys inside the file via their ``prompts_ref`` field; this node
 * is the visual representation of the shared file that defines
 * those keys.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface PromptsNodeData {
  node_type_id: "prompts";
  label: string;
  category: "resource";
  /** Project-root-relative POSIX path. */
  prompts_path: string;
}

export function PromptsNode({
  data,
  selected,
}: NodeProps<PromptsNodeData>): JSX.Element {
  return (
    <NodeCard
      category="Resource"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_input_handle={false}
    >
      <span className="truncate font-mono" title={data.prompts_path}>
        {data.prompts_path || "— path unset —"}
      </span>
    </NodeCard>
  );
}
