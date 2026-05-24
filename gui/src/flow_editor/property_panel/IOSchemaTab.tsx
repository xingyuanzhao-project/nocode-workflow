/**
 * Output Schema tab of the :mod:`PropertyPanel`.
 *
 * Editable table of the processor's output fields. Each row carries
 * a ``field_name``, ``data_type``, ``required`` flag, and conditional
 * metadata (``options`` for category, ``range`` / ``interval`` for
 * numeric/integer).
 */

import { useCallback, useMemo } from "react";

import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

type DataType = "string" | "binary" | "category" | "numeric" | "integer";

const DATA_TYPE_OPTIONS: { value: DataType; label: string }[] = [
  { value: "string", label: "String" },
  { value: "binary", label: "Binary" },
  { value: "category", label: "Category" },
  { value: "numeric", label: "Numeric" },
  { value: "integer", label: "Integer" },
];

const DATA_TYPE_TO_JSON_SCHEMA: Record<DataType, string> = {
  string: "string",
  binary: "string",
  category: "string",
  numeric: "number",
  integer: "integer",
};

interface OutputFieldRow {
  field_name: string;
  data_type: DataType;
  required: boolean;
  options: string[];
  range: string;
  interval: string;
}

function parseDataType(raw: unknown): DataType {
  if (
    typeof raw === "string" &&
    (DATA_TYPE_OPTIONS as { value: string }[]).some((dt) => dt.value === raw)
  ) {
    return raw as DataType;
  }
  if (raw === "number") return "numeric";
  if (raw === "boolean") return "binary";
  if (raw === "array") return "category";
  if (raw === "integer") return "integer";
  return "string";
}

function readOutputRows(node: GraphNode): OutputFieldRow[] {
  const io_schema_override = node.data.io_schema;
  const io_schema_source =
    io_schema_override && typeof io_schema_override === "object"
      ? io_schema_override
      : node.data.default_io_schema;
  if (!io_schema_source || typeof io_schema_source !== "object") {
    return [];
  }
  const output_block = (io_schema_source as Record<string, unknown>).output;
  if (!output_block || typeof output_block !== "object") {
    return [];
  }
  const required_list = (
    (io_schema_source as Record<string, unknown>).required_output ?? []
  ) as unknown;
  const required_set = new Set<string>(
    Array.isArray(required_list)
      ? required_list.map((value) => String(value))
      : [],
  );
  return Object.entries(output_block as Record<string, unknown>).map(
    ([field_name, field_body]) => {
      if (!field_body || typeof field_body !== "object") {
        return {
          field_name,
          data_type: "string" as DataType,
          required: required_set.has(field_name),
          options: [],
          range: "",
          interval: "",
        };
      }
      const rec = field_body as Record<string, unknown>;
      const raw_data_type = rec.data_type ?? rec.type ?? "string";
      const options_raw = rec.options;
      const options_list: string[] = Array.isArray(options_raw)
        ? options_raw.map((v) => String(v))
        : [];
      return {
        field_name,
        data_type: parseDataType(raw_data_type),
        required: required_set.has(field_name),
        options: options_list,
        range: String(rec.range ?? ""),
        interval: String(rec.interval ?? ""),
      };
    },
  );
}

function rowsToIoSchema(rows: OutputFieldRow[]): Record<string, unknown> {
  const output: Record<string, Record<string, unknown>> = {};
  const required_output: string[] = [];
  for (const row of rows) {
    if (!row.field_name) continue;
    const entry: Record<string, unknown> = {
      type: DATA_TYPE_TO_JSON_SCHEMA[row.data_type],
      data_type: row.data_type,
    };
    if (row.data_type === "category") {
      entry.options = row.options;
    } else if (row.data_type === "numeric" || row.data_type === "integer") {
      if (row.range) entry.range = row.range;
      if (row.interval) entry.interval = row.interval;
    }
    output[row.field_name] = entry;
    if (row.required) {
      required_output.push(row.field_name);
    }
  }
  return { output, required_output };
}

export interface IOSchemaTabProps {
  node: GraphNode;
}

