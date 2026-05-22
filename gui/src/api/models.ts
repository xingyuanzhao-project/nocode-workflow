/**
 * API client for the provider model-list proxy endpoint.
 */

import { requestJson } from "./client";
import {
  providerModelsResponseSchema,
  type ProviderModelsResponse,
  type ProviderName,
} from "@/schemas/models";

/** Fetch the cached model list for ``provider``. */
export function getProviderModels(
  provider: ProviderName,
): Promise<ProviderModelsResponse> {
  return requestJson({
    method: "GET",
    path: `/api/models/${encodeURIComponent(provider)}`,
    responseSchema: providerModelsResponseSchema,
  });
}
