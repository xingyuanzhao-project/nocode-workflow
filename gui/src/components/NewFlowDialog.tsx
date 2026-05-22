/**
 * "New flow" dialog shown from the My Flows page.
 *
 * Lists the preset templates returned by ``GET /api/flow/templates``
 * plus a "Blank canvas" option. Picking one takes the user to
 * ``/flows/new`` with the chosen template body loaded into the
 * graph store via :func:`flowConfigToGraph`.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getFlowTemplate, listFlowTemplates } from "@/api/templates";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { flowBodySchema } from "@/schemas/flow";
import { flowConfigToGraph } from "@/serialisation/flow_config_to_graph";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useFlowSettingsStore } from "@/stores/flow_settings_store";
import { useGraphStore } from "@/stores/graph_store";
import { cn } from "@/lib/utils";

const BLANK_TEMPLATE_ID = "__blank__";

export interface NewFlowDialogProps {
  open: boolean;
  on_open_change: (open: boolean) => void;
}

export function NewFlowDialog({
  open,
  on_open_change,
}: NewFlowDialogProps): JSX.Element {
  const navigate = useNavigate();
  const templates_query = useQuery({
    queryKey: ["flow-templates"],
    queryFn: listFlowTemplates,
    staleTime: 5 * 60_000,
  });
  const [selected_template_id, set_selected_template_id] = useState<string>(
    BLANK_TEMPLATE_ID,
  );
  const [is_loading, set_is_loading] = useState(false);
  const [load_error, set_load_error] = useState<string | null>(null);

  const set_graph = useGraphStore((state) => state.set_graph);
  const set_metadata = useFlowMetadataStore((state) => state.set_metadata);
  const set_settings = useFlowSettingsStore((state) => state.set_settings);
  const reset_settings = useFlowSettingsStore(
    (state) => state.reset_settings,
  );

  const handle_create = async (): Promise<void> => {
    set_load_error(null);
    set_is_loading(true);
    try {
      if (selected_template_id === BLANK_TEMPLATE_ID) {
        set_graph([], []);
        set_metadata({
          flow_id: null,
          name: "Untitled flow",
          description: "",
          is_dirty: false,
        });
        reset_settings();
      } else {
        const template = await getFlowTemplate(selected_template_id);
        const parsed_body = flowBodySchema.parse(template.flow);
        const graph_state = flowConfigToGraph(parsed_body);
        set_graph(graph_state.nodes, graph_state.edges);
        set_metadata({
          flow_id: null,
          name: graph_state.flow_metadata.name,
          description: graph_state.flow_metadata.description,
          is_dirty: true,
        });
        set_settings(graph_state.flow_settings);
      }
      on_open_change(false);
      navigate("/flows/new");
    } catch (caught_error) {
      set_load_error(
        caught_error instanceof Error
          ? caught_error.message
          : String(caught_error),
      );
    } finally {
      set_is_loading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={on_open_change}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create a new flow</DialogTitle>
          <DialogDescription>
            Start from a preset template or begin with a blank canvas.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          {templates_query.isLoading ? (
            <div className="text-sm text-muted-foreground">
              Loading templates...
            </div>
          ) : templates_query.isError ? (
            <div className="text-sm text-destructive">
              Could not load templates.
            </div>
          ) : (
            <>
              {(templates_query.data ?? []).map((template_item) => (
                <label
                  key={template_item.id}
                  className={cn(
                    "flex cursor-pointer flex-col gap-0.5 rounded-md border p-3",
                    selected_template_id === template_item.id
                      ? "border-primary bg-accent"
                      : "hover:bg-accent",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="template"
                      checked={selected_template_id === template_item.id}
                      onChange={() =>
                        set_selected_template_id(template_item.id)
                      }
                    />
                    <span className="font-medium">{template_item.label}</span>
                  </div>
                  <p className="ml-6 text-xs text-muted-foreground">
                    {template_item.description}
                  </p>
                </label>
              ))}
              <label
                className={cn(
                  "flex cursor-pointer flex-col gap-0.5 rounded-md border p-3",
                  selected_template_id === BLANK_TEMPLATE_ID
                    ? "border-primary bg-accent"
                    : "hover:bg-accent",
                )}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="template"
                    checked={selected_template_id === BLANK_TEMPLATE_ID}
                    onChange={() =>
                      set_selected_template_id(BLANK_TEMPLATE_ID)
                    }
                  />
                  <span className="font-medium">Blank canvas</span>
                </div>
                <p className="ml-6 text-xs text-muted-foreground">
                  Start from scratch.
                </p>
              </label>
            </>
          )}
          {load_error ? (
            <div className="text-xs text-destructive">{load_error}</div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => on_open_change(false)}
            disabled={is_loading}
          >
            Cancel
          </Button>
          <Button onClick={handle_create} disabled={is_loading}>
            {is_loading ? "Loading..." : "Create flow"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
