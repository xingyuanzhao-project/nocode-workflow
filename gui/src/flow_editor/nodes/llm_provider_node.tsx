/**
 * Canvas node for one :class:`LLMCallNode` typed model.
 *
 * Exposes a compact provider / model / resource-id summary. The
 * property panel lets the user edit temperature, max tokens, and
 * the API-key environment variable name.
 *
 * Renders one default target handle on the left edge (the LLMCall
 * edge's target endpoint) and no source handle — an LLM Call is a
 * leaf consumer in the graph.
 */

import type { NodeProps } from "reactflow";
import { Position } from "reactflow";

import { NodeCard } from "./node_card";

export interface LLMProviderNodeData {
  node_type_id: "llm_call";
  label: string;
  category: "resource";
  /** Resource id (defaults to ``"default"``). */
  resource_id: string;
  /** Provider name (openrouter / openai / local_vllm). */
  provider: string;
  /** Model identifier. */
  model: string;
  /** Temperature, shown as a small readout. */
  temperature: number;
  /** Single ``max_tokens`` cap for every call this LLM resource serves. */
  max_tokens: number;
}

export function LLMProviderNode({
  data,
  selected,
}: NodeProps<LLMProviderNodeData>): JSX.Element {
  return (
    <NodeCard
      category="Resource"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_input_handle={true}
      input_handle_position={Position.Bottom}
      has_output_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        <span>
          Id: <span className="font-mono">{data.resource_id}</span>
        </span>
        <span>
          Provider: <span className="font-mono">{data.provider}</span>
        </span>
        <span
          className="truncate font-mono"
          title={data.model}
        >
          {data.model || "— no model —"}
        </span>
        <span className="text-muted-foreground">
          T={(data.temperature ?? 0).toFixed(2)} · max_tokens={data.max_tokens ?? 1024}
        </span>
      </div>
    </NodeCard>
  );
}
