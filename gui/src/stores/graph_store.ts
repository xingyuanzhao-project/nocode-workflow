/**
 * Zustand store for the React Flow graph editor.
 *
 * Holds the canvas nodes, edges, and the identifier of the currently
 * selected node. The entire slice is wrapped in the ``zundo``
 * temporal middleware so the user can undo/redo edits via
 * ``useGraphStore.temporal.getState().undo()`` / ``.redo()``.
 *
 * The store is intentionally thin: the React Flow handlers
 * (``onNodesChange``, ``onEdgesChange``, ``onConnect``) call the
 * setters below, and the custom node components read/write their own
 * ``data`` payload via :func:`updateNodeData`.
 */

import type {
  Connection,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
} from "reactflow";
import { addEdge, applyEdgeChanges, applyNodeChanges } from "reactflow";
import { temporal, type TemporalState } from "zundo";
import {
  create,
  useStore,
  type StoreApi,
  type UseBoundStore,
} from "zustand";

/**
 * A React Flow node carrying one of our domain-specific ``data``
 * payloads. ``data`` is kept as an open record here and narrowed by
 * the per-node-type component when it reads its own fields.
 */
export type GraphNode = Node<Record<string, unknown>>;

/** A React Flow edge; the default ``data`` shape is sufficient. */
export type GraphEdge = Edge;

export interface GraphState {
  /** Canvas nodes in insertion order. */
  nodes: GraphNode[];
  /** Canvas edges in insertion order. */
  edges: GraphEdge[];
  /** Id of the node whose Property Panel is currently visible. */
  selected_node_id: string | null;

  /** Replace the full graph at once (used by the codec on load). */
  set_graph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  /** Reset to an empty canvas. */
  clear_graph: () => void;

  /** React Flow ``onNodesChange`` handler. */
  on_nodes_change: (changes: NodeChange[]) => void;
  /** React Flow ``onEdgesChange`` handler. */
  on_edges_change: (changes: EdgeChange[]) => void;
  /** React Flow ``onConnect`` handler. */
  on_connect: (connection: Connection) => void;

  /** Append one node to the graph (used when dragging from the palette). */
  add_node: (node: GraphNode) => void;
  /** Merge a partial ``data`` patch into one node. */
  update_node_data: (
    node_id: string,
    data_patch: Record<string, unknown>,
  ) => void;

  /** Select the node whose Property Panel should be visible. */
  set_selected_node_id: (node_id: string | null) => void;
}

/**
 * Domain-aware overrides for zundo's default change detection.
 *
 * React Flow fires one change event per mouse-move while dragging,
 * which would otherwise flood the undo stack. Excluding the
 * ``position`` and ``selected`` fields from the tracked diff means
 * drag gestures do not create undo-stack entries; edits that matter
 * (add/remove nodes, add/remove edges, update ``data``) still do.
 *
 * ``width`` and ``height`` are written onto each node by React Flow's
 * internal ``ResizeObserver`` after it measures the rendered DOM.
 * They must also be ignored here, otherwise every ``undo()`` call
 * restores a node with no measured size, the ResizeObserver fires,
 * the store sees a "new" state, zundo clears ``futureStates``, and
 * the undo stack becomes undrainable. See tests/e2e/07_undo_redo.
 */
const TEMPORAL_EQUALITY_IGNORED_FIELDS: ReadonlySet<string> = new Set([
  "position",
  "positionAbsolute",
  "selected",
  "dragging",
  "width",
  "height",
]);

function stripIgnoredNodeFields(node: GraphNode): Record<string, unknown> {
  const serialised: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node)) {
    if (TEMPORAL_EQUALITY_IGNORED_FIELDS.has(key)) {
      continue;
    }
    serialised[key] = value;
  }
  return serialised;
}

function areGraphStatesEquivalent(
  previous: GraphState,
  next: GraphState,
): boolean {
  if (previous.selected_node_id !== next.selected_node_id) {
    return false;
  }
  if (previous.nodes.length !== next.nodes.length) {
    return false;
  }
  if (previous.edges.length !== next.edges.length) {
    return false;
  }
  for (let index = 0; index < previous.nodes.length; index += 1) {
    const prev_stripped = stripIgnoredNodeFields(previous.nodes[index]!);
    const next_stripped = stripIgnoredNodeFields(next.nodes[index]!);
    if (JSON.stringify(prev_stripped) !== JSON.stringify(next_stripped)) {
      return false;
    }
  }
  for (let index = 0; index < previous.edges.length; index += 1) {
    if (
      JSON.stringify(previous.edges[index]) !==
      JSON.stringify(next.edges[index])
    ) {
      return false;
    }
  }
  return true;
}

/**
 * Zustand + zundo store for the React Flow canvas.
 *
 * Exposes the state, the React Flow change handlers, and a handful
 * of domain-specific helpers (``add_node``, ``update_node_data``).
 * Undo/redo is available under ``useGraphStore.temporal``.
 */
export const useGraphStore: UseBoundStore<StoreApi<GraphState>> & {
  temporal: StoreApi<TemporalState<GraphState>>;
} = create<GraphState>()(
  temporal(
    (set) => ({
      nodes: [],
      edges: [],
      selected_node_id: null,

      set_graph: (nodes, edges) => set({ nodes, edges }),
      clear_graph: () =>
        set({ nodes: [], edges: [], selected_node_id: null }),

      on_nodes_change: (changes) =>
        set((state) => ({
          nodes: applyNodeChanges(changes, state.nodes) as GraphNode[],
        })),
      on_edges_change: (changes) =>
        set((state) => ({
          edges: applyEdgeChanges(changes, state.edges),
        })),
      on_connect: (connection) =>
        set((state) => ({
          edges: addEdge(connection, state.edges),
        })),

      add_node: (node) =>
        set((state) => ({
          nodes: [...state.nodes, node],
        })),
      update_node_data: (node_id, data_patch) =>
        set((state) => ({
          nodes: state.nodes.map((node) =>
            node.id === node_id
              ? { ...node, data: { ...node.data, ...data_patch } }
              : node,
          ),
        })),

      set_selected_node_id: (node_id) => set({ selected_node_id: node_id }),
    }),
    {
      equality: areGraphStatesEquivalent,
      limit: 100,
    },
  ),
) as UseBoundStore<StoreApi<GraphState>> & {
  temporal: StoreApi<TemporalState<GraphState>>;
};

/**
 * Convenience hook for the undo/redo controls.
 *
 * Subscribes to the temporal store so buttons wired to ``undo`` /
 * ``redo`` re-render when the ``pastStates`` / ``futureStates`` arrays
 * change.
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
