/**
 * Config-tab form for ``category=processor`` nodes.
 *
 * Edits: ``unit`` and ``group_by``. Prompt instructions and output
 * schema live on their own tabs.
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
});
type ProcessorFormValues = z.infer<typeof processorFormSchema>;

export interface ProcessingConfigFormProps {
  node: GraphNode;
}

function readInitialValues(node: GraphNode): ProcessorFormValues {
  const data = node.data;
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
  };
}

export function ProcessingConfigForm({
  node,
}: ProcessingConfigFormProps): JSX.Element {
  const form = useForm<ProcessorFormValues>({
    resolver: zodResolver(processorFormSchema),
    defaultValues: readInitialValues(node),
  });

  useEffect(() => {
    form.reset(readInitialValues(node));
  }, [node.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useAutoSaveNodeData(node.id, form.watch);

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
    </form>
  );
}
