/**
 * Config tab of the :mod:`PropertyPanel`.
 *
 * Dispatches on the selected node's ``node_type_id`` to the right
 * config form. Every form writes its values back to the graph
 * store via :mod:`./node_update_helpers`.
 */

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { listTaxonomies } from "@/api/taxonomies";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";
import { DataSourceConfigForm } from "./config_forms/DataSourceConfigForm";
import { LLMProviderConfigForm } from "./config_forms/LLMProviderConfigForm";
import { ProcessingConfigForm } from "./config_forms/ProcessingConfigForm";

function CodebookSelectorForm({ node }: { node: GraphNode }): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);
  const codebooks_query = useQuery({
    queryKey: ["taxonomy-list"],
    queryFn: listTaxonomies,
    staleTime: 30_000,
  });

  const selected_id =
    typeof node.data.codebook_id === "string" ? node.data.codebook_id : "";

  const on_change = useCallback(
    (next_id: string) => {
      update_node_data(node.id, {
        codebook_id: next_id || null,
        codebook_path: null,
      });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const items = useMemo(
    () => (Array.isArray(codebooks_query.data) ? codebooks_query.data : []),
    [codebooks_query.data],
  );

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Codebook</span>
        <select
          className="rounded-md border bg-background px-2 py-1 text-sm"
          value={selected_id}
          onChange={(event) => on_change(event.target.value)}
        >
          <option value="">Select a codebook...</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground">
          Choose from your saved codebooks (Menu &rarr; Codebook).
        </span>
      </label>
    </div>
  );
}

function OutputConfigForm({ node }: { node: GraphNode }): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  const output_path =
    typeof node.data.output_path === "string" ? node.data.output_path : "";
  const output_fields = Array.isArray(node.data.output_fields)
    ? (node.data.output_fields as string[]).filter(Boolean)
    : ["summary"];
  const extend = node.data.extend === true;

  const on_output_path_change = useCallback(
    (value: string) => {
      update_node_data(node.id, { output_path: value });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const on_extend_change = useCallback(
    (checked: boolean) => {
      update_node_data(node.id, { extend: checked });
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const on_add_output_field = useCallback(() => {
    update_node_data(node.id, {
      output_fields: [...output_fields, ""],
    });
    set_dirty(true);
  }, [node.id, output_fields, update_node_data, set_dirty]);

  const on_remove_output_field = useCallback(
    (index: number) => {
      if (output_fields.length <= 1) return;
      update_node_data(node.id, {
        output_fields: output_fields.filter((_, i) => i !== index),
      });
      set_dirty(true);
    },
    [node.id, output_fields, update_node_data, set_dirty],
  );

  const on_output_field_change = useCallback(
    (index: number, value: string) => {
      const next = output_fields.map((f, i) => (i === index ? value : f));
      update_node_data(node.id, { output_fields: next });
      set_dirty(true);
    },
    [node.id, output_fields, update_node_data, set_dirty],
  );

  return (
    <div className="flex flex-col gap-3 text-xs">
      <label className="flex flex-col gap-1">
        <span className="font-medium">Output path</span>
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm"
          placeholder="results/output.csv"
          value={output_path}
          onChange={(event) => on_output_path_change(event.target.value)}
        />
      </label>
      <div className="flex flex-col gap-1">
        <span className="font-medium">Output Fields</span>
        {output_fields.map((field, index) => (
          <div key={index} className="flex items-center gap-1">
            <input
              className="flex-1 rounded-md border bg-background px-2 py-1 text-sm"
              placeholder="e.g. summary"
              value={field}
              onChange={(event) =>
                on_output_field_change(index, event.target.value)
              }
            />
            {output_fields.length > 1 && (
              <button
                type="button"
                className="rounded-md border px-1.5 py-1 text-sm text-muted-foreground hover:text-foreground"
                title="Remove field"
                onClick={() => on_remove_output_field(index)}
              >
                &times;
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          className="mt-1 w-fit rounded-md border bg-secondary px-2 py-1 text-secondary-foreground hover:bg-accent"
          onClick={on_add_output_field}
        >
          + Add Field
        </button>
        <span className="text-muted-foreground">
          Field names become column headers in the output CSV.
        </span>
      </div>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={extend}
          onChange={(event) => on_extend_change(event.target.checked)}
        />
        <span className="font-medium">Append to existing file</span>
      </label>
    </div>
  );
}

export interface ConfigTabProps {
  node: GraphNode;
}

export function ConfigTab({ node }: ConfigTabProps): JSX.Element {
  const node_type_id = String(node.data.node_type_id ?? "");
  const category = String(node.data.category ?? "");

  if (node_type_id === "csv_input" || node_type_id === "json_input") {
    return <DataSourceConfigForm node={node} />;
  }
  if (node_type_id === "llm_call") {
    return <LLMProviderConfigForm node={node} />;
  }
  if (node_type_id === "codebook") {
    return <CodebookSelectorForm node={node} />;
  }
  if (node_type_id === "csv_output" || node_type_id === "json_output") {
    return <OutputConfigForm node={node} />;
  }
  if (category === "processor") {
    return <ProcessingConfigForm node={node} />;
  }
  return (
    <p className="text-xs text-muted-foreground">
      Node type {node_type_id} has no configuration fields.
    </p>
  );
}
