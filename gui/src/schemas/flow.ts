/**
 * Zod mirror of the new ``flow:`` document shape.
 *
 * The flow editor was rebuilt around an explicit graph: the YAML stores
 * nodes and edges directly, with no implicit derivation. This module
 * mirrors :class:`src.flow_loader.FlowDocument` and the per-node /
 * per-edge entries; it also keeps the HTTP wrapper schemas the rest of
 * the GUI consumes (save / list / get / validate / cost estimate).
 *
 * Imports here:
 *
 * - ``flowDocumentSchema`` and ``flowBodySchema`` validate the parsed
 *   YAML before it touches any Zustand store.
 * - The settings sub-schemas (``asyncConfigSchema``, ``loggingConfigSchema``,
 *   ``displayConfigSchema``) are shared with
 *   :class:`@/stores/flow_settings_store`.
 * - The HTTP wrapper schemas validate every API response shape.
 */

import { z } from "zod";

import { validationErrorItemSchema } from "./errors";

// ---------- Settings sub-blocks ----------------------------------------

export const asyncConfigSchema = z.object({
  enabled: z.boolean().default(true),
  max_concurrent_rows: z.number().int().positive().default(15),
  max_concurrent_llm_calls: z.number().int().positive().default(50),
  max_retries: z.number().int().nonnegative().default(5),
});
export type AsyncConfig = z.infer<typeof asyncConfigSchema>;

export const loggingConfigSchema = z.object({
  file: z.string().default("processing.log"),
  log_progress: z.boolean().default(true),
  log_prompts: z.boolean().default(false),
  log_response: z.boolean().default(false),
});
export type LoggingConfig = z.infer<typeof loggingConfigSchema>;

export const displayConfigSchema = z.object({
  use_progress_bar: z.boolean().default(true),
});
export type DisplayConfig = z.infer<typeof displayConfigSchema>;

export const flowSettingsSchema = z.object({
  processing_limit: z.number().int().positive().nullable().default(null),
  async: asyncConfigSchema.default({
    enabled: true,
    max_concurrent_rows: 15,
    max_concurrent_llm_calls: 50,
    max_retries: 5,
  }),
  logging: loggingConfigSchema.default({
    file: "processing.log",
    log_progress: true,
    log_prompts: false,
    log_response: false,
  }),
  display: displayConfigSchema.default({ use_progress_bar: true }),
});
export type FlowSettings = z.infer<typeof flowSettingsSchema>;

// ---------- Node and edge entries --------------------------------------

const nodePositionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

/**
 * Per-node entry under ``flow.nodes[]``. The type discriminator selects
 * the typed subclass (see ``model/register.ts``); ``config`` is opaque
 * here and parsed by the subclass's :meth:`apply_config`.
 */
export const nodeEntrySchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  position: nodePositionSchema.optional(),
  config: z.record(z.unknown()).default({}),
});
export type NodeEntry = z.infer<typeof nodeEntrySchema>;

/**
 * Per-edge entry under ``flow.edges[]``. ``source`` and ``target`` are
 * node ids; the ``type`` discriminator selects the edge subclass.
 */
export const edgeEntrySchema = z.object({
  type: z.string().min(1),
  source: z.string().min(1),
  target: z.string().min(1),
});
export type EdgeEntry = z.infer<typeof edgeEntrySchema>;

// ---------- Flow document (top-level) ---------------------------------

/**
 * The raw flow body as it appears under the ``flow:`` key on disk and as
 * it is submitted to ``POST /api/schema/validate`` /
 * ``POST /api/flow`` / ``PUT /api/flow/{id}``.
 */
export const flowDocumentSchema = z.object({
  name: z.string().min(1),
  description: z.string().default(""),
  nodes: z.array(nodeEntrySchema),
  edges: z.array(edgeEntrySchema),
  settings: flowSettingsSchema.default({
    processing_limit: null,
    async: {
      enabled: true,
      max_concurrent_rows: 15,
      max_concurrent_llm_calls: 50,
      max_retries: 5,
    },
    logging: {
      file: "processing.log",
      log_progress: true,
      log_prompts: false,
      log_response: false,
    },
    display: { use_progress_bar: true },
  }),
});
export type FlowDocument = z.infer<typeof flowDocumentSchema>;

/**
 * Backwards-compatible alias used by the few sites that still import
 * ``flowBodySchema`` / ``FlowBody`` from the old layout.
 */
export const flowBodySchema = flowDocumentSchema;
export type FlowBody = FlowDocument;

// ---------- HTTP wrappers (mirror server/schemas/flow.py) -------------

export const flowValidationResponseSchema = z.object({
  valid: z.boolean(),
  errors: z.array(validationErrorItemSchema).default([]),
});
export type FlowValidationResponse = z.infer<typeof flowValidationResponseSchema>;

export const flowSaveResponseSchema = z.object({
  id: z.string().min(1),
  path: z.string().min(1),
});
export type FlowSaveResponse = z.infer<typeof flowSaveResponseSchema>;

export const flowListItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().default(""),
  updated_at: z.string(),
});
export type FlowListItem = z.infer<typeof flowListItemSchema>;

export const flowGetResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  flow: z.record(z.unknown()),
  updated_at: z.string(),
});
export type FlowGetResponse = z.infer<typeof flowGetResponseSchema>;

export const flowListSchema = z.array(flowListItemSchema);
export type FlowList = z.infer<typeof flowListSchema>;

// ---------- Cost estimate (mirrors server/schemas/flow.py) ------------

export const costEstimateResponseSchema = z.object({
  estimated_tokens: z.number(),
  estimated_cost_usd: z.number(),
  model: z.string(),
  step_count: z.number(),
  message: z.string(),
});
export type CostEstimateResponse = z.infer<typeof costEstimateResponseSchema>;
