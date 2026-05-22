/**
 * Canvas node for one :class:`src.flow_loader.LLMResource`.
 *
 * Exposes a compact provider / model / resource-id summary. The
 * property panel lets the user edit temperature, max tokens, and
 * the API-key environment variable name.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface LLMProviderNodeData {
  node_type_id: "llm_provider";
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
  /** max_tokens for summary calls. */
  max_tokens_summary: number;
  /** max_tokens for classification calls. */
  max_tokens_classification: number;
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
      has_input_handle={false}
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
          T={data.temperature.toFixed(2)} · summary={data.max_tokens_summary} ·
          class={data.max_tokens_classification}
        </span>
      </div>
    </NodeCard>
  );
}
