/**
 * Right-hand property panel for the selected node.
 *
 * Dispatches on :attr:`NodeTypeEntry.category` and ``node_type_id``
 * to render:
 *
 * - A Config section every node gets (see :mod:`./ConfigTab`).
 * - An Output Schema section shown only for processor nodes.
 * - A Prompt section shown only for processor nodes.
 *
 * For processor nodes all three sections are rendered in a single
 * scrollable pane (no tabs).
 *
 * The panel is entirely driven by :mod:`@/stores/graph_store`:
 * it reads the selected node's ``data`` and writes changes through
 * ``update_node_data``.
 */

import { useCallback, useMemo } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

import { ConfigTab } from "./ConfigTab";

/* ── Output-schema types and helpers ──────────────────────────── */

type DataType = "string" | "binary" | "category" | "numeric" | "integer";

const DATA_TYPE_OPTIONS: { value: DataType; label: string }[] = [
  { value: "string", label: "String" },
  { value: "binary", label: "Binary" },
  { value: "category", label: "Category" },
  { value: "numeric", label: "Numeric" },
  { value: "integer", label: "Integer" },
];

interface OutputFieldRow {
  field_name: string;
  data_type: DataType;
  required: boolean;
  options: string[];
  range_start: string;
  range_end: string;
  step: string;
}

function parseDataType(raw: unknown): DataType {
  if (
    typeof raw === "string" &&
    (DATA_TYPE_OPTIONS as { value: string }[]).some((dt) => dt.value === raw)
  ) {
    return raw as DataType;
  }
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
          range_start: "",
          range_end: "",
          step: "",
        };
      }
      const rec = field_body as Record<string, unknown>;
      const raw_data_type = rec.data_type ?? "string";
      const options_raw = rec.options;
      const options_list: string[] = Array.isArray(options_raw)
        ? options_raw.map((v) => String(v))
        : [];
      return {
        field_name,
        data_type: parseDataType(raw_data_type),
        required: required_set.has(field_name),
        options: options_list,
        range_start: String(rec.range_start ?? ""),
        range_end: String(rec.range_end ?? ""),
        step: String(rec.step ?? ""),
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
      data_type: row.data_type,
    };
    if (row.data_type === "category") {
      entry.options = row.options;
    } else if (row.data_type === "numeric" || row.data_type === "integer") {
      if (row.range_start) entry.range_start = row.range_start;
      if (row.range_end) entry.range_end = row.range_end;
      if (row.step) entry.step = row.step;
    }
    output[row.field_name] = entry;
    if (row.required) {
      required_output.push(row.field_name);
    }
  }
  return { output, required_output };
}

/* ── Prompt helpers ───────────────────────────────────────────── */

function readInstructions(node: GraphNode): string {
  const prompt = node.data.prompt;
  if (prompt && typeof prompt === "object") {
    const instructions = (prompt as Record<string, unknown>).instructions;
    if (Array.isArray(instructions) && instructions.length > 0) {
      return instructions.map(String).join("\n");
    }
  }
  return "";
}

function readPromptsRef(node: GraphNode): string | null {
  const ref = node.data.prompts_ref;
  return typeof ref === "string" && ref.length > 0 ? ref : null;
}

function writeInstructions(text: string): Record<string, unknown> {
  const lines = text.split("\n").filter((line) => line.length > 0);
  return {
    prompt: { instructions: lines },
    prompts_ref: null,
    prompt_overrides: null,
  };
}

/* ── Internal sections (processor-only) ───────────────────────── */

