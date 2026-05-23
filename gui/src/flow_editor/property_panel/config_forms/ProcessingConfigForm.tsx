/**
 * Config-tab form for ``category=processor`` nodes.
 *
 * Currently the only processing unit is ``row``. This form is a
 * placeholder that shows the unit as read-only.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAutoSaveNodeData } from "../node_update_helpers";
import type { GraphNode } from "@/stores/graph_store";

const processorFormSchema = z.object({
  unit: z.literal("row"),
});
type ProcessorFormValues = z.infer<typeof processorFormSchema>;

export interface ProcessingConfigFormProps {
  node: GraphNode;
}

export function ProcessingConfigForm({
  node,
}: ProcessingConfigFormProps): JSX.Element {
  const form = useForm<ProcessorFormValues>({
    resolver: zodResolver(processorFormSchema),
    defaultValues: { unit: "row" },
  });

  useEffect(() => {
    form.reset({ unit: "row" });
  }, [node.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useAutoSaveNodeData(node.id, form.watch);

  return (
    <form className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Unit</span>
        <select
          className="rounded-md border bg-background px-2 py-1 text-sm"
          {...form.register("unit")}
          disabled
        >
          <option value="row">row</option>
        </select>
      </label>
    </form>
  );
}
