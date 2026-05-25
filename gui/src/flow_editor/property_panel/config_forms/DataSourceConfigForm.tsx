/**
 * Config-tab form for data input nodes (CSV input / JSON input).
 *
 * Lets the user pick from files already uploaded via Menu > Data,
 * then select which columns/fields to pass to the processor.
 */

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchColumnHeaders, listDataFiles } from "@/api/files";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

export interface DataSourceConfigFormProps {
  node: GraphNode;
}

function read_input_columns(node: GraphNode): string[] {
  const raw = node.data.input_columns;
  if (Array.isArray(raw)) return raw.filter((x): x is string => typeof x === "string");
  return [];
}

export function DataSourceConfigForm({
  node,
}: DataSourceConfigFormProps): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);
  const node_type_id = String(node.data.node_type_id ?? "csv_input");

  const selected_path =
    typeof node.data.selected_file === "string" ? node.data.selected_file : "";

  const files_query = useQuery({
    queryKey: ["data-files-list"],
    queryFn: listDataFiles,
    staleTime: 30_000,
  });

  const is_json = node_type_id === "json_input";

  const columns_query = useQuery({
    queryKey: ["file-fields", selected_path],
    queryFn: () => fetchColumnHeaders(selected_path),
    enabled: selected_path.length > 0,
    staleTime: 60_000,
  });

  const available_columns = columns_query.data?.columns ?? [];

  const allowed_extensions = useMemo(() => {
    if (is_json) return new Set([".json", ".jsonl"]);
    return new Set([".csv"]);
  }, [is_json]);

  const available_files = useMemo(() => {
    const all = files_query.data?.files ?? [];
    return all.filter((f) => {
      const ext = f.filename.substring(f.filename.lastIndexOf(".")).toLowerCase();
      return allowed_extensions.has(ext);
    });
  }, [files_query.data, allowed_extensions]);

  const display_files = available_files;

  const input_columns = read_input_columns(node);

  const on_select = useCallback(
    (stored_path: string) => {
      update_node_data(node.id, { selected_file: stored_path || null });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const update_columns = useCallback(
    (next: string[]) => {
      update_node_data(node.id, { input_columns: next });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const on_column_value_change = useCallback(
    (index: number, value: string) => {
      const next = input_columns.map((col, i) => (i === index ? value : col));
      update_columns(next);
    },
    [input_columns, update_columns],
  );

  const on_add_column = useCallback(() => {
    update_columns([...input_columns, ""]);
  }, [input_columns, update_columns]);

  const on_remove_column = useCallback(
    (index: number) => {
      update_columns(input_columns.filter((_, i) => i !== index));
    },
    [input_columns, update_columns],
  );

  const section_label = is_json ? "Input Fields" : "Input Columns";
  const field_label = is_json ? "Field Name" : "Column Name";
  const placeholder = is_json ? "Select field..." : "Select column...";
  const add_label = is_json ? "+ Add Field" : "+ Add Column";

  return (
    <div className="flex flex-col gap-4 text-xs">
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
            {display_files.map((file) => (
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

      <div className="flex flex-col gap-2">
        <span className="font-medium">{section_label}</span>

        {columns_query.isLoading && selected_path && (
          <span className="text-muted-foreground">Loading data...</span>
        )}

        {input_columns.map((col_name, index) => (
          <div key={index} className="flex items-end gap-1">
            <label className="flex flex-1 flex-col gap-0.5">
              {index === 0 && (
                <span className="text-muted-foreground">{field_label}</span>
              )}
              <select
                className="rounded-md border bg-background px-2 py-1 text-sm"
                value={col_name}
                disabled={columns_query.isLoading}
                onChange={(e) => on_column_value_change(index, e.target.value)}
              >
                <option value="">{placeholder}</option>
                {available_columns.map((col) => (
                  <option key={col} value={col}>
                    {col}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="rounded-md border px-1.5 py-1 text-sm text-muted-foreground hover:text-foreground"
              title="Remove"
              onClick={() => on_remove_column(index)}
            >
              &times;
            </button>
          </div>
        ))}

        <button
          type="button"
          className="self-start rounded-md border px-2 py-1 text-sm hover:bg-muted"
          onClick={on_add_column}
        >
          {add_label}
        </button>
        <span className="text-muted-foreground">
          Selected {is_json ? "fields" : "columns"} will be passed to the processor as input.
        </span>
      </div>
    </div>
  );
}