function OutputSchemaSection({ node }: { node: GraphNode }): JSX.Element {
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
        range_start: "",
        range_end: "",
        step: "",
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
                        range_start: "",
                        range_end: "",
                        step: "",
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

                {row.data_type === "category" && (
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium">
                      Available Options (comma-separated)
                    </span>
                    <input
                      className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
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

                {row.data_type === "numeric" && (
                  <div className="grid grid-cols-2 gap-2">
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Range start</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 0"
                        value={row.range_start}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            range_start: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Range end</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 100"
                        value={row.range_end}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            range_end: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                )}

                {row.data_type === "integer" && (
                  <div className="grid grid-cols-3 gap-2">
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Range start</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 0"
                        value={row.range_start}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            range_start: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Range end</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 100"
                        value={row.range_end}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            range_end: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="flex flex-col gap-0.5 text-xs">
                      <span className="font-medium">Step</span>
                      <input
                        className="rounded-md border bg-background px-1.5 py-0.5 text-sm"
                        placeholder="e.g. 1"
                        value={row.step}
                        onChange={(event) =>
                          on_row_change(row_index, {
                            step: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
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

function PromptSection({ node }: { node: GraphNode }): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const instructions = useMemo(() => readInstructions(node), [node]);
  const prompts_ref = useMemo(() => readPromptsRef(node), [node]);

  const on_change = useCallback(
    (text: string) => {
      update_node_data(node.id, writeInstructions(text));
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  return (
    <div className="flex flex-col gap-3 text-xs">
      {prompts_ref && !instructions ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
          <p className="font-medium">Using prompt reference: {prompts_ref}</p>
          <p className="mt-1 text-muted-foreground">
            This processor uses a shared prompt template. Write instructions
            below to override it with an inline prompt.
          </p>
        </div>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className="font-medium">Instructions</span>
        <textarea
          className="min-h-[12rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
          placeholder="Write the processing instructions for this step..."
          value={instructions}
          onChange={(event) => on_change(event.target.value)}
        />
        <span className="text-muted-foreground">
          One instruction per line. These are sent as the system prompt
          to the LLM.
        </span>
      </label>
    </div>
  );
}

/* ── Main panel ───────────────────────────────────────────────── */

const PROCESSOR_CATEGORY = "processor";

function readNodeById(
  nodes: GraphNode[],
  node_id: string | null,
): GraphNode | null {
  if (node_id === null) {
    return null;
  }
  return nodes.find((candidate) => candidate.id === node_id) ?? null;
}

export function PropertyPanel(): JSX.Element {
  const selected_node_id = useGraphStore(
    (state) => state.selected_node_id,
  );
  const nodes = useGraphStore((state) => state.nodes);
  const delete_node = useGraphStore((state) => state.delete_node);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const selected_node = useMemo(
    () => readNodeById(nodes, selected_node_id),
    [nodes, selected_node_id],
  );

  if (!selected_node) {
    return (
      <aside className="flex h-full w-80 shrink-0 flex-col border-l bg-background p-4 text-sm text-muted-foreground">
        Select a node to edit its configuration.
      </aside>
    );
  }

  const node_type_id = String(selected_node.data.node_type_id ?? "");
  const category = String(selected_node.data.category ?? "");
  const label = String(selected_node.data.label ?? node_type_id);
  const is_processor_node = category === PROCESSOR_CATEGORY;
  const on_delete = () => {
    if (
      window.confirm(`Delete ${label}? This will remove its connected wires too.`)
    ) {
      delete_node(selected_node.id);
      set_dirty(true);
    }
  };

  return (
    <aside className="flex h-full w-96 shrink-0 flex-col overflow-hidden border-l bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {is_processor_node ? (
              <>
                <h2 className="text-sm font-semibold">{label}</h2>
                <div className="text-xs text-muted-foreground">
                  Configure output schema and prompt instructions.
                </div>
              </>
            ) : (
              <>
                <div className="text-[0.65rem] font-mono uppercase tracking-wide text-muted-foreground">
                  {category || "Node"}
                </div>
                <h2 className="text-sm font-semibold">{label}</h2>
              </>
            )}
          </div>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            className="shrink-0"
            onClick={on_delete}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>
      {is_processor_node ? (
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-6">
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Config
            </h3>
            <ConfigTab node={selected_node} />
          </section>
          <hr />
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Output Schema
            </h3>
            <OutputSchemaSection node={selected_node} />
          </section>
          <hr />
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Prompt
            </h3>
            <PromptSection node={selected_node} />
          </section>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <ConfigTab node={selected_node} />
        </div>
      )}
    </aside>
  );
}
