/**
 * Left-hand palette of draggable node types.
 *
 * Driven by :func:`@/hooks/use_node_types.useNodeTypes`; the palette
 * renders one section per :class:`NodeTypeCategory` and one button
 * per :class:`NodeTypeEntry`. Users drag a palette entry onto the
 * canvas; :mod:`@/flow_editor/canvas/FlowCanvas` reads the
 * ``application/agent_paper_node_type`` dataTransfer string and
 * appends a new node to the graph store.
 */

import type { DragEvent } from "react";

import { cn } from "@/lib/utils";
import {
  groupNodeEntriesByCategory,
  useNodeTypes,
} from "@/hooks/use_node_types";
import type {
  NodeTypeCategory,
  NodeTypeEntry,
} from "@/schemas/node_types";

/** MIME type used by the palette/canvas drag-and-drop protocol. */
export const NODE_TYPE_DRAG_MIME_TYPE = "application/agent_paper_node_type";

const CATEGORY_LABELS: Record<NodeTypeCategory, string> = {
  data: "Data",
  processor: "Processing",
  resource: "Resources",
};

const CATEGORY_DISPLAY_ORDER: readonly NodeTypeCategory[] = [
  "data",
  "processor",
  "resource",
] as const;

function onPaletteEntryDragStart(
  event: DragEvent<HTMLButtonElement>,
  entry: NodeTypeEntry,
): void {
  event.dataTransfer.setData(NODE_TYPE_DRAG_MIME_TYPE, entry.id);
  event.dataTransfer.effectAllowed = "move";
}

/**
 * Left panel showing every palette entry grouped by category.
 */
export function NodePalette(): JSX.Element {
  const node_types_query = useNodeTypes();

  if (node_types_query.isLoading) {
    return (
      <aside className="flex h-full w-64 shrink-0 items-center justify-center border-r bg-background text-sm text-muted-foreground">
        Loading nodes...
      </aside>
    );
  }
  if (node_types_query.isError || !node_types_query.data) {
    return (
      <aside className="flex h-full w-64 shrink-0 items-center justify-center border-r bg-background px-3 text-center text-sm text-destructive">
        Failed to load node types.
      </aside>
    );
  }

  const grouped_entries = groupNodeEntriesByCategory(node_types_query.data);

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col gap-4 overflow-y-auto border-r bg-background p-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Palette
      </h2>
      {CATEGORY_DISPLAY_ORDER.map((category) => {
        const entries = grouped_entries[category] ?? [];
        if (entries.length === 0) {
          return null;
        }
        return (
          <section key={category} className="flex flex-col gap-2">
            <h3 className="text-xs font-medium text-muted-foreground">
              {CATEGORY_LABELS[category]}
            </h3>
            <div className="flex flex-col gap-1.5">
              {entries.map((entry) => (
                <PaletteEntryButton key={entry.id} entry={entry} />
              ))}
            </div>
          </section>
        );
      })}
    </aside>
  );
}

interface PaletteEntryButtonProps {
  entry: NodeTypeEntry;
}

function PaletteEntryButton({ entry }: PaletteEntryButtonProps): JSX.Element {
  return (
    <button
      type="button"
      draggable
      onDragStart={(event) => onPaletteEntryDragStart(event, entry)}
      title={entry.description || entry.label}
      className={cn(
        "group flex cursor-grab flex-col items-start gap-0.5 rounded-md border bg-card px-3 py-2 text-left shadow-sm transition-colors",
        "hover:bg-accent active:cursor-grabbing",
      )}
    >
      <span className="text-sm font-medium">{entry.label || entry.id}</span>
      <span className="text-[0.65rem] font-mono text-muted-foreground">
        {entry.id}
      </span>
    </button>
  );
}
