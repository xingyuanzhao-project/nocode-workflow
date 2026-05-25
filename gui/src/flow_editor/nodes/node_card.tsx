/**
 * Shared visual chrome for every custom React Flow node.
 *
 * Keeps the card layout (category caption, title, handle positions)
 * consistent across node types so the per-type components focus on
 * their domain-specific summary.
 */

import type { ReactNode } from "react";
import { Handle, Position } from "reactflow";

import { cn } from "@/lib/utils";

export interface NodeCardProps {
  /** Category shown as a small mono caption above the title. */
  category: string;
  /** Title line. Usually the node-type ``label``. */
  title: string;
  /** ``node_type_id`` rendered under the title. */
  type_id: string;
  /** Domain-specific summary rendered as the card body. */
  children?: ReactNode;
  /** React Flow selection flag. */
  selected?: boolean;
  /** Toggle the input (target) handle on the card's left edge. */
  has_input_handle?: boolean;
  /** Position of the input (target) handle. Defaults to ``Left``. */
  input_handle_position?: Position;
  /** Toggle the output (source) handle on the card's right edge. */
  has_output_handle?: boolean;
  /**
   * Add a source handle at the card's top edge (id: ``llm-out``).
   * Used by processor nodes for the processor → LLM Call edge.
   */
  has_top_handle?: boolean;
  /**
   * Add a source handle at the card's bottom edge (id: ``cb-out``).
   * Used by processor nodes for the processor → Codebook edge.
   */
  has_bottom_handle?: boolean;
  /** Optional extra class names on the outer card wrapper. */
  class_name?: string;
}

/**
 * Card-style React Flow node with input/output handles and slots
 * for a per-type body.
 */
export function NodeCard({
  category,
  title,
  type_id: _type_id,
  children,
  selected = false,
  has_input_handle = true,
  input_handle_position = Position.Left,
  has_output_handle = true,
  has_top_handle = false,
  has_bottom_handle = false,
  class_name,
}: NodeCardProps): JSX.Element {
  return (
    <div
      className={cn(
        "min-w-[12rem] max-w-[16rem] rounded-md border bg-card px-3 py-2 shadow-sm",
        selected && "ring-2 ring-ring",
        class_name,
      )}
    >
      <div className="text-[0.65rem] font-mono uppercase tracking-wide text-muted-foreground">
        {category}
      </div>
      <div className="text-sm font-medium">{title}</div>
      {children ? <div className="mt-2 text-xs">{children}</div> : null}
      {has_input_handle ? (
        <Handle
          type="target"
          id="data-in"
          position={input_handle_position}
          className="!bg-foreground !w-3 !h-3"
        />
      ) : null}
      {has_output_handle ? (
        <Handle
          type="source"
          id="data-out"
          position={Position.Right}
          className="!bg-foreground !w-3 !h-3"
        />
      ) : null}
      {has_top_handle ? (
        <Handle
          type="source"
          id="llm-out"
          position={Position.Top}
          className="!bg-foreground !w-3 !h-3"
        />
      ) : null}
      {has_bottom_handle ? (
        <Handle
          type="source"
          id="cb-out"
          position={Position.Bottom}
          className="!bg-foreground !w-3 !h-3"
        />
      ) : null}
    </div>
  );
}
