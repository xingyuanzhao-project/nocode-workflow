/**
 * Table component consuming :class:`ResultsPreviewResponse`.
 *
 * Scoped to the run-page panel; the plan defers the full tanstack-
 * virtualised table for later. Keeps the column order the server
 * emitted and coerces every cell to a string for display.
 */

import type { ResultsPreviewResponse } from "@/schemas/results";

export interface ResultsPreviewTableProps {
  preview: ResultsPreviewResponse | null;
  is_loading: boolean;
  error: Error | null;
}

function renderCellValue(cell_value: unknown): string {
  if (cell_value === null || cell_value === undefined) {
    return "";
  }
  if (typeof cell_value === "object") {
    try {
      return JSON.stringify(cell_value);
    } catch {
      return String(cell_value);
    }
  }
  return String(cell_value);
}

export function ResultsPreviewTable({
  preview,
  is_loading,
  error,
}: ResultsPreviewTableProps): JSX.Element {
  if (is_loading) {
    return (
      <div className="text-sm text-muted-foreground">Loading preview...</div>
    );
  }
  if (error) {
    return (
      <div className="text-sm text-destructive">
        Could not load preview: {error.message}
      </div>
    );
  }
  if (!preview) {
    return (
      <div className="text-sm text-muted-foreground">
        No preview available yet.
      </div>
    );
  }
  if (preview.columns.length === 0 || preview.preview_rows.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        Preview is empty.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs text-muted-foreground">
        Showing {preview.preview_rows.length} of{" "}
        {preview.total_row_count.toLocaleString()} rows
      </div>
      <div className="overflow-auto rounded-md border bg-card">
        <table className="min-w-full text-xs">
          <thead className="bg-muted/50">
            <tr>
              {preview.columns.map((column_name) => (
                <th
                  key={column_name}
                  className="whitespace-nowrap border-b px-3 py-2 text-left font-medium"
                >
                  {column_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.preview_rows.map((row_record, row_index) => (
              <tr
                key={row_index}
                className="border-b last:border-0"
              >
                {preview.columns.map((column_name) => (
                  <td
                    key={column_name}
                    className="max-w-[16rem] truncate px-3 py-1.5 align-top"
                    title={renderCellValue(row_record[column_name])}
                  >
                    {renderCellValue(row_record[column_name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
