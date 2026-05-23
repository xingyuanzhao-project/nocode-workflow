/**
 * Zustand store for the React Flow graph editor.
 *
 * The flow editor was rebuilt around an explicit graph: the store now
 * holds typed :class:`BaseNode` and :class:`BaseEdge` instances as the
 * authoritative state, and exposes the matching React Flow ``Node[]`` /
 * ``Edge[]`` shapes as derived fields the canvas + property panel read.
 *
 * Mutations always go through the typed objects:
 *
 * - Palette drop → :meth:`BaseNode.from_palette` → ``add_node``.
 * - User draws a wire → :meth:`BaseEdge.from_connection` → ``on_connect``.
 * - Property panel form change → ``update_node_data`` → typed
 *   :meth:`BaseNode.patch_config`.
 * - React Flow position/remove change → translated into typed
 *   mutations by ``on_nodes_change`` / ``on_edges_change``.
 *
 * The temporal middleware (zundo) wraps the slice so undo/redo restores
 * past typed states; equality uses each typed object's serialised form
 * so class identity does not skew the comparison.
 */

import type {
  Connection,
  Edge as ReactFlowEdge,
  EdgeChange,
  Node as ReactFlowNode,
  NodeChange,
} from "reactflow";
import { applyNodeChanges } from "reactflow";
import { temporal, type TemporalState } from "zundo";
import {
  create,
  useStore,
  type StoreApi,
  type UseBoundStore,
} from "zustand";

import { BaseEdge } from "@/flow_editor/model/base_edge";
import { BaseNode } from "@/flow_editor/model/base_node";

import "@/flow_editor/model/register";

/**
 * A React Flow node carrying one of our domain-specific ``data``
 * payloads. ``data`` is kept as an open record here and narrowed by
 * the per-node-type component when it reads its own fields.
 */
export type GraphNode = ReactFlowNode<Record<string, unknown>>;

/** A React Flow edge; the default ``data`` shape is sufficient. */
export type GraphEdge = ReactFlowEdge;

export interface GraphState {
  /** Typed nodes — authoritative source of truth. */
  typed_nodes: BaseNode[];
  /** Typed edges — authoritative source of truth. */
  typed_edges: BaseEdge[];

  /** React Flow projection of :attr:`typed_nodes`. Kept in sync on every mutation. */
  nodes: GraphNode[];
  /** React Flow projection of :attr:`typed_edges`. Kept in sync on every mutation. */
  edges: GraphEdge[];

  /** Id of the node whose Property Panel is currently visible. */
  selected_node_id: string | null;

  /** Replace the full graph at once (used by the deserialiser on load). */
  set_graph: (typed_nodes: BaseNode[], typed_edges: BaseEdge[]) => void;
  /** Reset to an empty canvas. */
  clear_graph: () => void;

  /** React Flow ``onNodesChange`` handler. */
  on_nodes_change: (changes: NodeChange[]) => void;
  /** React Flow ``onEdgesChange`` handler. */
  on_edges_change: (changes: EdgeChange[]) => void;
  /** React Flow ``onConnect`` handler. */
  on_connect: (connection: Connection) => void;

  /** Append one typed node to the graph (used when dragging from the palette). */
  add_typed_node: (node: BaseNode) => void;
  /** Append one typed edge to the graph (used by tests and by the deserialiser). */
  add_typed_edge: (edge: BaseEdge) => void;

  /** Merge a partial config patch into one typed node and rebuild its data payload. */
  update_node_data: (
    node_id: string,
    data_patch: Record<string, unknown>,
  ) => void;

  /** Look up a typed node by id. */
  get_typed_node: (node_id: string) => BaseNode | null;

  /** Select the node whose Property Panel should be visible. */
  set_selected_node_id: (node_id: string | null) => void;
}

function project_react_flow_nodes(typed_nodes: BaseNode[]): GraphNode[] {
  return typed_nodes.map((typed_node) => typed_node.to_react_flow_node());
}

function project_react_flow_edges(typed_edges: BaseEdge[]): GraphEdge[] {
  return typed_edges.map((typed_edge) => typed_edge.to_react_flow_edge());
}

/**
 * Apply React Flow ``NodeChange[]`` events back onto the typed-node
 * array. We only translate the change kinds that affect the canonical
 * model:
 *
 * - ``position`` → mutate ``typed_node.position``.
 * - ``remove`` → drop the typed node and any incident typed edges.
 *
 * Everything else (``select``, ``dimensions``, ``add``) is handled at
 * the React Flow projection layer and then re-projected.
 */
