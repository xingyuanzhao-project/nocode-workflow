/**
 * Zod mirror of server/schemas/results.py.
 */

import { z } from "zod";

export const artifactNameSchema = z.union([
  z.literal("summary"),
  z.literal("results"),
  z.literal("states"),
  z.literal("spans"),
]);
export type ArtifactName = z.infer<typeof artifactNameSchema>;

export const ARTIFACT_NAMES: readonly ArtifactName[] = [
  "summary",
  "results",
  "states",
  "spans",
] as const;

export const resultsPreviewResponseSchema = z.object({
  run_id: z.string(),
  artifact_name: artifactNameSchema,
  columns: z.array(z.string()).default([]),
  preview_rows: z.array(z.record(z.unknown())).default([]),
  total_row_count: z.number().int().nonnegative().default(0),
});
export type ResultsPreviewResponse = z.infer<typeof resultsPreviewResponseSchema>;
