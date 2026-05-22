/**
 * API client for the ``/api/settings/*`` endpoints.
 *
 * Covers provider status listing, API-key storage (session-only),
 * and key validation.
 */

import { z } from "zod";

import { requestJson } from "./client";

const providerNameSchema = z.union([
  z.literal("openrouter"),
  z.literal("openai"),
]);
export type ProviderName = z.infer<typeof providerNameSchema>;

const providerStatusItemSchema = z.object({
  provider: providerNameSchema,
  configured: z.boolean(),
  env_var: z.string(),
});
export type ProviderStatusItem = z.infer<typeof providerStatusItemSchema>;

const providerStatusResponseSchema = z.object({
  providers: z.array(providerStatusItemSchema),
});
export type ProviderStatusResponse = z.infer<
  typeof providerStatusResponseSchema
>;

const apiKeyTestResponseSchema = z.object({
  provider: providerNameSchema,
  valid: z.boolean(),
  message: z.string(),
});
export type ApiKeyTestResponse = z.infer<typeof apiKeyTestResponseSchema>;

/** Fetch current provider status (which keys are configured). */
export function getProviderStatus(): Promise<ProviderStatusResponse> {
  return requestJson({
    method: "GET",
    path: "/api/settings/providers",
    responseSchema: providerStatusResponseSchema,
  });
}

/** Store an API key in the server's session environment. */
export function setApiKey(
  provider: ProviderName,
  api_key: string,
): Promise<ProviderStatusResponse> {
  return requestJson({
    method: "POST",
    path: "/api/settings/api-key",
    responseSchema: providerStatusResponseSchema,
    jsonBody: { provider, api_key },
  });
}

/** Validate an API key against the provider without storing it. */
export function testApiKey(
  provider: ProviderName,
  api_key: string,
): Promise<ApiKeyTestResponse> {
  return requestJson({
    method: "POST",
    path: "/api/settings/api-key/test",
    responseSchema: apiKeyTestResponseSchema,
    jsonBody: { provider, api_key },
  });
}
