/**
 * Abstract base class for every typed edge in the flow graph.
 *
 * An edge is a first-class relationship between two nodes — not a
 * decorative line. Persisted shape ``{ type, source, target }`` is read
 * by both the React Flow canvas and the Python backend, so what the user
 * draws is what runs.
 *
 * Three concrete subclasses live under ``model/edges/``:
 *
 * - :class:`FeedforwardEdge` — data flow between adjacent processors
 *   (and from the input node to the first processor, and from the last
 *   processor to the output node).
 * - :class:`LLMCallEdge` — a processor calls a specific LLM resource.
 * - :class:`CodebookInquiryEdge` — a processor consults a specific
 *   codebook (a.k.a. taxonomy) resource.
 *
 * The edge's ``edge_type`` discriminator is fixed at the subclass level
 * and round-trips through the YAML untouched. The handle ids the edge
 * attaches to on each endpoint are derived from the edge type, NOT
 * stored in the YAML — drawing logic is reproducible from the type alone.
 */

import type { Edge as ReactFlowEdge, Connection } from "reactflow";
import { MarkerType } from "reactflow";

import type { BaseNode } from "./base_node";

/** Plain shape used when an edge round-trips through YAML / network. */
export interface SerializedEdge {
  type: string;
  source: string;
  target: string;
}

/**
 * Constructor signature every concrete edge subclass exposes. The
 * registry uses this to instantiate without importing the subclass.
 */
type BaseEdgeConstructor = new (
  source_node_id: string,
  target_node_id: string,
) => BaseEdge;

const EDGE_REGISTRY: Map<string, BaseEdgeConstructor> = new Map();

/**
 * Mapping from a source ``Connection.sourceHandle`` produced by React
 * Flow to the edge type that handle implies. Populated at registration
 * time by each subclass's :meth:`BaseEdge.register_for_handle` call so
 * the user-drawn edge case stays declarative.
 *
 * Special key ``__default__`` covers the unnamed right-edge handle on a
 * processor's output side (it is rendered without an id, so React Flow
 * sends ``sourceHandle: null``).
 */
const HANDLE_TO_EDGE_TYPE: Map<string, string> = new Map();

const DEFAULT_HANDLE_KEY = "__default__";

/** Generate a stable, human-readable id for an edge. */
function build_edge_id(type: string, source: string, target: string): string {
  return `${type}__${source}__${target}`;
}

/**
 * Abstract typed edge. Concrete subclasses live under ``model/edges/``.
 *
 * Subclasses MUST:
 * - Set :attr:`edge_type` to the discriminator string used in YAML.
 * - Set :attr:`source_handle` and :attr:`target_handle` to the handle ids
 *   on each endpoint that this edge attaches to (``null`` means "default
 *   unnamed handle on that side").
 * - Set :attr:`source_handle_for_drawing` to the source handle this edge
 *   is created from when the user drags a wire (``null`` for the default
 *   right-edge handle).
 * - Implement :meth:`validate` to check the source and target node types
 *   are compatible.
 */
export abstract class BaseEdge {
  readonly id: string;
  readonly source_node_id: string;
  readonly target_node_id: string;

  /** Discriminator string. Same value used in YAML ``edges[*].type``. */
  abstract readonly edge_type: string;

  /**
   * React Flow handle id on the source endpoint. ``null`` means the
   * default unnamed source handle (typically the right edge of the node).
   */
  abstract readonly source_handle: string | null;

  /**
   * React Flow handle id on the target endpoint. ``null`` means the
   * default unnamed target handle (typically the left edge of the node).
   */
  abstract readonly target_handle: string | null;

  /** Whether the React Flow rendering should show a closed arrow head. */
  abstract readonly has_arrow: boolean;

  /** Whether to also show an arrow at the source end (bidirectional). */
  readonly has_start_arrow: boolean = false;

