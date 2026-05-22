/**
 * Generic property form for nodes whose configuration is a small
 * set of top-level string / boolean fields (Taxonomy, Prompts,
 * CSVOutput, GroupBy).
 *
 * Each :class:`FieldDefinition` declares one field with its type,
 * label, and help text. The form wires the inputs to the graph
 * store through :func:`useAutoSaveNodeData` so edits propagate
 * with the same lifecycle as the RHF-based forms.
 */

import { useEffect } from "react";
import { useForm, type FieldValues } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { useAutoSaveNodeData } from "../node_update_helpers";
import type { GraphNode } from "@/stores/graph_store";

export type FieldKind = "text" | "boolean" | "textarea";

export interface FieldDefinition {
  /** Key on the node's ``data`` payload. */
  field_name: string;
  /** Visible label above the input. */
  label: string;
  /** Optional placeholder text. */
  placeholder?: string;
  /** Optional help text shown under the input. */
  help?: string;
  /** Form input kind; defaults to ``"text"``. */
  kind?: FieldKind;
  /** When ``true``, the field is shown as nullable (empty ≡ ``null``). */
  nullable?: boolean;
}

interface SimpleStringFieldFormProps {
  node: GraphNode;
  fields: readonly FieldDefinition[];
}

function buildSchema(
  fields: readonly FieldDefinition[],
): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const field of fields) {
    if (field.kind === "boolean") {
      shape[field.field_name] = z.boolean();
    } else if (field.nullable) {
      shape[field.field_name] = z.string().nullable();
    } else {
      shape[field.field_name] = z.string();
    }
  }
  return z.object(shape);
}

function readInitialValues(
  node: GraphNode,
  fields: readonly FieldDefinition[],
): FieldValues {
  const values: FieldValues = {};
  for (const field of fields) {
    const raw_value = node.data[field.field_name];
    if (field.kind === "boolean") {
      values[field.field_name] =
        typeof raw_value === "boolean" ? raw_value : false;
    } else if (typeof raw_value === "string") {
      values[field.field_name] = raw_value;
    } else {
      values[field.field_name] = field.nullable ? null : "";
    }
  }
  return values;
}

export function SimpleStringFieldForm({
  node,
  fields,
}: SimpleStringFieldFormProps): JSX.Element {
  const form_schema = buildSchema(fields);
  const form = useForm<FieldValues>({
    resolver: zodResolver(form_schema),
    defaultValues: readInitialValues(node, fields),
  });

  useEffect(() => {
    form.reset(readInitialValues(node, fields));
  }, [node.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useAutoSaveNodeData(node.id, form.watch);

  return (
    <form className="flex flex-col gap-3">
      {fields.map((field) => {
        if (field.kind === "boolean") {
          return (
            <label
              key={field.field_name}
              className="flex items-center gap-2 text-xs"
            >
              <input
                type="checkbox"
                className="h-4 w-4 rounded border"
                {...form.register(field.field_name)}
              />
              <span className="font-medium">{field.label}</span>
              {field.help ? (
                <span className="text-muted-foreground">{field.help}</span>
              ) : null}
            </label>
          );
        }
        const current_value = form.watch(field.field_name);
        return (
          <label
            key={field.field_name}
            className="flex flex-col gap-1 text-xs"
          >
            <span className="font-medium">{field.label}</span>
            {field.kind === "textarea" ? (
              <textarea
                className="min-h-[6rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
                placeholder={field.placeholder}
                value={typeof current_value === "string" ? current_value : ""}
                onChange={(event) =>
                  form.setValue(
                    field.field_name,
                    field.nullable && event.target.value === ""
                      ? null
                      : event.target.value,
                    { shouldDirty: true },
                  )
                }
              />
            ) : (
              <input
                className="rounded-md border bg-background px-2 py-1 text-sm"
                placeholder={field.placeholder}
                value={typeof current_value === "string" ? current_value : ""}
                onChange={(event) =>
                  form.setValue(
                    field.field_name,
                    field.nullable && event.target.value === ""
                      ? null
                      : event.target.value,
                    { shouldDirty: true },
                  )
                }
              />
            )}
            {field.help ? (
              <span className="text-muted-foreground">{field.help}</span>
            ) : null}
          </label>
        );
      })}
    </form>
  );
}
