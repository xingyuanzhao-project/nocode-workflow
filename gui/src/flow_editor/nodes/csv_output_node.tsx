/**
 * Canvas node for the output-CSV sink.
 *
 * Summarises which artifact CSVs the run will emit (summary, results,
 * states, spans) and whether ``extend`` is enabled. The codec
 * translates this node into :class:`src.flow_loader.OutputConfig`.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface CSVOutputNodeData {
  node_type_id: "csv_output";
  label: string;
  category: "data";
  /** Relative POSIX path of the summary CSV (required). */
  summary_csv: string;
  /** Optional relative POSIX path of results.csv. */
  results_csv: string | null;
  /** Optional relative POSIX path of states.csv. */
  states_csv: string | null;
  /** Optional relative POSIX path of spans.csv. */
  spans_csv: string | null;
  /** Append-to-existing flag. */
  extend: boolean;
}

const ARTIFACT_FIELD_LABELS: readonly { key: keyof CSVOutputNodeData; label: string }[] = [
  { key: "summary_csv", label: "summary.csv" },
  { key: "results_csv", label: "results.csv" },
  { key: "states_csv", label: "states.csv" },
  { key: "spans_csv", label: "spans.csv" },
];

export function CSVOutputNode({
  data,
  selected,
}: NodeProps<CSVOutputNodeData>): JSX.Element {
  const enabled_count = ARTIFACT_FIELD_LABELS.filter((field) => {
    const value = data[field.key];
    return typeof value === "string" && value.length > 0;
  }).length;
  return (
    <NodeCard
      category="Output"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_output_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        <span>
          {enabled_count}/{ARTIFACT_FIELD_LABELS.length} artifacts enabled
        </span>
        <span className="text-muted-foreground">
          {data.extend ? "Append (extend=true)" : "Overwrite"}
        </span>
      </div>
    </NodeCard>
  );
}
