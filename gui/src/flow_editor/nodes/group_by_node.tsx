/**
 * Canvas node declaring the entity-grouping step.
 *
 * The underlying flow schema expresses grouping on
 * :attr:`src.flow_loader.StepConfig.group_by` rather than on a
 * standalone step, but the GUI exposes it as a first-class node to
 * keep the canvas readable. The codec collapses this node into the
 * ``group_by: entity`` fields on the downstream processing steps.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface GroupByNodeData {
  node_type_id: "group_by";
  label: string;
  category: "data";
  /** Entity column name used for grouping. */
  entity_column: string;
  /** Sort-within-entity column name. */
  sort_by_column: string;
  /** Informational entity-count estimate from the latest upload. */
  entity_count_estimate: number | null;
  /** Informational average-documents-per-entity estimate. */
  avg_documents_per_entity: number | null;
}

export function GroupByNode({
  data,
  selected,
}: NodeProps<GroupByNodeData>): JSX.Element {
  return (
    <NodeCard
      category="Group By"
      title={data.label}
      selected={selected}
    >
      <div className="flex flex-col gap-0.5">
        <span>
          Entity: <span className="font-mono">{data.entity_column || "—"}</span>
        </span>
        <span>
          Sort by:{" "}
          <span className="font-mono">{data.sort_by_column || "—"}</span>
        </span>
        {data.entity_count_estimate !== null ? (
          <span className="text-muted-foreground">
            {data.entity_count_estimate.toLocaleString()} entities · avg{" "}
            {data.avg_documents_per_entity?.toFixed(1) ?? "?"} docs/entity
          </span>
        ) : null}
      </div>
    </NodeCard>
  );
}
