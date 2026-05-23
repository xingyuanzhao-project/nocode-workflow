/**
 * Data management page.
 *
 * Shows every data file in the workspace in one flat list. Users can
 * upload new files (CSV, JSON, JSONL) or delete existing ones. The
 * ``stored_path`` shown in the table is the value to use as
 * ``input_csv`` / ``input_file`` in a flow.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";

import { listDataFiles, uploadCsv } from "@/api/files";
import { Button } from "@/components/ui/button";
import { ApiError, buildApiUrl } from "@/api/client";

const DATA_FILES_QUERY_KEY = ["data-files"] as const;

export default function DataPage(): JSX.Element {
  const query_client = useQueryClient();
  const file_input_ref = useRef<HTMLInputElement | null>(null);
  const [upload_error, set_upload_error] = useState<string | null>(null);
  const [is_uploading, set_is_uploading] = useState(false);

  const files_query = useQuery({
    queryKey: DATA_FILES_QUERY_KEY,
    queryFn: listDataFiles,
    staleTime: 15_000,
  });

  const handle_upload = useCallback(
    async (file: File) => {
      set_upload_error(null);
      set_is_uploading(true);
      try {
        await uploadCsv(file);
        query_client.invalidateQueries({ queryKey: DATA_FILES_QUERY_KEY });
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
      }
    },
    [query_client],
  );

  const all_files = files_query.data?.files ?? [];

  const { input_files, output_files } = useMemo(() => {
    const input: typeof all_files = [];
    const output: typeof all_files = [];
    for (const f of all_files) {
      if (f.source === "output") {
        output.push(f);
      } else {
        input.push(f);
      }
    }
    return { input_files: input, output_files: output };
  }, [all_files]);

  const download_url = (stored_path: string) =>
    buildApiUrl("/api/files/download?path=" + encodeURIComponent(stored_path));

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <h1 className="text-lg font-semibold">Data</h1>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => file_input_ref.current?.click()}
            disabled={is_uploading}
          >
            <Upload className="mr-1 h-4 w-4" />
            {is_uploading ? "Uploading..." : "Upload file"}
          </Button>
          <input
            ref={file_input_ref}
            type="file"
            accept=".csv,.json,.jsonl,text/csv,application/json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void handle_upload(file);
              }
              event.target.value = "";
            }}
          />
        </div>
      </header>

      {upload_error ? (
        <div className="border-b bg-destructive/10 px-6 py-2 text-xs text-destructive">
          {upload_error}
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {files_query.isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : files_query.isError ? (
          <div className="text-sm text-destructive">
            Could not load data files: {String(files_query.error)}
          </div>
        ) : all_files.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No data files yet. Click &quot;Upload file&quot; to add one.
          </div>
        ) : (
          <div className="space-y-6">
            {input_files.length > 0 && (
              <section>
                <h2 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Input Data
                </h2>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Filename</th>
                      <th className="py-2 pr-3 font-medium">Stored path</th>
                      <th className="py-2 pr-3 font-medium">Rows</th>
                      <th className="py-2 font-medium">Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {input_files.map((file_item) => (
                      <tr
                        key={file_item.stored_path}
                        className="border-b last:border-0"
                      >
                        <td className="py-2 pr-3 font-medium">
                          {file_item.filename}
                        </td>
                        <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">
                          {file_item.stored_path}
                        </td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">
                          {file_item.row_count !== null
                            ? file_item.row_count.toLocaleString()
                            : "—"}
                        </td>
                        <td className="py-2">
                          <a
                            href={download_url(file_item.stored_path)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <Download className="h-3 w-3" />
                            Download
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {output_files.length > 0 && (
              <section>
                <h2 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Output Files
                </h2>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Filename</th>
                      <th className="py-2 pr-3 font-medium">Stored path</th>
                      <th className="py-2 font-medium">Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {output_files.map((file_item) => (
                      <tr
                        key={file_item.stored_path}
                        className="border-b last:border-0"
                      >
                        <td className="py-2 pr-3 font-medium text-emerald-600 dark:text-emerald-400">
                          {file_item.filename}
                        </td>
                        <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">
                          {file_item.stored_path}
                        </td>
                        <td className="py-2">
                          <a
                            href={download_url(file_item.stored_path)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <Download className="h-3 w-3" />
                            Download
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
