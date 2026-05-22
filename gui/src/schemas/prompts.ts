/**
 * Zod mirror of server/schemas/prompts.py.
 */

import { z } from "zod";

export const promptEntrySchema = z
  .object({
    instructions: z.array(z.string()).default([]),
    output_format: z.record(z.unknown()).nullable().optional(),
  })
  .passthrough();
export type PromptEntry = z.infer<typeof promptEntrySchema>;

export const promptsResponseSchema = z.object({
  path: z.string(),
  prompts: z.record(promptEntrySchema),
});
export type PromptsResponse = z.infer<typeof promptsResponseSchema>;
