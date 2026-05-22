/**
 * API client for the prompts-registry endpoint.
 */

import { requestJson } from "./client";
import {
  promptsResponseSchema,
  type PromptsResponse,
} from "@/schemas/prompts";

/**
 * Fetch ``config/prompts.json`` parsed into the typed registry shape.
 */
export function getPrompts(): Promise<PromptsResponse> {
  return requestJson({
    method: "GET",
    path: "/api/prompts",
    responseSchema: promptsResponseSchema,
  });
}
