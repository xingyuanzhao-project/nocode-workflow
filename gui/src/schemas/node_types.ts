/**
 * Zod mirror of server/schemas/node_types.py.
 *
 * The GUI reads the node-type catalog from
 * ``GET /api/schema/node-types`` and uses the entries' fields to
 * drive the palette, the property panel forms, and the unit-aware
 * edge validator.
 */

import { z } from "zod";

export const nodeTypeCategorySchema = z.union([
  z.literal("data"),
  z.literal("processor"),
  z.literal("resource"),
]);
export type NodeTypeCategory = z.infer<typeof nodeTypeCategorySchema>;

export const unitValueSchema = z.union([
  z.literal("row"),
  z.literal("document"),
  z.literal("entity"),
]);
export type UnitValue = z.infer<typeof unitValueSchema>;

export const nodeTypeEntrySchema = z.object({
  id: z.string(),
  category: nodeTypeCategorySchema,
  label: z.string().default(""),
  description: z.string().default(""),
  default_unit: z.string().nullable().default(null),
  consumes: z.array(z.string()).default([]),
  produces: z.array(z.string()).default([]),
  llm_backed: z.boolean().default(false),
  requires_resources: z.array(z.string()).default([]),
  default_io_schema: z.record(z.unknown()).nullable().default(null),
  default_prompt_ref: z.string().nullable().default(null),
  default_group_by: z.string().nullable().default(null),
});
export type NodeTypeEntry = z.infer<typeof nodeTypeEntrySchema>;

export const nodeTypeRegistrySchema = z.object({
  version: z.number().int(),
  entries: z.array(nodeTypeEntrySchema),
});
export type NodeTypeRegistry = z.infer<typeof nodeTypeRegistrySchema>;
