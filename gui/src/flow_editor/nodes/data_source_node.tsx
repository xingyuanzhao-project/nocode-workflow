/**
 * Canvas node for the CSV input data source.
 *
 * Renders a compact summary of the current upload and the column
 * mapping. The full upload + column-mapping workflow lives in the
 * Property Panel so users do not have to zoom in to interact with
 * file pickers.
 */

import type { NodeProps } from "reactflow";

import { NodeCard } from "./node_card";
import type { CSVUploadResponse } from "@/schemas/files";
import type { ColumnRoles } from "@/schemas/flow";

export interface DataSourceNodeData {
  node_type_id: "csv_input";
  label: string;
  category: "data";
  /** The current upload metadata (``null`` before any upload). */
  upload: Partial<CSVUploadResponse> | null;
  /** Column role mapping filled out via :class:`ColumnMapper`. */
  column_roles: Partial<ColumnRoles>;
}

export function DataSourceNode({
  data,
  selected,
}: NodeProps<DataSourceNodeData>): JSX.Element {
  // Defend against a half-built payload: ``Object.values(undefined)``
  // would throw and crash the whole canvas via the router's error
  // boundary. Today's :func:`buildDefaultNodeData` always supplies an
  // empty object, but the guard keeps any future regression contained
  // to a single node card.
  const column_roles_map = (data.column_roles ?? {}) as Record<string, unknown>;
  const mapped_count = Object.values(column_roles_map).filter(
    (value) => typeof value === "string" && value !== "",
  ).length;
  // ``upload`` may come from a codec rehydration path where only
  // ``stored_path`` is known. Render every sub-field defensively so
  // the canvas never crashes on a partial payload.
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
      type_id={data.node_type_id}
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
          <span className="text-muted-foreground">
            {mapped_count}/4 roles mapped
          </span>
        </div>
      ) : (
        <span className="italic text-muted-foreground">
          No CSV uploaded yet.
        </span>
      )}
    </NodeCard>
  );
}
