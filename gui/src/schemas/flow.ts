/**
 * Zod mirror of server/schemas/flow.py plus src/flow_loader.py.
 *
 * Covers two layers:
 *
 * - The HTTP DTOs that wrap a flow (save / list / get / validate).
 * - The raw flow body itself (the shape submitted to
 *   ``POST /api/schema/validate`` and persisted under
 *   ``server/data/flows/*.yml``), mirroring
 *   :class:`src.flow_loader.FlowSchema`.
 */

import { z } from "zod";

import { validationErrorItemSchema } from "./errors";

// ---------- Flow body (mirrors src/flow_loader.py) ------------------------

export const llmResourceSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("llm_provider").default("llm_provider"),
    provider: z.union([
      z.literal("local_vllm"),
      z.literal("openrouter"),
      z.literal("openai"),
    ]),
    model: z.string().min(1),
    api_base: z.string().url().nullable().optional(),
    api_key: z.string().nullable().optional(),
    api_key_env: z.string().nullable().optional(),
    temperature: z.number().default(0.0),
    max_tokens_summary: z.number().int().positive().default(1024),
    max_tokens_classification: z.number().int().positive().default(256),
  })
  .refine(
    (value) => !(value.api_key && value.api_key_env),
    "A resource declares both api_key and api_key_env; use exactly one.",
  );
export type LLMResource = z.infer<typeof llmResourceSchema>;

export const columnRolesSchema = z.object({
  text: z.string().min(1),
  entity_id: z.string().min(1),
  doc_id: z.string().min(1),
  sort_by: z.string().min(1),
  passthrough: z.array(z.string()).default([]),
});
export type ColumnRoles = z.infer<typeof columnRolesSchema>;

export const dataConfigSchema = z.preprocess(
  (data) => {
    if (
      data != null &&
      typeof data === "object" &&
      "input_file" in data &&
      !("input_csv" in data)
    ) {
      const { input_file, ...rest } = data as Record<string, unknown>;
      return { input_csv: input_file, ...rest };
    }
    return data;
  },
  z.object({
    input_csv: z.string().min(1),
    column_roles: columnRolesSchema,
  }),
);
export type DataConfig = z.infer<typeof dataConfigSchema>;

export const ioSchemaBlockSchema = z
  .object({
    input: z.record(z.unknown()).default({}),
    output: z.record(z.unknown()),
  })
  .partial()
  .refine((value) => value.output !== undefined, "output is required");
export type IOSchemaBlock = z.infer<typeof ioSchemaBlockSchema>;

export const promptInlineSchema = z
  .object({
    instructions: z.array(z.string()).default([]),
    output_format: z.record(z.unknown()).nullable().optional(),
  })
  .passthrough();
export type PromptInline = z.infer<typeof promptInlineSchema>;

export const promptOverrideSchema = z
  .object({
    append: z.array(z.string()).optional(),
    prepend: z.array(z.string()).optional(),
    replace: z.array(z.string()).optional(),
  })
  .partial();
export type PromptOverride = z.infer<typeof promptOverrideSchema>;

export const stepConfigSchema = z
  .object({
    type: z.string().min(1),
    unit: unitValueSchemaLikelyImported(),
    group_by: z.string().nullable().optional(),
    llm: z.string().nullable().optional(),
    mode: z.string().nullable().optional(),
    keys: z.unknown().nullable().optional(),
    io_schema: ioSchemaBlockSchema.nullable().optional(),
    prompts_ref: z.string().nullable().optional(),
    prompt: promptInlineSchema.nullable().optional(),
    prompt_overrides: promptOverrideSchema.nullable().optional(),
  })
  .refine(
    (value) => !(value.prompt && value.prompts_ref),
    "A step cannot set both prompt (inline) and prompts_ref (reference).",
  )
  .refine(
    (value) => !(value.prompt_overrides && !value.prompts_ref),
    "prompt_overrides requires prompts_ref.",
  );
export type StepConfig = z.infer<typeof stepConfigSchema>;

function unitValueSchemaLikelyImported() {
  // `unit` is a string in the flow schema. We keep it narrowly-typed
  // here rather than importing from node_types.ts to avoid cycles.
  return z.union([z.literal("row"), z.literal("document"), z.literal("entity")]);
}

export const asyncConfigSchema = z.object({
  enabled: z.boolean().default(true),
  max_concurrent_rows: z.number().int().positive().default(15),
  max_concurrent_llm_calls: z.number().int().positive().default(50),
  max_retries: z.number().int().nonnegative().default(5),
});
export type AsyncConfig = z.infer<typeof asyncConfigSchema>;

export const outputConfigSchema = z.object({
  summary_csv: z.string().min(1),
  results_csv: z.string().nullable().optional(),
  states_csv: z.string().nullable().optional(),
  spans_csv: z.string().nullable().optional(),
  extend: z.boolean().default(false),
});
export type OutputConfig = z.infer<typeof outputConfigSchema>;

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

export const flowBodySchema = z.object({
  schema_version: z.number().int().default(1),
  name: z.string().min(1),
  description: z.string().default(""),
  resources: z.array(llmResourceSchema).min(1),
  data: dataConfigSchema,
  taxonomy: z.string().min(1),
  prompts: z.string().min(1),
  steps: z.array(stepConfigSchema).min(1),
  processing_limit: z.number().int().positive().nullable().optional(),
  async: asyncConfigSchema.default({
    enabled: true,
    max_concurrent_rows: 15,
    max_concurrent_llm_calls: 50,
    max_retries: 5,
  }),
  output: outputConfigSchema,
  logging: loggingConfigSchema.default({
    file: "processing.log",
    log_progress: true,
    log_prompts: false,
    log_response: false,
  }),
  display: displayConfigSchema.default({ use_progress_bar: true }),
});
export type FlowBody = z.infer<typeof flowBodySchema>;

// ---------- HTTP wrappers (mirror server/schemas/flow.py) ----------------

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

// ---------- Cost estimate (mirrors server/schemas/flow.py) ----------------

export const costEstimateResponseSchema = z.object({
  estimated_tokens: z.number(),
  estimated_cost_usd: z.number(),
  model: z.string(),
  step_count: z.number(),
  message: z.string(),
});
export type CostEstimateResponse = z.infer<typeof costEstimateResponseSchema>;
