/**
 * Config-tab form for every ``category=processor`` node.
 *
 * Edits the fields :mod:`src.flow_loader.StepConfig` cares about:
 * ``unit``, ``group_by``, ``llm``, ``mode``, ``keys``. IO schema
 * and prompt overrides live on their own tabs.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAutoSaveNodeData } from "../node_update_helpers";
import type { GraphNode } from "@/stores/graph_store";
import { unitValueSchema } from "@/schemas/node_types";

const processorFormSchema = z.object({
  unit: unitValueSchema,
  group_by: z.string().nullable(),
  llm_resource_id: z.string().nullable(),
  mode: z.string().nullable(),
  keys: z.string().nullable(),
});
type ProcessorFormValues = z.infer<typeof processorFormSchema>;

const MODE_NODE_TYPE_IDS: ReadonlySet<string> = new Set([
  "label_summary",
]);

const KEYS_NODE_TYPE_IDS: ReadonlySet<string> = new Set([
  "classification",
]);

export interface ProcessingConfigFormProps {
  node: GraphNode;
}

function readInitialValues(node: GraphNode): ProcessorFormValues {
  const data = node.data;
  const raw_keys = data.keys;
  const keys_string =
    raw_keys === null || raw_keys === undefined
      ? null
      : typeof raw_keys === "string"
        ? raw_keys
        : JSON.stringify(raw_keys);
  return {
    unit:
      typeof data.unit === "string" &&
      (data.unit === "row" || data.unit === "document" || data.unit === "entity")
        ? (data.unit as ProcessorFormValues["unit"])
        : (typeof data.default_unit === "string" &&
            (data.default_unit === "row" ||
              data.default_unit === "document" ||
              data.default_unit === "entity")
            ? (data.default_unit as ProcessorFormValues["unit"])
            : "row"),
    group_by:
      typeof data.group_by === "string"
        ? data.group_by
        : typeof data.default_group_by === "string"
          ? data.default_group_by
          : null,
    llm_resource_id:
      typeof data.llm_resource_id === "string" && data.llm_resource_id.length > 0
        ? data.llm_resource_id
        : null,
    mode: typeof data.mode === "string" ? data.mode : null,
    keys: keys_string,
  };
}

export function ProcessingConfigForm({
  node,
}: ProcessingConfigFormProps): JSX.Element {
  const node_type_id = String(node.data.node_type_id ?? "");
  const form = useForm<ProcessorFormValues>({
    resolver: zodResolver(processorFormSchema),
    defaultValues: readInitialValues(node),
  });

  useEffect(() => {
    form.reset(readInitialValues(node));
  }, [node.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useAutoSaveNodeData(node.id, form.watch);

  const show_mode = MODE_NODE_TYPE_IDS.has(node_type_id);
  const show_keys = KEYS_NODE_TYPE_IDS.has(node_type_id);

  return (
    <form className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Unit</span>
        <select
          className="rounded-md border bg-background px-2 py-1 text-sm"
          {...form.register("unit")}
        >
          <option value="row">row</option>
          <option value="document">document</option>
          <option value="entity">entity</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Group by</span>
        <select
          className="rounded-md border bg-background px-2 py-1 text-sm"
          value={form.watch("group_by") ?? ""}
          onChange={(event) =>
            form.setValue(
              "group_by",
              event.target.value === "" ? null : event.target.value,
              { shouldDirty: true },
            )
          }
        >
          <option value="">(none)</option>
          <option value="entity">entity</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">LLM resource id</span>
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm"
          placeholder="default (leave blank)"
          value={form.watch("llm_resource_id") ?? ""}
          onChange={(event) =>
            form.setValue(
              "llm_resource_id",
              event.target.value === "" ? null : event.target.value,
              { shouldDirty: true },
            )
          }
        />
        <span className="text-muted-foreground">
          Resource id (matches one of the LLMProvider nodes). Leave
          blank to use the resource named <code>default</code>.
        </span>
      </label>

      {show_mode ? (
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">Mode</span>
          <select
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={form.watch("mode") ?? ""}
            onChange={(event) =>
              form.setValue(
                "mode",
                event.target.value === "" ? null : event.target.value,
                { shouldDirty: true },
              )
            }
          >
            <option value="">(none)</option>
            <option value="hybrid">hybrid</option>
            <option value="full_async">full_async</option>
          </select>
        </label>
      ) : null}

      {show_keys ? (
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">Keys</span>
          <input
            className="rounded-md border bg-background px-2 py-1 text-sm"
            placeholder='"all" or ["key1","key2"]'
            value={form.watch("keys") ?? ""}
            onChange={(event) =>
              form.setValue(
                "keys",
                event.target.value === "" ? null : event.target.value,
                { shouldDirty: true },
              )
            }
          />
          <span className="text-muted-foreground">
            Either the literal string <code>all</code> or a JSON array of
            taxonomy keys.
          </span>
        </label>
      ) : null}
    </form>
  );
}
