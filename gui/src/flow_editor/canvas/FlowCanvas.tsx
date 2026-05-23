/**
 * React Flow canvas component driven by :mod:`@/stores/graph_store`.
 *
 * Responsibilities:
 *
 * - Register the node-type components via ``nodeTypes``, sourced from
 *   :mod:`@/flow_editor/nodes/node_types_registry`.
 * - Accept palette drops: :class:`NodeTypeEntry` from the palette →
 *   :meth:`BaseNode.from_palette` → store ``add_typed_node``.
 * - Accept user-drawn edges: React Flow ``Connection`` →
 *   :meth:`BaseEdge.from_connection` (called inside the store's
 *   ``on_connect`` action) → store ``typed_edges``.
 * - Track the currently-selected node via
 *   :func:`useGraphStore.set_selected_node_id`.
 */

import type { DragEvent } from "react";
import { useCallback, useMemo, useRef } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type EdgeTypes,
  type NodeTypes,
} from "reactflow";

import "reactflow/dist/style.css";

import { UnitAwareEdge } from "@/flow_editor/edges/unit_aware_edge";
import { BaseEdge } from "@/flow_editor/model/base_edge";
import { BaseNode } from "@/flow_editor/model/base_node";
import "@/flow_editor/model/register";
import { NODE_TYPE_DRAG_MIME_TYPE } from "@/flow_editor/palette/NodePalette";
import { buildNodeTypesRegistry } from "@/flow_editor/nodes/node_types_registry";
import { useNodeTypes } from "@/hooks/use_node_types";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

function generateNodeId(type_id: string): string {
  const random_suffix = Math.random().toString(36).slice(2, 9);
  return `${type_id}_${random_suffix}`;
}

const EDGE_TYPES: EdgeTypes = {
  unit_aware: UnitAwareEdge,
};

const DEFAULT_EDGE_OPTIONS = {
  type: "unit_aware",
  markerEnd: { type: MarkerType.ArrowClosed },
};

function FlowCanvasInner(): JSX.Element {
  const node_types_query = useNodeTypes();

  const nodes = useGraphStore((state) => state.nodes);
  const edges = useGraphStore((state) => state.edges);
  const on_nodes_change = useGraphStore((state) => state.on_nodes_change);
  const on_edges_change = useGraphStore((state) => state.on_edges_change);
  const on_connect = useGraphStore((state) => state.on_connect);
  const add_typed_node = useGraphStore((state) => state.add_typed_node);
  const set_selected_node_id = useGraphStore(
    (state) => state.set_selected_node_id,
  );
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const react_flow_instance = useReactFlow();
  const wrapper_ref = useRef<HTMLDivElement | null>(null);

  const node_types: NodeTypes = useMemo(buildNodeTypesRegistry, []);

  const is_connection_valid = useCallback(
    (connection: Connection): boolean => {
      const new_edge = BaseEdge.from_connection(connection);
      if (new_edge === null) {
        return false;
      }
      const typed_nodes = useGraphStore.getState().typed_nodes;
      const source_node = typed_nodes.find(
        (candidate) => candidate.id === connection.source,
      );
      const target_node = typed_nodes.find(
        (candidate) => candidate.id === connection.target,
      );
      if (!source_node || !target_node) {
        return false;
      }
      const error_message = new_edge.validate(source_node, target_node);
      if (error_message !== null) {
        console.warn(error_message);
        return false;
      }
      return true;
    },
    [],
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
      let new_node;
      try {
        new_node = BaseNode.from_palette(
          entry.id,
          generateNodeId(entry.id),
          drop_position,
        );
      } catch (caught_error) {
        console.warn(
          `Cannot drop node of type ${entry.id}: ${
            caught_error instanceof Error ? caught_error.message : String(caught_error)
          }`,
        );
        return;
      }
      add_typed_node(new_node);
      set_dirty(true);
    },
    [node_types_query.data, react_flow_instance, add_typed_node, set_dirty],
  );

  const on_drag_over = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const on_selection_change = useCallback(
    ({ nodes: selected_nodes }: { nodes: GraphNode[] }) => {
      const current_selected = useGraphStore.getState().selected_node_id;
      if (selected_nodes.length === 0 && current_selected !== null) {
        const still_exists = useGraphStore.getState().typed_nodes.some(
          (n) => n.id === current_selected,
        );
        if (still_exists) return;
      }
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
        connectionMode={ConnectionMode.Loose}
        connectionRadius={20}
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
