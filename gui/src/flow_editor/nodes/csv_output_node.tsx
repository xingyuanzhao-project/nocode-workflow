/**
 * Canvas node for the output-CSV sink.
 *
 * Supports both the new model (output_path + artifact_paths) and the
 * legacy model (summary_csv / results_csv / states_csv / spans_csv).
 * The codec translates this node into :class:`src.flow_loader.OutputConfig`.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface CSVOutputNodeData {
  node_type_id: string;
  label: string;
  category: "data";
  // New model
  output_path?: string;
  artifact_paths?: string[];
  output_fields?: string[];
  // Old model
  summary_csv?: string;
  results_csv?: string | null;
  states_csv?: string | null;
  spans_csv?: string | null;
  extend?: boolean;
}

const ARTIFACT_FIELD_LABELS: readonly { key: string; label: string }[] = [
  { key: "summary_csv", label: "summary.csv" },
  { key: "results_csv", label: "results.csv" },
  { key: "states_csv", label: "states.csv" },
  { key: "spans_csv", label: "spans.csv" },
];

export function CSVOutputNode({
  data,
  selected,
}: NodeProps<CSVOutputNodeData>): JSX.Element {
  const has_new_model = typeof data.output_path === "string";

  return (
    <NodeCard
      category="Output"
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_output_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        {has_new_model ? (
          <>
            <span className="truncate font-mono" title={data.output_path}>
              {data.output_path || "— path unset —"}
            </span>
            {(data.output_fields?.length ?? 0) > 0 && (
              <span className="text-muted-foreground">
                Fields: {data.output_fields!.join(", ")}
              </span>
            )}
            {(data.artifact_paths?.length ?? 0) > 0 && (
              <span className="text-muted-foreground">
                +{data.artifact_paths!.length} artifact{data.artifact_paths!.length === 1 ? "" : "s"}
              </span>
            )}
          </>
        ) : (
          <>
            <span>
              {ARTIFACT_FIELD_LABELS.filter((f) => {
                const v = (data as Record<string, unknown>)[f.key];
                return typeof v === "string" && (v as string).length > 0;
              }).length}/{ARTIFACT_FIELD_LABELS.length} artifacts enabled
            </span>
          </>
        )}
        <span className="text-muted-foreground">
          {data.extend ? "Append (extend=true)" : "Overwrite"}
        </span>
      </div>
    </NodeCard>
  );
}
