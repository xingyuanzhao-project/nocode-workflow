/**
 * Zod mirror of server/schemas/errors.py.
 *
 * The FastAPI app wraps every non-2xx response in an ErrorResponse
 * envelope; the API client parses bodies with these schemas so
 * components receive typed error payloads.
 */

import { z } from "zod";

export const validationErrorItemSchema = z.object({
  loc: z.array(z.unknown()),
  msg: z.string(),
  type: z.string(),
});
export type ValidationErrorItem = z.infer<typeof validationErrorItemSchema>;

export const errorResponseSchema = z.object({
  errors: z.array(validationErrorItemSchema),
});
export type ErrorResponse = z.infer<typeof errorResponseSchema>;
