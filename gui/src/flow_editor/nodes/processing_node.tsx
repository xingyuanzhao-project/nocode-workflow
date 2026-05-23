/**
 * Canvas node for a generic processor step.
 *
 * Shows the processing unit and output field names derived from the
 * node's io_schema.
 */

import { useMemo } from "react";
import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";

export interface ProcessingNodeData {
  node_type_id: string;
  label: string;
  category: "processor";
  unit: string;
  io_schema?: { output?: Record<string, unknown> } | null;
  prompt?: { instructions?: string[] } | null;
  prompts_ref?: string | null;
}

export function ProcessingNode({
  data,
  selected,
}: NodeProps<ProcessingNodeData>): JSX.Element {
  const output_field_names = useMemo(() => {
    const schema = data.io_schema;
    if (schema && typeof schema === "object" && schema.output && typeof schema.output === "object") {
      return Object.keys(schema.output);
    }
    return [];
  }, [data.io_schema]);

  return (
    <NodeCard
      category=""
      title={data.label}
      type_id={data.node_type_id}
      selected={selected}
      has_top_handle={true}
      has_bottom_handle={true}
    >
      <div className="flex flex-col gap-0.5">
        <span>
          Unit: <span className="font-mono">{data.unit}</span>
        </span>
        {output_field_names.length > 0 ? (
          <span className="truncate" title={output_field_names.join(", ")}>
            Output: <span className="font-mono">{output_field_names.join(", ")}</span>
          </span>
        ) : (
          <span className="text-muted-foreground italic">No output fields defined</span>
        )}
      </div>
    </NodeCard>
  );
}
