/**
 * Zod mirror of server/schemas/health.py.
 */

import { z } from "zod";

export const healthResponseSchema = z.object({
  status: z.union([z.literal("ok"), z.literal("degraded")]),
  redis_ok: z.boolean(),
  worker_ok: z.boolean(),
});
export type HealthResponse = z.infer<typeof healthResponseSchema>;
