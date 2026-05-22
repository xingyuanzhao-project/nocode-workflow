/**
 * Zod mirror of server/schemas/run.py.
 */

import { z } from "zod";

export const runStatusSchema = z.union([
  z.literal("queued"),
  z.literal("running"),
  z.literal("succeeded"),
  z.literal("failed"),
  z.literal("cancelled"),
]);
export type RunStatus = z.infer<typeof runStatusSchema>;

export const TERMINAL_RUN_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "succeeded",
  "failed",
  "cancelled",
]);

export const runStartResponseSchema = z.object({
  run_id: z.string(),
  status: runStatusSchema.default("queued"),
});
export type RunStartResponse = z.infer<typeof runStartResponseSchema>;

export const runStatusDtoSchema = z.object({
  run_id: z.string(),
  status: runStatusSchema,
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  completed_entity_count: z.number().int().nonnegative().default(0),
});
export type RunStatusDTO = z.infer<typeof runStatusDtoSchema>;
