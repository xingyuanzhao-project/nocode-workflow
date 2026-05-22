/**
 * Zod mirror of server/schemas/templates.py.
 */

import { z } from "zod";

export const flowTemplateListItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().default(""),
});
export type FlowTemplateListItem = z.infer<typeof flowTemplateListItemSchema>;

export const flowTemplateListSchema = z.array(flowTemplateListItemSchema);
export type FlowTemplateList = z.infer<typeof flowTemplateListSchema>;

export const flowTemplateDetailSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().default(""),
  flow: z.record(z.unknown()),
});
export type FlowTemplateDetail = z.infer<typeof flowTemplateDetailSchema>;
