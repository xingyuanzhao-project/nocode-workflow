/**
 * Editable list of taxonomy labels.
 *
 * The taxonomy JSON is an open dict of ``label_key -> {definition,
 * options, context_definition, ...}``. The editor is deliberately
 * forgiving: unknown per-label fields are preserved so imports of
 * hand-crafted taxonomies round-trip cleanly.
 */

import { useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";

export type DataType = "string" | "binary" | "category" | "numeric" | "integer";

export const DATA_TYPE_LABELS: { value: DataType; label: string }[] = [
  { value: "string", label: "String" },
  { value: "binary", label: "Binary" },
  { value: "category", label: "Category" },
  { value: "numeric", label: "Numeric" },
  { value: "integer", label: "Integer" },
];

export interface LabelEntry {
  /** Machine name, used by the LLM prompts. */
  key: string;
  /** Human description. */
  definition: string;
  /** Data type of this variable. */
  data_type: DataType;
  /** Valid classification values (comma-separated at display time). */
  options: string[];
  /** Lower and upper bound for numeric/integer types. */
  range: string;
  /** Step size for numeric/integer types. */
  interval: string;
  /** Detailed extraction guidance. */
  context_definition: string;
  /** Preserved per-label fields we do not otherwise touch. */
  passthrough: Record<string, unknown>;
}

const KNOWN_FIELDS = new Set([
  "definition",
  "data_type",
  "options",
  "range",
  "interval",
  "context_definition",
]);

function parseDataType(raw: unknown): DataType {
  const valid: DataType[] = ["string", "binary", "category", "numeric", "integer"];
  if (typeof raw === "string" && valid.includes(raw as DataType)) {
    return raw as DataType;
  }
  return "string";
}

export function labelEntriesFromJson(
  taxonomy: Record<string, unknown>,
): LabelEntry[] {
  return Object.entries(taxonomy).map(([key, body]) => {
    if (!body || typeof body !== "object") {
      return {
        key,
        definition: "",
        data_type: "string" as DataType,
        options: [],
        range: "",
        interval: "",
        context_definition: "",
        passthrough: {},
      };
    }
    const record = body as Record<string, unknown>;
    const options_raw = record.options;
    const options_list: string[] = Array.isArray(options_raw)
      ? options_raw.map((option_value) => String(option_value))
      : [];
    const passthrough: Record<string, unknown> = {};
    for (const [field_name, field_value] of Object.entries(record)) {
      if (KNOWN_FIELDS.has(field_name)) {
        continue;
      }
      passthrough[field_name] = field_value;
    }
    return {
      key,
      definition: String(record.definition ?? ""),
      data_type: parseDataType(record.data_type),
      options: options_list,
      range: String(record.range ?? ""),
      interval: String(record.interval ?? ""),
      context_definition: String(record.context_definition ?? ""),
      passthrough,
    };
  });
}

export function labelEntriesToJson(
  entries: LabelEntry[],
): Record<string, unknown> {
  const taxonomy_body: Record<string, unknown> = {};
  for (const entry of entries) {
    if (!entry.key) {
      continue;
    }
    const body: Record<string, unknown> = {
      ...entry.passthrough,
      definition: entry.definition,
      data_type: entry.data_type,
      context_definition: entry.context_definition,
    };
    if (entry.data_type === "numeric" || entry.data_type === "integer") {
      body.range = entry.range;
      body.interval = entry.interval;
    } else {
      body.options = entry.options;
    }
    taxonomy_body[entry.key] = body;
  }
  return taxonomy_body;
}

export interface LabelEditorProps {
  entries: LabelEntry[];
  on_change: (next_entries: LabelEntry[]) => void;
}

export function LabelEditor({
  entries,
  on_change,
}: LabelEditorProps): JSX.Element {
  const update_entry = useCallback(
    (entry_index: number, patch: Partial<LabelEntry>) => {
      on_change(
        entries.map((entry, candidate_index) =>
          candidate_index === entry_index ? { ...entry, ...patch } : entry,
        ),
      );
    },
    [entries, on_change],
  );

  const remove_entry = useCallback(
    (entry_index: number) => {
      on_change(entries.filter((_, candidate_index) => candidate_index !== entry_index));
    },
    [entries, on_change],
  );

  const add_entry = useCallback(() => {
    on_change([
      ...entries,
      {
        key: `variable_${entries.length + 1}`,
        definition: "",
        data_type: "string" as DataType,
        options: [],
        range: "",
        interval: "",
        context_definition: "",
        passthrough: {},
      },
    ]);
  }, [entries, on_change]);

  return (
    <div className="flex flex-col gap-4">
      {entries.map((entry, entry_index) => (
        <div
          key={`${entry.key}_${entry_index}`}
          className="rounded-md border bg-card p-3"
        >
          <div className="flex items-start gap-3">
            <div className="flex-1 space-y-2">
              <label className="flex flex-col gap-0.5 text-xs">
                <span className="font-medium">Variable Name</span>
                <input
                  className="rounded-md border bg-background px-2 py-1 text-sm font-mono"
                  value={entry.key}
                  onChange={(event) =>
                    update_entry(entry_index, { key: event.target.value })
                  }
                />
              </label>
              <label className="flex flex-col gap-0.5 text-xs">
                <span className="font-medium">Definition</span>
                <input
                  className="rounded-md border bg-background px-2 py-1 text-sm"
                  value={entry.definition}
                  onChange={(event) =>
                    update_entry(entry_index, {
                      definition: event.target.value,
                    })
                  }
                />
              </label>
              <label className="flex flex-col gap-0.5 text-xs">
                <span className="font-medium">Data Type</span>
                <select
                  className="rounded-md border bg-background px-2 py-1 text-sm"
                  value={entry.data_type}
                  onChange={(event) =>
                    update_entry(entry_index, {
                      data_type: event.target.value as DataType,
                    })
                  }
                >
                  {DATA_TYPE_LABELS.map((dt) => (
                    <option key={dt.value} value={dt.value}>
                      {dt.label}
                    </option>
                  ))}
                </select>
              </label>
              {(entry.data_type === "numeric" || entry.data_type === "integer") ? (
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium">Range</span>
                    <input
                      className="rounded-md border bg-background px-2 py-1 text-sm"
                      placeholder="e.g. 0–100"
                      value={entry.range}
                      onChange={(event) =>
                        update_entry(entry_index, { range: event.target.value })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium">Interval</span>
                    <input
                      className="rounded-md border bg-background px-2 py-1 text-sm"
                      placeholder="e.g. 1"
                      value={entry.interval}
                      onChange={(event) =>
                        update_entry(entry_index, {
                          interval: event.target.value,
                        })
                      }
                    />
                  </label>
                </div>
              ) : (
                <label className="flex flex-col gap-0.5 text-xs">
                  <span className="font-medium">
                    {entry.data_type === "category"
                      ? "Available Options (comma-separated)"
                      : "Available Options"}
                  </span>
                  <input
                    className="rounded-md border bg-background px-2 py-1 text-sm disabled:opacity-50"
                    disabled={entry.data_type === "string" || entry.data_type === "binary"}
                    value={entry.options.join(", ")}
                    onChange={(event) =>
                      update_entry(entry_index, {
                        options: event.target.value
                          .split(",")
                          .map((option_value) => option_value.trim())
                          .filter((option_value) => option_value.length > 0),
                      })
                    }
                  />
                </label>
              )}
              <label className="flex flex-col gap-0.5 text-xs">
                <span className="font-medium">Context</span>
                <textarea
                  className="min-h-[4rem] rounded-md border bg-background px-2 py-1 text-sm"
                  value={entry.context_definition}
                  onChange={(event) =>
                    update_entry(entry_index, {
                      context_definition: event.target.value,
                    })
                  }
                />
              </label>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => remove_entry(entry_index)}
              title="Remove label"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        onClick={add_entry}
        className="self-start"
      >
        <Plus className="mr-1 h-4 w-4" /> Add label
      </Button>
    </div>
  );
}
