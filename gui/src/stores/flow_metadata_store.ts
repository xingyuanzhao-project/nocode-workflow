/**
 * Zustand store for the flow's identity and dirty flag.
 *
 * A new flow starts with ``flow_id=null``; the id is populated after
 * :func:`@/api/flows.createFlow` returns. ``is_dirty`` flips to
 * ``true`` whenever the canvas or the Property Panel edits something;
 * the saved-flow view resets it to ``false`` after a successful
 * :func:`@/api/flows.updateFlow`.
 */

import { create, type StoreApi, type UseBoundStore } from "zustand";

export interface FlowMetadataState {
  /** Saved-flow identifier, or ``null`` while creating a new flow. */
  flow_id: string | null;
  /** Human-readable flow name. Shown in the My Flows list. */
  name: string;
  /** Free-form description. Optional. */
  description: string;
  /** True when the graph has unsaved changes. */
  is_dirty: boolean;

  /** Replace the metadata, typically after a load/save. */
  set_metadata: (args: {
    flow_id: string | null;
    name: string;
    description: string;
    is_dirty?: boolean;
  }) => void;
  /** Mark the flow as modified. */
  set_dirty: (is_dirty: boolean) => void;
  /** Patch just the name (used by the rename control). */
  set_name: (name: string) => void;
  /** Patch just the description. */
  set_description: (description: string) => void;
  /** Reset to an empty flow (used by New Flow). */
  reset: () => void;
}

const INITIAL_METADATA: Pick<
  FlowMetadataState,
  "flow_id" | "name" | "description" | "is_dirty"
> = {
  flow_id: null,
  name: "",
  description: "",
  is_dirty: false,
};

export const useFlowMetadataStore: UseBoundStore<StoreApi<FlowMetadataState>> =
  create<FlowMetadataState>((set) => ({
    ...INITIAL_METADATA,

    set_metadata: ({ flow_id, name, description, is_dirty = false }) =>
      set({ flow_id, name, description, is_dirty }),
    set_dirty: (is_dirty) => set({ is_dirty }),
    set_name: (name) => set((state) => ({ name, is_dirty: state.is_dirty || name !== "" })),
    set_description: (description) => set({ description, is_dirty: true }),
    reset: () => set({ ...INITIAL_METADATA }),
  }));
