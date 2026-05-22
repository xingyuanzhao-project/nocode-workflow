/**
 * Saved-flow list page.
 *
 * Shows every flow saved in the user's workspace (including any that
 * were seeded at first launch). "New blank flow" opens the editor
 * with an empty canvas.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

import {
  deleteFlow,
  duplicateFlow,
  listFlows,
} from "@/api/flows";
import { Button } from "@/components/ui/button";
import type { FlowListItem } from "@/schemas/flow";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useFlowSettingsStore } from "@/stores/flow_settings_store";
import { useGraphStore } from "@/stores/graph_store";

const FLOW_LIST_QUERY_KEY = ["flow-list"] as const;

export default function MyFlowsPage(): JSX.Element {
  const navigate = useNavigate();
  const query_client = useQueryClient();

  const set_graph = useGraphStore((state) => state.set_graph);
  const set_metadata = useFlowMetadataStore((state) => state.set_metadata);
  const reset_settings = useFlowSettingsStore((state) => state.reset_settings);

  const flow_list_query = useQuery({
    queryKey: FLOW_LIST_QUERY_KEY,
    queryFn: listFlows,
    staleTime: 30_000,
  });

  const duplicate_mutation = useMutation({
    mutationFn: ({
      flow_id,
      new_name,
    }: {
      flow_id: string;
      new_name: string;
    }) => duplicateFlow(flow_id, new_name),
    onSuccess: () => {
      query_client.invalidateQueries({ queryKey: FLOW_LIST_QUERY_KEY });
    },
  });

  const delete_mutation = useMutation({
    mutationFn: (flow_id: string) => deleteFlow(flow_id),
    onSuccess: () => {
      query_client.invalidateQueries({ queryKey: FLOW_LIST_QUERY_KEY });
    },
  });

  const handle_new_blank_flow = () => {
    set_graph([], []);
    set_metadata({
      flow_id: null,
      name: "Untitled flow",
      description: "",
      is_dirty: false,
    });
    reset_settings();
    navigate("/flows/new");
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <h1 className="text-lg font-semibold">My flows</h1>
        <Button onClick={handle_new_blank_flow}>
          <Plus className="mr-1 h-4 w-4" /> New blank flow
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {flow_list_query.isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : flow_list_query.isError ? (
          <div className="text-sm text-destructive">
            Could not load flows: {String(flow_list_query.error)}
          </div>
        ) : (flow_list_query.data ?? []).length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No saved flows yet. Click &quot;New blank flow&quot; to create one.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">Name</th>
                <th className="py-2 pr-3 font-medium">Description</th>
                <th className="py-2 pr-3 font-medium">Updated</th>
                <th className="py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(flow_list_query.data ?? []).map((flow_item: FlowListItem) => (
                <tr key={flow_item.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-medium">{flow_item.name}</td>
                  <td className="py-2 pr-3 text-muted-foreground">
                    {flow_item.description}
                  </td>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">
                    {new Date(flow_item.updated_at).toLocaleString()}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          navigate(
                            `/flows/${encodeURIComponent(flow_item.id)}/edit`,
                          )
                        }
                      >
                        Open
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          duplicate_mutation.mutate({
                            flow_id: flow_item.id,
                            new_name: `${flow_item.name} (copy)`,
                          })
                        }
                      >
                        Duplicate
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Delete flow "${flow_item.name}"? This cannot be undone.`,
                            )
                          ) {
                            delete_mutation.mutate(flow_item.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