  protected constructor(
    edge_type_literal: string,
    source_node_id: string,
    target_node_id: string,
  ) {
    this.source_node_id = source_node_id;
    this.target_node_id = target_node_id;
    this.id = build_edge_id(edge_type_literal, source_node_id, target_node_id);
  }

  /**
   * Register a concrete subclass under its ``edge_type`` discriminator.
   *
   * Optionally also bind the source-side handle id this edge is drawn
   * FROM so :meth:`BaseEdge.from_connection` can resolve the type when
   * the user drags a wire on the canvas. Pass ``null`` for the default
   * unnamed source handle (right edge).
   */
  static register(
    type: string,
    ctor: BaseEdgeConstructor,
    drawn_from_source_handle: string | null,
  ): void {
    EDGE_REGISTRY.set(type, ctor);
    const handle_key =
      drawn_from_source_handle === null
        ? DEFAULT_HANDLE_KEY
        : drawn_from_source_handle;
    HANDLE_TO_EDGE_TYPE.set(handle_key, type);
  }

  /**
   * Construct a typed edge from one ``{ type, source, target }`` YAML
   * entry. Throws when the discriminator has no registered constructor.
   */
  static from_yaml(entry: SerializedEdge): BaseEdge {
    const ctor = EDGE_REGISTRY.get(entry.type);
    if (!ctor) {
      throw new Error(
        `Unknown edge type ${JSON.stringify(entry.type)}. Registered: ` +
          `${Array.from(EDGE_REGISTRY.keys()).join(", ")}`,
      );
    }
    return new ctor(entry.source, entry.target);
  }

  /**
   * Construct a typed edge from a React Flow ``Connection`` (the object
   * passed to ``onConnect``). The ``sourceHandle`` field decides which
   * subclass to instantiate — see :data:`HANDLE_TO_EDGE_TYPE`.
   *
   * Returns ``null`` when ``connection.source`` or ``connection.target``
   * is missing, OR when the source handle has no edge type bound to it
   * (which means the connection is invalid in this graph).
   */
  static from_connection(connection: Connection): BaseEdge | null {
    const { source, target, sourceHandle } = connection;
    if (source === null || target === null) {
      return null;
    }
    const handle_key =
      sourceHandle === null || sourceHandle === undefined
        ? DEFAULT_HANDLE_KEY
        : sourceHandle;
    const edge_type = HANDLE_TO_EDGE_TYPE.get(handle_key);
    if (!edge_type) {
      return null;
    }
    const ctor = EDGE_REGISTRY.get(edge_type);
    if (!ctor) {
      return null;
    }
    return new ctor(source, target);
  }

  /**
   * Verify that the edge's source and target nodes have compatible types
   * (and units, for feedforward). Returns ``null`` when valid or a short
   * human-readable message when not.
   */
  abstract validate(source_node: BaseNode, target_node: BaseNode): string | null;

  /** Turn the edge into a YAML-ready ``{ type, source, target }`` entry. */
  serialize(): SerializedEdge {
    return {
      type: this.edge_type,
      source: this.source_node_id,
      target: this.target_node_id,
    };
  }

  /** Turn the edge into a React Flow ``Edge`` ready for ``<ReactFlow>``. */
  to_react_flow_edge(): ReactFlowEdge {
    return {
      id: this.id,
      source: this.source_node_id,
      target: this.target_node_id,
      sourceHandle: this.source_handle ?? undefined,
      targetHandle: this.target_handle ?? undefined,
      type: "unit_aware",
      data: { edge_type: this.edge_type },
      markerStart: this.has_start_arrow ? { type: MarkerType.ArrowClosed } : undefined,
      markerEnd: this.has_arrow ? { type: MarkerType.ArrowClosed } : undefined,
    };
  }
}

/** Read-only view of the registered ``edge_type`` strings. */
export function registered_edge_types(): string[] {
  return Array.from(EDGE_REGISTRY.keys());
}
