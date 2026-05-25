/**
 * Zod mirror of server/schemas/codebook.py.
 *
 * The codebook body itself is kept as an open record because
 * :class:`server.services.codebook_repository.CodebookRepository`
 * accepts arbitrary JSON; the GUI's codebook editor narrows that
 * record when it renders the label table.
 */

import { z } from "zod";

export const codebookBodySchema = z.record(z.unknown());
export type CodebookBody = z.infer<typeof codebookBodySchema>;

export const codebookSaveRequestSchema = z.object({
  name: z.string().min(1),
  codebook: codebookBodySchema,
});
export type CodebookSaveRequest = z.infer<typeof codebookSaveRequestSchema>;

export const codebookResponseSchema = z.object({
  id: z.string(),
  name: z.string(),
  codebook: codebookBodySchema,
  updated_at: z.string(),
});
export type CodebookResponse = z.infer<typeof codebookResponseSchema>;

export const codebookListItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  updated_at: z.string(),
});
export type CodebookListItem = z.infer<typeof codebookListItemSchema>;

export const codebookListSchema = z.array(codebookListItemSchema);
export type CodebookList = z.infer<typeof codebookListSchema>;
