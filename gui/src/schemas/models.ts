/**
 * Zod mirror of server/schemas/models.py.
 */

import { z } from "zod";

export const providerNameSchema = z.union([
  z.literal("openrouter"),
  z.literal("openai"),
  z.literal("local_vllm"),
  z.literal("ollama"),
  z.literal("vllm"),
  z.literal("llama_cpp"),
]);
export type ProviderName = z.infer<typeof providerNameSchema>;

export const providerModelSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  context_length: z.number().int().nullable().optional(),
});
export type ProviderModel = z.infer<typeof providerModelSchema>;

export const providerModelsResponseSchema = z.object({
  provider: providerNameSchema,
  fetched_at: z.string(),
  models: z.array(providerModelSchema).default([]),
});
export type ProviderModelsResponse = z.infer<typeof providerModelsResponseSchema>;