function apply_changes_to_typed_nodes(
  typed_nodes: BaseNode[],
  changes: NodeChange[],
): {
  typed_nodes: BaseNode[];
  removed_ids: Set<string>;
} {
  const removed_ids = new Set<string>();
  for (const change of changes) {
    if (change.type === "remove") {
      removed_ids.add(change.id);
    } else if (change.type === "position" && change.position) {
      const target = typed_nodes.find(
        (candidate) => candidate.id === change.id,
      );
      if (target) {
        target.position = { x: change.position.x, y: change.position.y };
      }
    }
  }
  if (removed_ids.size === 0) {
    return { typed_nodes, removed_ids };
  }
  return {
    typed_nodes: typed_nodes.filter((node) => !removed_ids.has(node.id)),
    removed_ids,
  };
}

function apply_changes_to_typed_edges(
  typed_edges: BaseEdge[],
  changes: EdgeChange[],
  removed_node_ids: Set<string>,
): BaseEdge[] {
  const removed_edge_ids = new Set<string>();
  for (const change of changes) {
    if (change.type === "remove") {
      removed_edge_ids.add(change.id);
    }
  }
  if (removed_edge_ids.size === 0 && removed_node_ids.size === 0) {
    return typed_edges;
  }
  return typed_edges.filter((edge) => {
    if (removed_edge_ids.has(edge.id)) {
      return false;
    }
    if (
      removed_node_ids.has(edge.source_node_id) ||
      removed_node_ids.has(edge.target_node_id)
    ) {
      return false;
    }
    return true;
  });
}

/**
 * Domain-aware equality for the temporal middleware.
 *
 * React Flow fires one change event per mouse-move while dragging, which
 * would otherwise flood the undo stack. Excluding ``position`` from the
 * tracked diff means drag gestures do not create undo entries; edits
 * that matter (add/remove nodes, add/remove edges, update config) still
 * do.
 */
const TYPED_EQUALITY_IGNORE_DRAG = true;

function summarise_typed_node(node: BaseNode): string {
  const config_json = JSON.stringify(node.emit_config());
  const position_part = TYPED_EQUALITY_IGNORE_DRAG
    ? ""
    : `:${node.position.x},${node.position.y}`;
  return `${node.id}:${node.node_type}${position_part}:${config_json}`;
}

function summarise_typed_edge(edge: BaseEdge): string {
  return `${edge.edge_type}:${edge.source_node_id}:${edge.target_node_id}`;
}

function are_graph_states_equivalent(
  previous: GraphState,
  next: GraphState,
): boolean {
  if (previous.selected_node_id !== next.selected_node_id) {
    return false;
  }
  if (previous.typed_nodes.length !== next.typed_nodes.length) {
    return false;
  }
  if (previous.typed_edges.length !== next.typed_edges.length) {
    return false;
  }
  for (let index = 0; index < previous.typed_nodes.length; index += 1) {
    if (
      summarise_typed_node(previous.typed_nodes[index]!) !==
      summarise_typed_node(next.typed_nodes[index]!)
    ) {
      return false;
    }
  }
  for (let index = 0; index < previous.typed_edges.length; index += 1) {
    if (
      summarise_typed_edge(previous.typed_edges[index]!) !==
      summarise_typed_edge(next.typed_edges[index]!)
    ) {
      return false;
    }
  }
  return true;
}

/**
 * Zustand + zundo store for the React Flow canvas.
 *
 * Exposes typed state, the React Flow projection, the React Flow change
 * handlers, and a handful of domain-specific helpers (``add_typed_node``,
 * ``update_node_data``). Undo/redo is available under
 * ``useGraphStore.temporal``.
 */
