/**
 * Abstract base class for every typed node in the flow graph.
 *
 * The flow editor was refactored away from a flat ``Record<string, unknown>``
 * data payload into class-based node objects. Each subclass represents one
 * palette item (CSV input, processor, LLM call, codebook, CSV output, ...)
 * and owns:
 *
 * - Its own typed configuration fields (subclass-specific properties).
 * - The mapping to a React Flow ``Node`` shape via :meth:`to_react_flow_node`.
 * - The mapping to the on-disk YAML entry shape via :meth:`serialize`.
 * - Validation of its own configuration via :meth:`validate`.
 *
 * Construction goes through the static registry pattern — :meth:`register` is
 * called once per concrete subclass at module import (see
 * ``model/register.ts``); :meth:`from_yaml` and :meth:`from_palette`
 * dispatch on the ``type`` string to return the correct child instance.
 */

import type { Node as ReactFlowNode } from "reactflow";

/**
 * Categories shared with ``server/schemas/node_types.py``. Used to colour
 * the palette and pick the right Property-Panel form.
 */
export type NodeCategory = "data" | "processor" | "resource";

/** Visual position of the node on the canvas (mirrors React Flow). */
export interface NodePosition {
  x: number;
  y: number;
}

/**
 * Constructor signature every concrete node subclass must expose so the
 * registry can instantiate it without knowing its class.
 */
type BaseNodeConstructor = new (
  id: string,
  config?: Record<string, unknown>,
  position?: NodePosition,
) => BaseNode;

/**
 * Plain shape used when a node round-trips through YAML / network.
 *
 * Mirrors :class:`src.flow_loader.NodeEntry` on the backend.
 */
export interface SerializedNode {
  id: string;
  type: string;
  config: Record<string, unknown>;
}

const NODE_REGISTRY: Map<string, BaseNodeConstructor> = new Map();

/**
 * Abstract typed node. Concrete subclasses live under ``model/nodes/``.
 *
 * Subclasses MUST:
 * - Set :attr:`node_type` to the string used in YAML (``processor``,
 *   ``llm_call``, ``codebook``, ``csv_input``, ``csv_output``, ...).
 * - Implement :meth:`apply_config` to copy the YAML config into typed
 *   fields with sensible defaults for missing values.
 * - Implement :meth:`emit_config` to project the typed fields back into a
 *   plain JS object suitable for YAML.
 * - Implement :meth:`validate` to return ``null`` if the current config is
 *   valid or a human-readable error message otherwise.
 * - Implement :meth:`build_data_payload` to produce the ``data`` record the
 *   matching React Flow component expects.
 */
export abstract class BaseNode {
  readonly id: string;
  position: NodePosition;

  /** Discriminator string. Same value used in YAML ``nodes[*].type``. */
  abstract readonly node_type: string;
  /** Palette grouping. Drives the property panel dispatcher. */
  abstract readonly category: NodeCategory;
  /** Human label shown on the canvas card title. */
  abstract readonly label: string;

  protected constructor(id: string, position: NodePosition = { x: 0, y: 0 }) {
    this.id = id;
    this.position = position;
  }

  /**
   * Register a concrete subclass under its ``node_type`` discriminator so
   * :meth:`BaseNode.from_yaml` and :meth:`BaseNode.from_palette` can create
   * it without importing the subclass directly.
   */
  static register(type: string, ctor: BaseNodeConstructor): void {
    NODE_REGISTRY.set(type, ctor);
  }

  /**
   * Construct a typed node from one ``{ id, type, config }`` YAML entry.
   *
   * @throws Error if ``type`` has no registered constructor.
   */
  static from_yaml(entry: SerializedNode, position?: NodePosition): BaseNode {
    const ctor = NODE_REGISTRY.get(entry.type);
    if (!ctor) {
      throw new Error(
        `Unknown node type ${JSON.stringify(entry.type)}. Registered: ` +
          `${Array.from(NODE_REGISTRY.keys()).join(", ")}`,
      );
    }
    return new ctor(entry.id, entry.config ?? {}, position ?? { x: 0, y: 0 });
  }

  /**
   * Construct a typed node when the user drops a palette entry on the
   * canvas. The config starts empty; subclasses fill in their own defaults
   * inside their :meth:`apply_config` implementation.
   */
  static from_palette(
    type: string,
    id: string,
    position: NodePosition,
  ): BaseNode {
    const ctor = NODE_REGISTRY.get(type);
    if (!ctor) {
      throw new Error(
        `Unknown node type ${type}. Registered: ` +
          `${Array.from(NODE_REGISTRY.keys()).join(", ")}`,
      );
    }
    return new ctor(id, {}, position);
  }

  /**
   * Replace the node's config with the supplied values. Subclasses should
   * preserve unspecified fields by using their existing values as fallbacks.
   */
  abstract apply_config(config: Record<string, unknown>): void;

  /** Project the typed fields into a plain dict for YAML serialisation. */
  abstract emit_config(): Record<string, unknown>;

  /**
   * Return ``null`` when the current config is valid; otherwise a short
   * human-readable error string suitable for a toast or panel banner.
   */
  abstract validate(): string | null;

  /**
   * Build the ``data`` payload consumed by the React Flow component that
   * renders this node type. The shape mirrors the existing per-component
   * ``Data`` interfaces under ``flow_editor/nodes/`` so those components
   * keep working without a parallel rewrite.
   */
  protected abstract build_data_payload(): Record<string, unknown>;

  /**
   * Merge a partial patch from a Property-Panel form into the node's
   * config. Default behaviour is "current emit_config + patch -> apply",
   * which works for every subclass that respects its own field defaults.
   */
  patch_config(patch: Record<string, unknown>): void {
    const merged = { ...this.emit_config(), ...patch };
    this.apply_config(merged);
  }

  /** Turn the node into a YAML-ready ``{ id, type, config }`` entry. */
  serialize(): SerializedNode {
    return {
      id: this.id,
      type: this.node_type,
      config: this.emit_config(),
    };
  }

  /** Turn the node into a React Flow ``Node`` ready for ``<ReactFlow>``. */
  to_react_flow_node(): ReactFlowNode<Record<string, unknown>> {
    return {
      id: this.id,
      type: this.node_type,
      position: { x: this.position.x, y: this.position.y },
      data: this.build_data_payload(),
    };
  }
}

/**
 * Read-only view of the registered ``node_type`` strings. Used by the
 * canvas to build ReactFlow's ``nodeTypes`` map and by tests.
 */
export function registered_node_types(): string[] {
  return Array.from(NODE_REGISTRY.keys());
}
