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
  /** Toggle the output (source) handle on the card's right edge. */
  has_output_handle?: boolean;
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
  type_id,
  children,
  selected = false,
  has_input_handle = true,
  has_output_handle = true,
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
      <div className="text-[0.7rem] text-muted-foreground">{type_id}</div>
      {children ? <div className="mt-2 text-xs">{children}</div> : null}
      {has_input_handle ? (
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-foreground"
        />
      ) : null}
      {has_output_handle ? (
        <Handle
          type="source"
          position={Position.Right}
          className="!bg-foreground"
        />
      ) : null}
    </div>
  );
}
