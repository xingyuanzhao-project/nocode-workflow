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

  return (
    <aside className="flex h-full w-96 shrink-0 flex-col border-l bg-background">
      <div className="border-b px-4 py-3">
        <div className="text-[0.65rem] font-mono uppercase tracking-wide text-muted-foreground">
          {category || "Node"}
        </div>
        <h2 className="text-sm font-semibold">{label}</h2>
        <div className="text-xs text-muted-foreground">{node_type_id}</div>
      </div>
      <Tabs defaultValue="config" className="flex flex-1 flex-col">
        <div className="border-b px-4 py-2">
          <TabsList>
            <TabsTrigger value="config">Config</TabsTrigger>
            <TabsTrigger value="io_schema" disabled={!is_processor_node}>
              IO Schema
            </TabsTrigger>
            <TabsTrigger value="prompt" disabled={!is_processor_node}>
              Prompt
            </TabsTrigger>
          </TabsList>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <TabsContent value="config" className="mt-0">
            <ConfigTab node={selected_node} />
          </TabsContent>
          <TabsContent value="io_schema" className="mt-0">
            {is_processor_node ? (
              <IOSchemaTab node={selected_node} />
            ) : (
              <p className="text-xs text-muted-foreground">
                IO schema is only editable on processor nodes.
              </p>
            )}
          </TabsContent>
          <TabsContent value="prompt" className="mt-0">
            {is_processor_node ? (
              <PromptTab node={selected_node} />
            ) : (
              <p className="text-xs text-muted-foreground">
                Prompt overrides are only editable on processor nodes.
              </p>
            )}
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  );
}
