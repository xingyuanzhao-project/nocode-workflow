/**
 * Zod schemas for run results preview.
 */

import { z } from "zod";

export const outputArtifactSchema = z.object({
  filename: z.string(),
  format: z.string().default("csv"),
  columns: z.array(z.string()).default([]),
  preview_rows: z.array(z.record(z.unknown())).default([]),
  total_row_count: z.number().int().nonnegative().default(0),
});
export type OutputArtifact = z.infer<typeof outputArtifactSchema>;

export const resultsPreviewResponseSchema = z.object({
  run_id: z.string(),
  columns: z.array(z.string()).default([]),
  preview_rows: z.array(z.record(z.unknown())).default([]),
  total_row_count: z.number().int().nonnegative().default(0),
  outputs: z.array(outputArtifactSchema).default([]),
});
export type ResultsPreviewResponse = z.infer<typeof resultsPreviewResponseSchema>;
