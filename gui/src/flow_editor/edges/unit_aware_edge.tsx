/**
 * Custom React Flow edge that displays the upstream schema badge
 * and highlights invalid unit transitions in red.
 *
 * The unit of each endpoint is read from the connected node's
 * ``data.unit`` (processor nodes) or inferred from the node type
 * (data / resource nodes have no unit). Compatibility is checked
 * against :mod:`@/lib/unit_compatibility`.
 */

import type { EdgeProps } from "reactflow";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useNodes,
} from "reactflow";

import { cn } from "@/lib/utils";
import {
  isValidUnitTransition,
  type UnitValue,
} from "@/lib/unit_compatibility";

interface ConnectedNodeSummary {
  label: string;
  unit: UnitValue | null;
  category: string | null;
}

function readNodeSummary(
  nodes: Array<{ id: string; data?: Record<string, unknown> }>,
  node_id: string,
): ConnectedNodeSummary | null {
  const matching_node = nodes.find((candidate) => candidate.id === node_id);
  if (!matching_node) {
    return null;
  }
  const data = matching_node.data ?? {};
  const label_value =
    typeof data.label === "string"
      ? data.label
      : String(data.node_type_id ?? node_id);
  const unit_value = data.unit;
  const category_value = data.category;
  return {
    label: label_value,
    unit: unit_value === "row" ? "row" : null,
    category:
      typeof category_value === "string" ? category_value : null,
  };
}

export function UnitAwareEdge(props: EdgeProps): JSX.Element {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    source,
    target,
    markerEnd,
    markerStart,
    style,
  } = props;

  const [edge_path, label_x, label_y] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const nodes = useNodes();
  const source_summary = readNodeSummary(
    nodes as Array<{ id: string; data?: Record<string, unknown> }>,
    source,
  );
  const target_summary = readNodeSummary(
    nodes as Array<{ id: string; data?: Record<string, unknown> }>,
    target,
  );

  const source_unit = source_summary?.unit ?? null;
  const target_unit = target_summary?.unit ?? null;
  const is_invalid =
    source_unit !== null &&
    target_unit !== null &&
    !isValidUnitTransition(source_unit, target_unit);

  const badge_text =
    source_summary && target_summary
      ? `${source_summary.unit ?? source_summary.category ?? "?"} \u2192 ${
          target_summary.unit ?? target_summary.category ?? "?"
        }`
      : "";

  return (
    <>
      <BaseEdge
        id={id}
        path={edge_path}
        markerStart={markerStart}
        markerEnd={markerEnd}
        style={{
          ...style,
          stroke: is_invalid
            ? "hsl(var(--destructive))"
            : "hsl(var(--foreground))",
          strokeWidth: 1.75,
        }}
      />
      {badge_text ? (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "pointer-events-none absolute rounded-full border bg-background px-2 py-0.5 text-[0.65rem] font-mono",
              is_invalid
                ? "border-destructive text-destructive"
                : "border-border text-muted-foreground",
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${label_x}px, ${label_y}px)`,
            }}
          >
            {badge_text}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
