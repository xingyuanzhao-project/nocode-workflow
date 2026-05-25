/**
 * Canvas node for the output-CSV/JSON sink.
 *
 * Shows the configured output path, output fields, and extend mode.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface CSVOutputNodeData {
  node_type_id: string;
  label: string;
  category: "data";
  output_path?: string;
  output_fields?: string[];
  extend?: boolean;
}

export function CSVOutputNode({
  data,
  selected,
}: NodeProps<CSVOutputNodeData>): JSX.Element {
  return (
    <NodeCard
      category="Output"
      title={data.label}
      selected={selected}
      has_output_handle={false}
    >
      <div className="flex flex-col gap-0.5">
        <span className="truncate font-mono" title={data.output_path}>
          {data.output_path || "— path unset —"}
        </span>
        {(data.output_fields?.length ?? 0) > 0 && (
          <span className="text-muted-foreground">
            Fields: {data.output_fields!.join(", ")}
          </span>
        )}
        <span className="text-muted-foreground">
          {data.extend ? "Append (extend=true)" : "Overwrite"}
        </span>
      </div>
    </NodeCard>
  );
}
