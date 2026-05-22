/**
 * Zustand store holding flow-level fields that do not fit the graph.
 *
 * The graph carries the nodes / edges the user sees and edits; the
 * flow YAML however also contains ``async``, ``logging``, ``display``,
 * ``processing_limit``, and ``schema_version`` which have no visual
 * representation. This store owns those fields so they survive a
 * YAML→graph→YAML round-trip without polluting the graph nodes.
 */

import { create, type StoreApi, type UseBoundStore } from "zustand";

import type {
  AsyncConfig,
  DisplayConfig,
  LoggingConfig,
} from "@/schemas/flow";

export interface FlowSettingsState {
  /** Flow schema version (server-defined; defaults to 1). */
  schema_version: number;
  /** Optional cap on the number of entities/rows the runner processes. */
  processing_limit: number | null;
  /** Async / concurrency settings (FlowConfig.async). */
  async_config: AsyncConfig;
  /** Logging settings (FlowConfig.logging). */
  logging_config: LoggingConfig;
  /** Display settings (FlowConfig.display). */
  display_config: DisplayConfig;

  /** Replace every setting at once (used by the codec on load). */
  set_settings: (patch: Partial<FlowSettingsState>) => void;
  /** Reset to defaults (used by the New Flow dialog). */
  reset_settings: () => void;
}

const DEFAULT_ASYNC_CONFIG: AsyncConfig = {
  enabled: true,
  max_concurrent_rows: 15,
  max_concurrent_llm_calls: 50,
  max_retries: 5,
};

const DEFAULT_LOGGING_CONFIG: LoggingConfig = {
  file: "processing.log",
  log_progress: true,
  log_prompts: false,
  log_response: false,
};

const DEFAULT_DISPLAY_CONFIG: DisplayConfig = {
  use_progress_bar: false,
};

const INITIAL_SETTINGS: Pick<
  FlowSettingsState,
  | "schema_version"
  | "processing_limit"
  | "async_config"
  | "logging_config"
  | "display_config"
> = {
  schema_version: 1,
  processing_limit: null,
  async_config: DEFAULT_ASYNC_CONFIG,
  logging_config: DEFAULT_LOGGING_CONFIG,
  display_config: DEFAULT_DISPLAY_CONFIG,
};

export const useFlowSettingsStore: UseBoundStore<StoreApi<FlowSettingsState>> =
  create<FlowSettingsState>((set) => ({
    ...INITIAL_SETTINGS,

    set_settings: (patch) => set(patch),
    reset_settings: () => set({ ...INITIAL_SETTINGS }),
  }));
