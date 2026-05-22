/**
 * Canvas node for a generic processor step.
 *
 * One component covers every :attr:`NodeTypeEntry.category` =
 * ``processor`` entry; the differences between
 * ``single_summary`` / ``conversation_summary_first`` /
 * ``conversation_summary_update`` / ``label_extraction`` /
 * ``label_summary`` / ``classification`` show up as different
 * ``node_type_id`` values plus step-specific ``mode`` / ``keys``
 * fields in the property panel.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface ProcessingNodeData {
  node_type_id: string;
  label: string;
  category: "processor";
  /** One of ``"row"`` / ``"document"`` / ``"entity"``. */
  unit: string;
  /** ``"hybrid"`` or ``"full_async"`` for label_summary. */
  mode?: string | null;
  /** ``"all"`` or a list of keys for classification. */
  keys?: unknown;
  /** Resource id the step wires to (defaults to ``"default"``). */
  llm_resource_id?: string | null;
  /** Whether the step has a custom io_schema override. */
  has_io_schema_override?: boolean;
  /** Whether the step has a custom prompt override. */
  has_prompt_override?: boolean;
}

export function ProcessingNode({
  data,
  selected,
}: NodeProps<ProcessingNodeData>): JSX.Element {
  const override_count =
    (data.has_io_schema_override ? 1 : 0) +
    (data.has_prompt_override ? 1 : 0);
  return (
    <NodeCard
      category="Processing"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
    >
      <div className="flex flex-col gap-0.5">
        <span>
          Unit: <span className="font-mono">{data.unit}</span>
        </span>
        {data.mode ? (
          <span>
            Mode: <span className="font-mono">{data.mode}</span>
          </span>
        ) : null}
        {typeof data.keys === "string" ? (
          <span>
            Keys: <span className="font-mono">{data.keys}</span>
          </span>
        ) : null}
        <span>
          LLM:{" "}
          <span className="font-mono">
            {data.llm_resource_id ?? "default"}
          </span>
        </span>
        {override_count > 0 ? (
          <span className="text-muted-foreground">
            {override_count} override{override_count === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
    </NodeCard>
  );
}
