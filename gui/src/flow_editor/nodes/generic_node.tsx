/**
 * Fallback node component used until per-type components are built.
 *
 * Renders a simple card with the node's ``label`` and
 * ``node_type_id`` plus input/output handles so edges can be drawn.
 * The `gui_custom_nodes` step replaces individual entries in
 * :mod:`@/flow_editor/nodes/node_types_registry` with specialised
 * components; this one stays as the default fallback for any
 * node-type id the registry does not map explicitly.
 */

import { Handle, Position, type NodeProps } from "reactflow";

export interface GenericNodeData {
  /** ``NodeTypeEntry.id``; shown as a mono caption. */
  node_type_id: string;
  /** ``NodeTypeEntry.label``; shown as the card title. */
  label: string;
  /** ``NodeTypeEntry.category`` for colour-coding later. */
  category: string;
}

export function GenericNode({
  data,
  selected,
}: NodeProps<GenericNodeData>): JSX.Element {
  return (
    <div
      className={
        "min-w-[10rem] rounded-md border bg-card px-3 py-2 shadow-sm " +
        (selected ? "ring-2 ring-ring" : "")
      }
    >
      <div className="text-[0.65rem] font-mono uppercase tracking-wide text-muted-foreground">
        {data.category}
      </div>
      <div className="mt-0.5 text-sm font-medium">{data.label}</div>
      <div className="text-xs text-muted-foreground">{data.node_type_id}</div>
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-foreground"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-foreground"
      />
    </div>
  );
}