export const useGraphStore: UseBoundStore<StoreApi<GraphState>> & {
  temporal: StoreApi<TemporalState<GraphState>>;
} = create<GraphState>()(
  temporal(
    (set, get) => ({
      typed_nodes: [],
      typed_edges: [],
      nodes: [],
      edges: [],
      selected_node_id: null,

      set_graph: (typed_nodes, typed_edges) =>
        set({
          typed_nodes,
          typed_edges,
          nodes: project_react_flow_nodes(typed_nodes),
          edges: project_react_flow_edges(typed_edges),
        }),

      clear_graph: () =>
        set({
          typed_nodes: [],
          typed_edges: [],
          nodes: [],
          edges: [],
          selected_node_id: null,
        }),

      on_nodes_change: (changes) =>
        set((state) => {
          const { typed_nodes: next_typed_nodes, removed_ids } =
            apply_changes_to_typed_nodes(state.typed_nodes, changes);
          const next_typed_edges =
            removed_ids.size > 0
              ? state.typed_edges.filter(
                  (edge) =>
                    !removed_ids.has(edge.source_node_id) &&
                    !removed_ids.has(edge.target_node_id),
                )
              : state.typed_edges;
          return {
            typed_nodes: next_typed_nodes,
            typed_edges: next_typed_edges,
            nodes: applyNodeChanges(changes, state.nodes) as GraphNode[],
            edges:
              next_typed_edges === state.typed_edges
                ? state.edges
                : project_react_flow_edges(next_typed_edges),
          };
        }),

      on_edges_change: (changes) =>
        set((state) => {
          const next_typed_edges = apply_changes_to_typed_edges(
            state.typed_edges,
            changes,
            new Set(),
          );
          return {
            typed_edges: next_typed_edges,
            edges: project_react_flow_edges(next_typed_edges),
          };
        }),

      on_connect: (connection) =>
        set((state) => {
          const new_edge = BaseEdge.from_connection(connection);
          if (new_edge === null) {
            return {};
          }
          const source_node = state.typed_nodes.find(
            (candidate) => candidate.id === new_edge.source_node_id,
          );
          const target_node = state.typed_nodes.find(
            (candidate) => candidate.id === new_edge.target_node_id,
          );
          if (!source_node || !target_node) {
            return {};
          }
          const error_message = new_edge.validate(source_node, target_node);
          if (error_message !== null) {
            console.warn(error_message);
            return {};
          }
          const duplicate_index = state.typed_edges.findIndex(
            (existing) => existing.id === new_edge.id,
          );
          const next_typed_edges =
            duplicate_index === -1
              ? [...state.typed_edges, new_edge]
              : state.typed_edges;
          return {
            typed_edges: next_typed_edges,
            edges: project_react_flow_edges(next_typed_edges),
          };
        }),

      add_typed_node: (node) =>
        set((state) => {
          const next_typed_nodes = [...state.typed_nodes, node];
          return {
            typed_nodes: next_typed_nodes,
            nodes: project_react_flow_nodes(next_typed_nodes),
          };
        }),

      add_typed_edge: (edge) =>
        set((state) => {
          const next_typed_edges = [...state.typed_edges, edge];
          return {
            typed_edges: next_typed_edges,
            edges: project_react_flow_edges(next_typed_edges),
          };
        }),

      update_node_data: (node_id, data_patch) =>
        set((state) => {
          const target = state.typed_nodes.find(
            (candidate) => candidate.id === node_id,
          );
          if (!target) {
            return {};
          }
          target.patch_config(data_patch);
          const next_typed_nodes = [...state.typed_nodes];
          return {
            typed_nodes: next_typed_nodes,
            nodes: project_react_flow_nodes(next_typed_nodes),
          };
        }),

      get_typed_node: (node_id) => {
        const state = get();
        return (
          state.typed_nodes.find(
            (candidate) => candidate.id === node_id,
          ) ?? null
        );
      },

      set_selected_node_id: (node_id) => set({ selected_node_id: node_id }),
    }),
    {
      equality: are_graph_states_equivalent,
      limit: 100,
    },
  ),
) as UseBoundStore<StoreApi<GraphState>> & {
  temporal: StoreApi<TemporalState<GraphState>>;
};

/**
 * Convenience hook for the undo/redo controls.
 */
export function useGraphHistory(): {
  undo: () => void;
  redo: () => void;
  clear_history: () => void;
  can_undo: boolean;
  can_redo: boolean;
} {
  const past_states_length = useStore(
    useGraphStore.temporal,
    (state: TemporalState<GraphState>) => state.pastStates.length,
  );
  const future_states_length = useStore(
    useGraphStore.temporal,
    (state: TemporalState<GraphState>) => state.futureStates.length,
  );
  return {
    undo: () => useGraphStore.temporal.getState().undo(),
    redo: () => useGraphStore.temporal.getState().redo(),
    clear_history: () => useGraphStore.temporal.getState().clear(),
    can_undo: past_states_length > 0,
    can_redo: future_states_length > 0,
  };
}
