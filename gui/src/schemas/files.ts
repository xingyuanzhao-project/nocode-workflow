/**
 * Zod mirror of server/schemas/files.py.
 */

import { z } from "zod";

export const csvColumnDescriptorSchema = z.object({
  name: z.string(),
  dtype: z.string(),
  sample_values: z.array(z.unknown()).default([]),
});
export type CSVColumnDescriptor = z.infer<typeof csvColumnDescriptorSchema>;

export const csvUploadResponseSchema = z.object({
  upload_id: z.string(),
  filename: z.string(),
  stored_path: z.string(),
  row_count: z.number().int().nonnegative(),
  columns: z.array(csvColumnDescriptorSchema).default([]),
});
export type CSVUploadResponse = z.infer<typeof csvUploadResponseSchema>;
