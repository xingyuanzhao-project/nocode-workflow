/**
 * Canvas node for the CSV input data source.
 *
 * Supports both the new model (selected_file path) and the legacy
 * model (upload object). The file picker lives in the Property Panel.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";
import type { CSVUploadResponse } from "@/schemas/files";

export interface DataSourceNodeData {
  node_type_id: string;
  label: string;
  category: "data";
  selected_file?: string | null;
  upload?: Partial<CSVUploadResponse> | null;
}

export function DataSourceNode({
  data,
  selected,
}: NodeProps<DataSourceNodeData>): JSX.Element {
  // New model: selected_file is a string path
  if (typeof data.selected_file === "string" && data.selected_file.length > 0) {
    const filename = data.selected_file.split("/").pop() ?? data.selected_file;
    return (
      <NodeCard
        category="Data"
        title={data.label}
        selected={selected}
        has_input_handle={false}
      >
        <div className="flex flex-col gap-0.5">
          <span className="truncate font-medium" title={data.selected_file}>
            {filename}
          </span>
        </div>
      </NodeCard>
    );
  }

  // Old model: upload object
  const upload_filename =
    typeof data.upload?.filename === "string"
      ? data.upload.filename
      : typeof data.upload?.stored_path === "string"
        ? data.upload.stored_path.split("/").pop() ?? data.upload.stored_path
        : null;
  const upload_row_count =
    typeof data.upload?.row_count === "number" ? data.upload.row_count : null;
  const upload_column_count =
    Array.isArray(data.upload?.columns)
      ? data.upload.columns.length
      : null;

  return (
    <NodeCard
      category="Data"
      title={data.label}
      selected={selected}
      has_input_handle={false}
    >
      {data.upload ? (
        <div className="flex flex-col gap-0.5">
          {upload_filename ? (
            <span className="truncate font-medium" title={upload_filename}>
              {upload_filename}
            </span>
          ) : null}
          {upload_row_count !== null && upload_column_count !== null ? (
            <span className="text-muted-foreground">
              {upload_row_count.toLocaleString()} rows ·{" "}
              {upload_column_count} columns
            </span>
          ) : null}
        </div>
      ) : (
        <span className="italic text-muted-foreground">
          No file selected.
        </span>
      )}
    </NodeCard>
  );
}
