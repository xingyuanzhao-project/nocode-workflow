/**
 * Config-tab form for data input nodes (CSV input / JSON input).
 *
 * Lets the user pick from files already uploaded via Menu > Data,
 * rather than uploading inside the flow editor.
 */

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { listDataFiles } from "@/api/files";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

export interface DataSourceConfigFormProps {
  node: GraphNode;
}

export function DataSourceConfigForm({
  node,
}: DataSourceConfigFormProps): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);
  const node_type_id = String(node.data.node_type_id ?? "csv_input");

  const files_query = useQuery({
    queryKey: ["data-files-list"],
    queryFn: listDataFiles,
    staleTime: 30_000,
  });

  const allowed_extensions = useMemo(() => {
    if (node_type_id === "json_input") return new Set([".json", ".jsonl"]);
    return new Set([".csv"]);
  }, [node_type_id]);

  const available_files = useMemo(() => {
    const all = files_query.data?.files ?? [];
    return all.filter((f) => {
      const ext = f.filename.substring(f.filename.lastIndexOf(".")).toLowerCase();
      return allowed_extensions.has(ext);
    });
  }, [files_query.data, allowed_extensions]);

  const selected_path =
    typeof node.data.selected_file === "string" ? node.data.selected_file : "";

  const on_select = useCallback(
    (stored_path: string) => {
      update_node_data(node.id, { selected_file: stored_path || null });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  return (
    <div className="flex flex-col gap-3 text-xs">
      <label className="flex flex-col gap-1">
        <span className="font-medium">Data file</span>
        {files_query.isLoading ? (
          <span className="text-muted-foreground">Loading files...</span>
        ) : (
          <select
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={selected_path}
            onChange={(event) => on_select(event.target.value)}
          >
            <option value="">Select a file...</option>
            {available_files.map((file) => (
              <option key={file.stored_path} value={file.stored_path}>
                {file.filename}
              </option>
            ))}
          </select>
        )}
        <span className="text-muted-foreground">
          Upload files via Menu &rarr; Data, then select here.
        </span>
      </label>
    </div>
  );
}
