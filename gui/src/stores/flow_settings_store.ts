/**
 * Zustand store holding flow-level fields that do not fit the graph.
 *
 * The graph carries the typed nodes / edges the user sees and edits;
 * the flow YAML however also contains ``async``, ``logging``, ``display``,
 * and ``processing_limit`` fields under a ``settings:`` block which have
 * no visual representation. This store owns those fields so they survive
 * a YAML→graph→YAML round-trip without polluting the graph nodes.
 */

import { create, type StoreApi, type UseBoundStore } from "zustand";

import type {
  AsyncConfig,
  DisplayConfig,
  LoggingConfig,
} from "@/schemas/flow";

export interface FlowSettingsState {
  /** Optional cap on the number of entities/rows the runner processes. */
  processing_limit: number | null;
  /** Async / concurrency settings (``flow.settings.async``). */
  async_config: AsyncConfig;
  /** Logging settings (``flow.settings.logging``). */
  logging_config: LoggingConfig;
  /** Display settings (``flow.settings.display``). */
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
  | "processing_limit"
  | "async_config"
  | "logging_config"
  | "display_config"
> = {
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
