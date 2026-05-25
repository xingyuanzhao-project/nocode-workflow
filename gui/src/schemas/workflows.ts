/**
 * Zod mirror of server/schemas/workflows.py.
 */

import { z } from "zod";

export const workflowListItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().default(""),
});
export type WorkflowListItem = z.infer<typeof workflowListItemSchema>;

export const workflowListSchema = z.array(workflowListItemSchema);
export type WorkflowList = z.infer<typeof workflowListSchema>;

export const workflowDetailSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().default(""),
  flow: z.record(z.unknown()),
});
export type WorkflowDetail = z.infer<typeof workflowDetailSchema>;
