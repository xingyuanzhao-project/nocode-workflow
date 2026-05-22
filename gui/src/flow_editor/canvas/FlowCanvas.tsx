/**
 * React Flow canvas component driven by :mod:`@/stores/graph_store`.
 *
 * Responsibilities:
 *
 * - Register the node-type components via ``nodeTypes``, sourced from
 *   :mod:`@/flow_editor/nodes/node_types_registry`.
 * - Accept palette drops: decoded to ``NodeTypeEntry`` via
 *   :func:`@/hooks/use_node_types.useNodeTypes`, then appended to
 *   the graph store with default data.
 * - Track the currently-selected node via
 *   :func:`useGraphStore.set_selected_node_id`.
 */

import type { DragEvent } from "react";
import { useCallback, useMemo, useRef } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type EdgeTypes,
  type NodeTypes,
} from "reactflow";

import "reactflow/dist/style.css";

import { UnitAwareEdge } from "@/flow_editor/edges/unit_aware_edge";
import { NODE_TYPE_DRAG_MIME_TYPE } from "@/flow_editor/palette/NodePalette";
import { buildDefaultNodeData } from "@/flow_editor/nodes/default_node_data";
import { buildNodeTypesRegistry } from "@/flow_editor/nodes/node_types_registry";
import { useNodeTypes } from "@/hooks/use_node_types";
import {
  buildInvalidUnitTransitionMessage,
  isValidUnitTransition,
  type UnitValue,
} from "@/lib/unit_compatibility";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

function generateNodeId(type_id: string): string {
  const random_suffix = Math.random().toString(36).slice(2, 9);
  return `${type_id}_${random_suffix}`;
}

const EDGE_TYPES: EdgeTypes = {
  unit_aware: UnitAwareEdge,
};

const DEFAULT_EDGE_OPTIONS = { type: "unit_aware" } as const;

function readUnitFromNodeData(
  node: GraphNode | undefined,
): UnitValue | null {
  if (!node) {
    return null;
  }
  const unit_candidate = node.data?.unit;
  if (
    unit_candidate === "row" ||
    unit_candidate === "document" ||
    unit_candidate === "entity"
  ) {
    return unit_candidate;
  }
  return null;
}

function readLabelFromNodeData(node: GraphNode | undefined): string {
  if (!node) {
    return "";
  }
  const label_candidate = node.data?.label;
  if (typeof label_candidate === "string") {
    return label_candidate;
  }
  return node.id;
}

function FlowCanvasInner(): JSX.Element {
  const node_types_query = useNodeTypes();

  const nodes = useGraphStore((state) => state.nodes);
  const edges = useGraphStore((state) => state.edges);
  const on_nodes_change = useGraphStore((state) => state.on_nodes_change);
  const on_edges_change = useGraphStore((state) => state.on_edges_change);
  const on_connect = useGraphStore((state) => state.on_connect);
  const add_node = useGraphStore((state) => state.add_node);
  const set_selected_node_id = useGraphStore(
    (state) => state.set_selected_node_id,
  );
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const react_flow_instance = useReactFlow();
  const wrapper_ref = useRef<HTMLDivElement | null>(null);

  const node_types: NodeTypes = useMemo(buildNodeTypesRegistry, []);

  const is_connection_valid = useCallback(
    (connection: Connection): boolean => {
      const source_node = nodes.find((node) => node.id === connection.source);
      const target_node = nodes.find((node) => node.id === connection.target);
      const source_unit = readUnitFromNodeData(source_node);
      const target_unit = readUnitFromNodeData(target_node);
      if (source_unit === null || target_unit === null) {
        // Resource / data nodes have no unit; they are freely connectable.
        return true;
      }
      if (!isValidUnitTransition(source_unit, target_unit)) {
        console.warn(
          buildInvalidUnitTransitionMessage(
            readLabelFromNodeData(source_node),
            source_unit,
            readLabelFromNodeData(target_node),
            target_unit,
          ),
        );
        return false;
      }
      return true;
    },
    [nodes],
  );

  const on_drop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const dragged_type_id = event.dataTransfer.getData(
        NODE_TYPE_DRAG_MIME_TYPE,
      );
      if (!dragged_type_id || !node_types_query.data) {
        return;
      }
      const entry = node_types_query.data.entries.find(
        (candidate) => candidate.id === dragged_type_id,
      );
      if (!entry) {
        return;
      }
      const drop_position = react_flow_instance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      const new_node: GraphNode = {
        id: generateNodeId(entry.id),
        type: entry.id,
        position: drop_position,
        data: buildDefaultNodeData(entry),
      };
      add_node(new_node);
      set_dirty(true);
    },
    [
      node_types_query.data,
      react_flow_instance,
      add_node,
      set_dirty,
    ],
  );

  const on_drag_over = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const on_selection_change = useCallback(
    ({ nodes: selected_nodes }: { nodes: GraphNode[] }) => {
      set_selected_node_id(selected_nodes[0]?.id ?? null);
    },
    [set_selected_node_id],
  );

  return (
    <div ref={wrapper_ref} className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={node_types}
        edgeTypes={EDGE_TYPES}
        defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
        onNodesChange={on_nodes_change}
        onEdgesChange={on_edges_change}
        onConnect={on_connect}
        isValidConnection={is_connection_valid}
        onDrop={on_drop}
        onDragOver={on_drag_over}
        onSelectionChange={on_selection_change}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}

/**
 * Canvas wrapper that supplies the :class:`ReactFlowProvider`
 * React Flow needs for :func:`useReactFlow` to work inside
 * :class:`FlowCanvasInner`.
 */
export function FlowCanvas(): JSX.Element {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner />
    </ReactFlowProvider>
  );
}
