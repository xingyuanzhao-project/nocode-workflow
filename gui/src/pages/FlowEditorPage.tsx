/**
 * Flow editor page — canvas, palette, property panel.
 *
 * Two entry modes:
 *
 * - ``"new"``: the caller has already populated the stores (via
 *   :class:`NewFlowDialog` or an import). The editor renders the
 *   canvas and a toolbar for saving / running / importing / exporting.
 * - ``"edit"``: loads the saved flow identified by ``:flow_id`` via
 *   ``GET /api/flow/:flow_id`` and pipes it through
 *   :func:`flowConfigToGraph` into the stores.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import {
  createFlow,
  getFlow,
  runAdhocFlow,
  updateFlow,
} from "@/api/flows";
import { FlowCanvas } from "@/flow_editor/canvas/FlowCanvas";
import { NodePalette } from "@/flow_editor/palette/NodePalette";
import { PropertyPanel } from "@/flow_editor/property_panel/PropertyPanel";
import { Button } from "@/components/ui/button";
import { CostEstimateDialog } from "@/components/CostEstimateDialog";
import { flowBodySchema } from "@/schemas/flow";
import { flowConfigToGraph } from "@/serialisation/flow_config_to_graph";
import { graphToFlowConfig } from "@/serialisation/graph_to_flow_config";
import {
  parseFlowYaml,
  stringifyFlowYaml,
} from "@/serialisation/yaml_codec";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useFlowSettingsStore } from "@/stores/flow_settings_store";
import { useGraphStore, useGraphHistory } from "@/stores/graph_store";
import { ApiError } from "@/api/client";

export interface FlowEditorPageProps {
  mode: "new" | "edit";
}

export default function FlowEditorPage({
  mode,
}: FlowEditorPageProps): JSX.Element {
  const navigate = useNavigate();
  const query_client = useQueryClient();
  const params = useParams<{ flow_id?: string }>();

  const [toolbar_error, set_toolbar_error] = useState<string | null>(null);
  const [show_cost_dialog, set_show_cost_dialog] = useState(false);
  const [pending_flow_body, set_pending_flow_body] =
    useState<Record<string, unknown> | null>(null);
  const import_input_ref = useRef<HTMLInputElement | null>(null);

  const { name, description, flow_id, is_dirty, set_metadata, set_name } =
    useFlowMetadataStore((state) => ({
      name: state.name,
      description: state.description,
      flow_id: state.flow_id,
      is_dirty: state.is_dirty,
      set_metadata: state.set_metadata,
      set_name: state.set_name,
    }));

  const flow_settings = useFlowSettingsStore((state) => ({
    schema_version: state.schema_version,
    processing_limit: state.processing_limit,
    async_config: state.async_config,
    logging_config: state.logging_config,
    display_config: state.display_config,
  }));
  const set_settings = useFlowSettingsStore((state) => state.set_settings);

  const handle_processing_limit_change = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const raw_value = event.target.value.trim();
      if (raw_value === "") {
        set_settings({ processing_limit: null });
        return;
      }
      const parsed_value = parseInt(raw_value, 10);
      if (!Number.isNaN(parsed_value) && parsed_value > 0) {
        set_settings({ processing_limit: parsed_value });
      }
    },
    [set_settings],
  );

  const nodes = useGraphStore((state) => state.nodes);
  const edges = useGraphStore((state) => state.edges);
  const set_graph = useGraphStore((state) => state.set_graph);
  const history = useGraphHistory();

  const saved_flow_query = useQuery({
    queryKey: ["flow", params.flow_id],
    queryFn: () => getFlow(params.flow_id as string),
    enabled: mode === "edit" && Boolean(params.flow_id),
  });

  useEffect(() => {
    if (mode !== "edit" || !saved_flow_query.data) {
      return;
    }
    const parsed_body = flowBodySchema.parse(saved_flow_query.data.flow);
    const graph_state = flowConfigToGraph(parsed_body);
    set_graph(graph_state.nodes, graph_state.edges);
    set_metadata({
      flow_id: saved_flow_query.data.id,
      name: graph_state.flow_metadata.name,
      description: graph_state.flow_metadata.description,
      is_dirty: false,
    });
    set_settings(graph_state.flow_settings);
  }, [mode, saved_flow_query.data, set_graph, set_metadata, set_settings]);

  const save_mutation = useMutation({
    mutationFn: async () => {
      const body = graphToFlowConfig(nodes, edges, {
        name,
        description,
        schema_version: flow_settings.schema_version,
        processing_limit: flow_settings.processing_limit,
        async_config: flow_settings.async_config,
        logging_config: flow_settings.logging_config,
        display_config: flow_settings.display_config,
      });
      const parsed_body = flowBodySchema.parse(body);
      if (flow_id) {
        const response = await updateFlow(flow_id, name, parsed_body);
        return response;
      }
      return createFlow(name, parsed_body);
    },
    onSuccess: (response) => {
      set_metadata({
        flow_id: response.id,
        name,
        description,
        is_dirty: false,
      });
      query_client.invalidateQueries({ queryKey: ["flow-list"] });
      if (!flow_id) {
        navigate(`/flows/${encodeURIComponent(response.id)}/edit`, {
          replace: true,
        });
      }
    },
    onError: (caught_error: unknown) => {
      set_toolbar_error(formatErrorMessage(caught_error));
    },
  });

  const run_mutation = useMutation({
    mutationFn: async () => {
      if (!pending_flow_body) {
        throw new Error("No flow body prepared for run.");
      }
      return runAdhocFlow(pending_flow_body);
    },
    onSuccess: (response) => {
      set_show_cost_dialog(false);
      set_pending_flow_body(null);
      navigate(`/runs/${encodeURIComponent(response.run_id)}`);
    },
    onError: (caught_error: unknown) => {
      set_toolbar_error(formatErrorMessage(caught_error));
      set_show_cost_dialog(false);
      set_pending_flow_body(null);
    },
  });

  const handle_run_click = useCallback(() => {
    try {
      const body = graphToFlowConfig(nodes, edges, {
        name,
        description,
        schema_version: flow_settings.schema_version,
        processing_limit: flow_settings.processing_limit,
        async_config: flow_settings.async_config,
        logging_config: flow_settings.logging_config,
        display_config: flow_settings.display_config,
      });
      const parsed_body = flowBodySchema.parse(body);
      set_pending_flow_body(parsed_body as Record<string, unknown>);
      set_show_cost_dialog(true);
      set_toolbar_error(null);
    } catch (caught_error) {
      set_toolbar_error(formatErrorMessage(caught_error));
    }
  }, [nodes, edges, name, description, flow_settings]);

  const handle_export_yaml = useCallback(() => {
    try {
      const body = graphToFlowConfig(nodes, edges, {
        name,
        description,
        schema_version: flow_settings.schema_version,
        processing_limit: flow_settings.processing_limit,
        async_config: flow_settings.async_config,
        logging_config: flow_settings.logging_config,
        display_config: flow_settings.display_config,
      });
      const yaml_text = stringifyFlowYaml(flowBodySchema.parse(body));
      const blob = new Blob([yaml_text], { type: "text/yaml" });
      const object_url = URL.createObjectURL(blob);
      const anchor_element = document.createElement("a");
      anchor_element.href = object_url;
      anchor_element.download = `${name || "flow"}.yml`;
      anchor_element.click();
      URL.revokeObjectURL(object_url);
      set_toolbar_error(null);
    } catch (caught_error) {
      set_toolbar_error(formatErrorMessage(caught_error));
    }
  }, [nodes, edges, name, description, flow_settings]);

  const handle_import_yaml = useCallback(
    async (file: File) => {
      try {
        const yaml_text = await file.text();
        const parsed_body = parseFlowYaml(yaml_text);
        const graph_state = flowConfigToGraph(parsed_body);
        set_graph(graph_state.nodes, graph_state.edges);
        set_metadata({
          flow_id: null,
          name: graph_state.flow_metadata.name,
          description: graph_state.flow_metadata.description,
          is_dirty: true,
        });
        set_settings(graph_state.flow_settings);
        history.clear_history();
        set_toolbar_error(null);
      } catch (caught_error) {
        set_toolbar_error(formatErrorMessage(caught_error));
      }
    },
    [set_graph, set_metadata, set_settings, history],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm font-medium min-w-[16rem]"
          value={name}
          placeholder="Flow name"
          onChange={(event) => set_name(event.target.value)}
        />
        <span className="text-xs text-muted-foreground">
          {is_dirty ? "unsaved changes" : flow_id ? "saved" : "new"}
        </span>
        <div className="flex items-center gap-1.5 rounded-md border px-2 py-1">
          <label
            htmlFor="processing-limit-input"
            className="text-xs text-muted-foreground whitespace-nowrap"
          >
            Limit
          </label>
          <input
            id="processing-limit-input"
            type="number"
            min={1}
            className="w-20 rounded border bg-background px-1.5 py-0.5 text-xs tabular-nums"
            placeholder="All"
            value={
              flow_settings.processing_limit !== null
                ? String(flow_settings.processing_limit)
                : ""
            }
            onChange={handle_processing_limit_change}
            title="Max entities/rows to process (leave empty for all)"
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={history.undo}
            disabled={!history.can_undo}
          >
            Undo
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={history.redo}
            disabled={!history.can_redo}
          >
            Redo
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => import_input_ref.current?.click()}
          >
            Import YAML
          </Button>
          <input
            ref={import_input_ref}
            type="file"
            accept=".yml,.yaml,text/yaml"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                void handle_import_yaml(file);
              }
              event.target.value = "";
            }}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handle_export_yaml}
          >
            Export YAML
          </Button>
          <Button
            size="sm"
            onClick={() => save_mutation.mutate()}
            disabled={save_mutation.isPending || !name.trim()}
          >
            {save_mutation.isPending
              ? "Saving..."
              : flow_id
                ? "Save"
                : "Save new"}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={handle_run_click}
            disabled={run_mutation.isPending}
          >
            {run_mutation.isPending ? "Submitting..." : "Run"}
          </Button>
        </div>
      </div>
      {toolbar_error ? (
        <div className="border-b bg-destructive/10 px-4 py-2 text-xs text-destructive">
          {toolbar_error}
        </div>
      ) : null}
      <div className="flex flex-1 overflow-hidden">
        <NodePalette />
        <div className="flex-1 overflow-hidden">
          <FlowCanvas />
        </div>
        <PropertyPanel />
      </div>
      {show_cost_dialog && pending_flow_body ? (
        <CostEstimateDialog
          flow_body={pending_flow_body}
          on_confirm={() => run_mutation.mutate()}
          on_cancel={() => {
            set_show_cost_dialog(false);
            set_pending_flow_body(null);
          }}
        />
      ) : null}
    </div>
  );
}

function formatErrorMessage(caught_error: unknown): string {
  if (caught_error instanceof ApiError) {
    if (caught_error.errors?.errors.length) {
      return caught_error.errors.errors
        .map((issue) => issue.msg)
        .join("; ");
    }
    return caught_error.message;
  }
  if (caught_error instanceof Error) {
    return caught_error.message;
  }
  return String(caught_error);
}
