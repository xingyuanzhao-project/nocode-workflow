/**
 * Deserialise a parsed-YAML object into typed nodes and edges.
 *
 * Counterpart of :mod:`./serialize`. Validates the parsed shape via the
 * Zod schema in ``@/schemas/flow`` before constructing typed objects, so
 * a malformed YAML throws cleanly instead of producing partially-typed
 * graph state.
 */

import { auto_layout } from "./layout";
import type { BaseEdge } from "./base_edge";
import { BaseEdge as BaseEdgeClass } from "./base_edge";
import type { BaseNode, NodePosition } from "./base_node";
import { BaseNode as BaseNodeClass } from "./base_node";
import {
  flowDocumentSchema,
  type FlowDocument,
} from "@/schemas/flow";

import "./register";

export interface DeserializedFlow {
  name: string;
  description: string;
  nodes: BaseNode[];
  edges: BaseEdge[];
  settings: FlowDocument["settings"];
}

/**
 * Validate the raw object as a :type:`FlowDocument` and rebuild the typed
 * model from it.
 *
 * Edges whose source or target node does not exist in the parsed nodes
 * list are dropped with a warning; the rest go through their typed
 * subclass's :meth:`validate` and only valid ones survive.
 */
export function deserialize_flow_document(raw: unknown): DeserializedFlow {
  const parsed: FlowDocument = flowDocumentSchema.parse(raw);

  const typed_nodes: BaseNode[] = parsed.nodes.map((entry) => {
    const position: NodePosition = entry.position ?? { x: 0, y: 0 };
    return BaseNodeClass.from_yaml(entry, position);
  });

  const node_by_id = new Map<string, BaseNode>();
  for (const typed_node of typed_nodes) {
    node_by_id.set(typed_node.id, typed_node);
  }

  const typed_edges: BaseEdge[] = [];
  for (const edge_entry of parsed.edges) {
    const source = node_by_id.get(edge_entry.source);
    const target = node_by_id.get(edge_entry.target);
    if (!source || !target) {
      console.warn(
        `Edge ${edge_entry.type} ${edge_entry.source} → ${edge_entry.target} ` +
          "references a missing node; dropped on load.",
      );
      continue;
    }
    const edge = BaseEdgeClass.from_yaml(edge_entry);
    const error_message = edge.validate(source, target);
    if (error_message !== null) {
      console.warn(`Edge dropped: ${error_message}`);
      continue;
    }
    typed_edges.push(edge);
  }

  auto_layout(typed_nodes);

  return {
    name: parsed.name,
    description: parsed.description,
    nodes: typed_nodes,
    edges: typed_edges,
    settings: parsed.settings,
  };
}
