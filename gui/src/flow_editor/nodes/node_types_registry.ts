/**
 * Map from ``node_type_id`` to the React Flow node component.
 *
 * :mod:`@/flow_editor/canvas/FlowCanvas` reads this map once at
 * construction and passes it to ReactFlow via ``nodeTypes``. The keys
 * here mirror the ``node_type`` strings used by :class:`BaseNode`
 * subclasses (``processor``, ``llm_call``, ``codebook``, ``csv_input``,
 * ``json_input``, ``csv_output``, ``json_output``).
 */

import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { CSVOutputNode } from "./csv_output_node";
import { DataSourceNode } from "./data_source_node";
import { GenericNode } from "./generic_node";
import { LLMProviderNode } from "./llm_provider_node";
import { ProcessingNode } from "./processing_node";
import { TaxonomyNode } from "./taxonomy_node";

/**
 * Node-type ids known to the front end. Each key matches the
 * ``node_type`` string set by the matching :class:`BaseNode` subclass.
 */
export const KNOWN_NODE_TYPE_IDS: readonly string[] = [
  "csv_input",
  "json_input",
  "csv_output",
  "json_output",
  "llm_call",
  "codebook",
  "processor",
] as const;

const TYPE_TO_COMPONENT: Record<string, ComponentType<NodeProps>> = {
  csv_input: DataSourceNode as ComponentType<NodeProps>,
  json_input: DataSourceNode as ComponentType<NodeProps>,
  csv_output: CSVOutputNode as ComponentType<NodeProps>,
  json_output: CSVOutputNode as ComponentType<NodeProps>,
  llm_call: LLMProviderNode as ComponentType<NodeProps>,
  codebook: TaxonomyNode as ComponentType<NodeProps>,
  processor: ProcessingNode as ComponentType<NodeProps>,
};

/**
 * Build the ``nodeTypes`` map for React Flow. Unknown ids fall back to
 * :class:`GenericNode` so the canvas never crashes if the backend adds
 * a new node type before the GUI is updated.
 */
export function buildNodeTypesRegistry(): Record<
  string,
  ComponentType<NodeProps>
> {
  const registry: Record<string, ComponentType<NodeProps>> = {};
  for (const node_type_id of KNOWN_NODE_TYPE_IDS) {
    registry[node_type_id] =
      TYPE_TO_COMPONENT[node_type_id] ??
      (GenericNode as ComponentType<NodeProps>);
  }
  return registry;
}
