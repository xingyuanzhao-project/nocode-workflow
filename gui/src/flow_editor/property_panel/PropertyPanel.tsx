/**
 * Right-hand property panel for the selected node.
 *
 * Dispatches on :attr:`NodeTypeEntry.category` and ``node_type_id``
 * to render:
 *
 * - A Config tab every node gets (see :mod:`./ConfigTab`).
 * - An IO Schema tab shown only for processor nodes (see
 *   :mod:`./IOSchemaTab`).
 * - A Prompt tab shown only for processor nodes (see
 *   :mod:`./PromptTab`).
 *
 * The panel is entirely driven by :mod:`@/stores/graph_store`:
 * it reads the selected node's ``data`` and writes changes through
 * ``update_node_data``.
 */

import { useMemo } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

import { ConfigTab } from "./ConfigTab";
import { IOSchemaTab } from "./IOSchemaTab";
import { PromptTab } from "./PromptTab";

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
        <Tabs defaultValue="config" className="flex min-h-0 flex-1 flex-col">
          <div className="border-b px-4 py-2">
            <TabsList>
              <TabsTrigger value="config">Config</TabsTrigger>
              <TabsTrigger value="output_schema">Output Schema</TabsTrigger>
              <TabsTrigger value="prompt">Prompt</TabsTrigger>
            </TabsList>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <TabsContent value="config" className="mt-0">
              <ConfigTab node={selected_node} />
            </TabsContent>
            <TabsContent value="output_schema" className="mt-0">
              <IOSchemaTab node={selected_node} />
            </TabsContent>
            <TabsContent value="prompt" className="mt-0">
              <PromptTab node={selected_node} />
            </TabsContent>
          </div>
        </Tabs>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <ConfigTab node={selected_node} />
        </div>
      )}
    </aside>
  );
}
