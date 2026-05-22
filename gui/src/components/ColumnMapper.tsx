/**
 * Maps the user's CSV column names to the flow's internal role fields.
 *
 * The four required roles (:attr:`src.flow_loader.ColumnRoles.text`,
 * ``entity_id``, ``doc_id``, ``sort_by``) are rendered as selects
 * whose options are the columns of the latest upload. The component
 * is purely controlled: the parent owns the mapping object and the
 * list of available columns.
 */

import { useMemo } from "react";

import type { CSVColumnDescriptor } from "@/schemas/files";
import type { ColumnRoles } from "@/schemas/flow";

export interface ColumnMapperProps {
  /** Columns the user's uploaded CSV exposes. */
  columns: CSVColumnDescriptor[];
  /** Current mapping. ``null`` entries are rendered as "unset". */
  column_roles: Partial<ColumnRoles>;
  /** Patch the mapping one role at a time. */
  on_change: (
    role_name: keyof ColumnRoles,
    column_name: string,
  ) => void;
  /** Disable every select (for example in a readonly node). */
  disabled?: boolean;
}

const ROLE_DEFINITIONS: Array<{
  role: keyof ColumnRoles;
  label: string;
  description: string;
  is_required: boolean;
}> = [
  {
    role: "text",
    label: "Document text",
    description: "Column holding the raw text the LLM summarises.",
    is_required: true,
  },
  {
    role: "entity_id",
    label: "Entity id",
    description: "Column grouping documents that belong to the same entity.",
    is_required: true,
  },
  {
    role: "doc_id",
    label: "Document id",
    description: "Column uniquely identifying each row.",
    is_required: true,
  },
  {
    role: "sort_by",
    label: "Sort within entity",
    description: "Column used to order documents within an entity.",
    is_required: true,
  },
];

/**
 * Four-select widget for the required column roles.
 */
export function ColumnMapper({
  columns,
  column_roles,
  on_change,
  disabled = false,
}: ColumnMapperProps): JSX.Element {
  const column_names = useMemo(
    () => columns.map((column) => column.name),
    [columns],
  );

  if (column_names.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Upload a CSV to map columns.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {ROLE_DEFINITIONS.map(({ role, label, description, is_required }) => {
        const selected_column = column_roles[role] ?? "";
        return (
          <label key={role} className="flex flex-col gap-0.5 text-xs">
            <span className="font-medium">
              {label}
              {is_required ? (
                <span className="ml-1 text-destructive">*</span>
              ) : null}
            </span>
            <span className="text-muted-foreground">{description}</span>
            <select
              value={selected_column}
              disabled={disabled}
              onChange={(event) => on_change(role, event.target.value)}
              className="mt-1 w-full rounded-md border bg-background px-2 py-1 text-sm"
            >
              <option value="">— pick a column —</option>
              {column_names.map((column_name) => (
                <option key={column_name} value={column_name}>
                  {column_name}
                </option>
              ))}
            </select>
          </label>
        );
      })}
    </div>
  );
}