export function IOSchemaTab({ node }: IOSchemaTabProps): JSX.Element {
  const rows = useMemo(() => readOutputRows(node), [node]);
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const write_rows = useCallback(
    (next_rows: OutputFieldRow[]) => {
      update_node_data(node.id, {
        io_schema: rowsToIoSchema(next_rows),
      });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const on_row_change = useCallback(
    (row_index: number, patch: Partial<OutputFieldRow>) => {
      const next_rows = rows.map((row, index_candidate) =>
        index_candidate === row_index ? { ...row, ...patch } : row,
      );
      write_rows(next_rows);
    },
    [rows, write_rows],
  );

  const on_row_remove = useCallback(
    (row_index: number) => {
      write_rows(rows.filter((_, index_candidate) => index_candidate !== row_index));
    },
    [rows, write_rows],
  );

  const on_add_row = useCallback(() => {
    write_rows([
      ...rows,
      {
        field_name: `field_${rows.length + 1}`,
        data_type: "string",
        required: false,
        options: [],
        range: "",
        interval: "",
      },
    ]);
  }, [rows, write_rows]);

  const on_reset_to_defaults = useCallback(() => {
    update_node_data(node.id, { io_schema: null });
    set_dirty(true);
  }, [node.id, update_node_data, set_dirty]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground">
          Define the fields the LLM should return for each processed
          item.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {rows.map((row, row_index) => (
          <div
            key={row_index}
            className="rounded-md border bg-card p-3"
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <label className="flex flex-1 flex-col gap-0.5 text-xs">
                    <span className="font-medium">Field</span>
                    <input
                      className="w-full rounded-md border bg-background px-1.5 py-0.5 font-mono text-sm"
                      value={row.field_name}
                      onChange={(event) =>
                        on_row_change(row_index, {
                          field_name: event.target.value,
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium">Required</span>
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={row.required}
                      onChange={(event) =>
                        on_row_change(row_index, {
                          required: event.target.checked,
                        })
                      }
                    />
                  </label>
                </div>

                <label className="flex flex-col gap-0.5 text-xs">
                  <span className="font-medium">Type</span>
                  <select
                    className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                    value={row.data_type}
                    onChange={(event) =>
                      on_row_change(row_index, {
                        data_type: event.target.value as DataType,
                        options: [],
                        range: "",
                        interval: "",
                      })
                    }
                  >
                    {DATA_TYPE_OPTIONS.map((dt) => (
                      <option key={dt.value} value={dt.value}>
                        {dt.label}
                      </option>
                    ))}
                  </select>
                </label>

                {(row.data_type === "numeric" ||
                  row.data_type === "integer") ? (
                  <div className="grid grid-cols-2 gap-2">
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Range</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 0–100"
                        value={row.range}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            range: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Interval</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 1"
                        value={row.interval}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            interval: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                ) : (
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium">
                      {row.data_type === "category"
                        ? "Available Options (comma-separated)"
                        : "Available Options"}
                    </span>
                    <input
                      className="rounded-md border bg-background px-1.5 py-0.5 text-sm disabled:opacity-50"
                      disabled={
                        row.data_type === "string" ||
                        row.data_type === "binary"
                      }
                      value={row.options.join(", ")}
                      onChange={(event) =>
                        on_row_change(row_index, {
                          options: event.target.value
                            .split(",")
                            .map((v) => v.trim())
                            .filter((v) => v.length > 0),
                        })
                      }
                    />
                  </label>
                )}
              </div>
              <button
                type="button"
                className="mt-4 text-xs text-destructive hover:underline"
                onClick={() => on_row_remove(row_index)}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 text-xs">
        <button
          type="button"
          className="rounded-md border bg-secondary px-2 py-1 text-secondary-foreground hover:bg-accent"
          onClick={on_add_row}
        >
          Add field
        </button>
        <button
          type="button"
          className="rounded-md border bg-background px-2 py-1 text-muted-foreground hover:bg-accent"
          onClick={on_reset_to_defaults}
        >
          Reset to default
        </button>
      </div>
    </div>
  );
}
