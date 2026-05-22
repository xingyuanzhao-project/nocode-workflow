/**
 * Utility helpers shared by every per-node-type property form.
 *
 * Central location for the "apply form values to the graph store and
 * flip is_dirty" dance so each form does not have to re-implement
 * the subscription pattern.
 */

import { useEffect } from "react";
import type { UseFormWatch, FieldValues } from "react-hook-form";

import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore } from "@/stores/graph_store";

/**
 * Subscribe to a React Hook Form instance and persist every change
 * into the graph store, flipping :attr:`FlowMetadataState.is_dirty`.
 *
 * The hook is generic over the form's field types so forms keep
 * their typed ``TFormValues`` inferred from their Zod schema.
 *
 * @param node_id - Target node id.
 * @param watch - ``useForm.watch`` function returning the current values.
 */
export function useAutoSaveNodeData<TFormValues extends FieldValues>(
  node_id: string,
  watch: UseFormWatch<TFormValues>,
): void {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);

  useEffect(() => {
    const subscription = watch((values) => {
      update_node_data(node_id, values as Record<string, unknown>);
      set_dirty(true);
    });
    return () => subscription.unsubscribe();
  }, [watch, node_id, update_node_data, set_dirty]);
}
