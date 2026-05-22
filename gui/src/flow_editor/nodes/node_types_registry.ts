/**
 * Map from ``node_type_id`` to the React Flow node component.
 *
 * :mod:`@/flow_editor/canvas/FlowCanvas` reads this map once at
 * construction and passes it to ReactFlow via ``nodeTypes``. Each
 * processor step-type id routes to :class:`ProcessingNode`; each
 * resource / data id routes to its dedicated component built in
 * the :mod:`gui_custom_nodes` step.
 */

import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { CSVOutputNode } from "./csv_output_node";
import { DataSourceNode } from "./data_source_node";
import { GenericNode } from "./generic_node";
import { GroupByNode } from "./group_by_node";
import { LLMProviderNode } from "./llm_provider_node";
import { ProcessingNode } from "./processing_node";
import { PromptsNode } from "./prompts_node";
import { TaxonomyNode } from "./taxonomy_node";

/**
 * Node-type ids known to the default registry
 * (``config/node_types.yaml``) plus the UI-only ``group_by`` node.
 *
 * Keeping the list here lets :mod:`@/flow_editor/canvas/FlowCanvas`
 * register a named entry per id, which is what React Flow needs to
 * route ``node.type`` to a component.
 */
export const KNOWN_NODE_TYPE_IDS: readonly string[] = [
  // data
  "csv_input",
  // resources
  "llm_provider",
  "taxonomy",
  "prompts",
  "csv_output",
  // processors
  "single_summary",
  "conversation_summary_first",
  "conversation_summary_update",
  "label_extraction",
  "label_summary",
  "classification",
  // UI-only nodes introduced by the graph codec
  "group_by",
] as const;

const PROCESSOR_NODE_TYPE_IDS: ReadonlySet<string> = new Set([
  "single_summary",
  "conversation_summary_first",
  "conversation_summary_update",
  "label_extraction",
  "label_summary",
  "classification",
]);

const RESOURCE_AND_DATA_COMPONENTS: Record<string, ComponentType<NodeProps>> = {
  csv_input: DataSourceNode as ComponentType<NodeProps>,
  group_by: GroupByNode as ComponentType<NodeProps>,
  llm_provider: LLMProviderNode as ComponentType<NodeProps>,
  taxonomy: TaxonomyNode as ComponentType<NodeProps>,
  prompts: PromptsNode as ComponentType<NodeProps>,
  csv_output: CSVOutputNode as ComponentType<NodeProps>,
};

/**
 * Build the ``nodeTypes`` map for React Flow.
 *
 * Each processor step-type id points at :class:`ProcessingNode`;
 * data and resource ids point at their dedicated components. Unknown
 * ids fall back to :class:`GenericNode` so the canvas never crashes
 * if the backend adds a new node type before the GUI is updated.
 */
export function buildNodeTypesRegistry(): Record<
  string,
  ComponentType<NodeProps>
> {
  const registry: Record<string, ComponentType<NodeProps>> = {};
  for (const node_type_id of KNOWN_NODE_TYPE_IDS) {
    if (PROCESSOR_NODE_TYPE_IDS.has(node_type_id)) {
      registry[node_type_id] = ProcessingNode as ComponentType<NodeProps>;
      continue;
    }
    const specialised = RESOURCE_AND_DATA_COMPONENTS[node_type_id];
    registry[node_type_id] = (specialised ??
      (GenericNode as ComponentType<NodeProps>)) as ComponentType<NodeProps>;
  }
  return registry;
}
