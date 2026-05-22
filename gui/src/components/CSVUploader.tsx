/**
 * Data file uploader widget (CSV, JSON, JSONL).
 *
 * Picks a local file from a standard ``<input type="file" />`` and
 * posts it to ``POST /api/files/upload`` via
 * :func:`@/api/files.uploadCsv`. The typed
 * :class:`CSVUploadResponse` is passed back to the parent via the
 * ``on_uploaded`` callback; the parent decides how to persist it
 * (usually on the selected node's ``data`` payload).
 */

import { useCallback, useId, useState, type ChangeEvent } from "react";

import { uploadCsv } from "@/api/files";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import type { CSVUploadResponse } from "@/schemas/files";

export interface CSVUploaderProps {
  /** Current upload (``null`` when none has been attached yet). */
  current_upload: CSVUploadResponse | null;
  /** Called when a fresh upload succeeds. */
  on_uploaded: (upload: CSVUploadResponse) => void;
  /** Optional caption shown above the file input. */
  caption?: string;
  /** Optional disabled flag (for example when the node is readonly). */
  disabled?: boolean;
}

/**
 * File-picker widget wrapping :func:`uploadCsv`.
 */
export function CSVUploader({
  current_upload,
  on_uploaded,
  caption = "Upload data file",
  disabled = false,
}: CSVUploaderProps): JSX.Element {
  const input_id = useId();
  const [upload_error, set_upload_error] = useState<string | null>(null);
  const [is_uploading, set_is_uploading] = useState<boolean>(false);

  const on_file_change = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) {
        return;
      }
      set_upload_error(null);
      set_is_uploading(true);
      try {
        const response = await uploadCsv(file);
        on_uploaded(response);
      } catch (caught_error) {
        if (caught_error instanceof ApiError) {
          set_upload_error(
            caught_error.errors?.errors.map((issue) => issue.msg).join("; ") ||
              caught_error.message,
          );
        } else if (caught_error instanceof Error) {
          set_upload_error(caught_error.message);
        } else {
          set_upload_error(String(caught_error));
        }
      } finally {
        set_is_uploading(false);
        event.target.value = "";
      }
    },
    [on_uploaded],
  );

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={input_id}
        className={cn(
          "text-xs font-medium text-muted-foreground",
          disabled && "opacity-50",
        )}
      >
        {caption}
      </label>
      <input
        id={input_id}
        type="file"
        accept=".csv,.json,.jsonl,text/csv,application/json"
        disabled={disabled || is_uploading}
        onChange={on_file_change}
        className={cn(
          "block w-full text-xs",
          "file:mr-2 file:rounded-md file:border file:bg-secondary file:px-2 file:py-1 file:text-xs file:text-secondary-foreground",
          "file:hover:bg-accent",
          disabled && "opacity-50",
        )}
      />
      {is_uploading ? (
        <span className="text-xs text-muted-foreground">Uploading...</span>
      ) : null}
      {current_upload ? (
        <div className="text-xs text-muted-foreground">
          <div>
            <span className="font-medium">
              {current_upload.filename ?? "(uploaded)"}
            </span>
            {typeof current_upload.row_count === "number" ? (
              <> — {current_upload.row_count.toLocaleString()} rows</>
            ) : null}
          </div>
          {current_upload.stored_path ? (
            <div
              className="truncate font-mono"
              title={current_upload.stored_path}
            >
              {current_upload.stored_path}
            </div>
          ) : null}
        </div>
      ) : null}
      {upload_error ? (
        <span className="text-xs text-destructive">{upload_error}</span>
      ) : null}
    </div>
  );
}
