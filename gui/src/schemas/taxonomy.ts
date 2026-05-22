/**
 * Zod mirror of server/schemas/taxonomy.py.
 *
 * The taxonomy body itself is kept as an open record because
 * :class:`server.services.taxonomy_repository.TaxonomyRepository`
 * accepts arbitrary JSON; the GUI's taxonomy editor narrows that
 * record when it renders the label table.
 */

import { z } from "zod";

export const taxonomyBodySchema = z.record(z.unknown());
export type TaxonomyBody = z.infer<typeof taxonomyBodySchema>;

export const taxonomySaveRequestSchema = z.object({
  name: z.string().min(1),
  taxonomy: taxonomyBodySchema,
});
export type TaxonomySaveRequest = z.infer<typeof taxonomySaveRequestSchema>;

export const taxonomyResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  taxonomy: taxonomyBodySchema,
  updated_at: z.string(),
});
export type TaxonomyResponse = z.infer<typeof taxonomyResponseSchema>;

export const taxonomyListItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  updated_at: z.string(),
});
export type TaxonomyListItem = z.infer<typeof taxonomyListItemSchema>;

export const taxonomyListSchema = z.array(taxonomyListItemSchema);
export type TaxonomyList = z.infer<typeof taxonomyListSchema>;
