/**
 * Output Schema tab of the :mod:`PropertyPanel`.
 *
 * Editable table of the processor's output fields. Each row carries
 * a ``field_name``, ``type``, and ``required`` flag.
 */

import { useCallback, useMemo } from "react";

import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

interface OutputFieldRow {
  field_name: string;
  type: string;
  required: boolean;
}

const PRIMITIVE_TYPE_OPTIONS: readonly string[] = [
  "string",
  "array",
  "object",
  "boolean",
  "integer",
  "number",
];

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
      const type_value =
        field_body &&
        typeof field_body === "object" &&
        "type" in (field_body as Record<string, unknown>)
          ? String((field_body as Record<string, unknown>).type ?? "")
          : typeof field_body === "string"
            ? field_body
            : "";
      return {
        field_name,
        type: type_value,
        required: required_set.has(field_name),
      };
    },
  );
}

function rowsToIoSchema(
  rows: OutputFieldRow[],
): Record<string, unknown> {
  const output: Record<string, { type: string }> = {};
  const required_output: string[] = [];
  for (const row of rows) {
    if (!row.field_name) {
      continue;
    }
    output[row.field_name] = { type: row.type };
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
      { field_name: `field_${rows.length + 1}`, type: "string", required: false },
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
      <table className="text-xs">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="pb-1 font-medium">Field</th>
            <th className="pb-1 font-medium">Type</th>
            <th className="pb-1 text-center font-medium">Required</th>
            <th></th>
          </tr>
        </thead>
        <tbody className="align-top">
          {rows.map((row, row_index) => (
            <tr key={`${row.field_name}_${row_index}`}>
              <td className="pr-1 py-0.5">
                <input
                  className="w-full rounded-md border bg-background px-1.5 py-0.5 font-mono"
                  value={row.field_name}
                  onChange={(event) =>
                    on_row_change(row_index, { field_name: event.target.value })
                  }
                />
              </td>
              <td className="pr-1 py-0.5">
                <select
                  className="w-full rounded-md border bg-background px-1.5 py-0.5"
                  value={row.type}
                  onChange={(event) =>
                    on_row_change(row_index, { type: event.target.value })
                  }
                >
                  {PRIMITIVE_TYPE_OPTIONS.map((primitive_type) => (
                    <option key={primitive_type} value={primitive_type}>
                      {primitive_type}
                    </option>
                  ))}
                </select>
              </td>
              <td className="text-center py-0.5">
                <input
                  type="checkbox"
                  checked={row.required}
                  onChange={(event) =>
                    on_row_change(row_index, { required: event.target.checked })
                  }
                />
              </td>
              <td className="py-0.5 text-right">
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() => on_row_remove(row_index)}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
