/**
 * API client for the ``/api/settings/*`` endpoints.
 *
 * Covers cloud provider key management and local endpoint
 * configuration (Ollama, vLLM, llama.cpp).
 */

import { z } from "zod";

import { requestJson } from "./client";

const providerNameSchema = z.union([
  z.literal("openrouter"),
  z.literal("openai"),
  z.literal("claude"),
  z.literal("google"),
]);
export type ProviderName = z.infer<typeof providerNameSchema>;

const localProviderNameSchema = z.union([
  z.literal("ollama"),
  z.literal("vllm"),
  z.literal("llama_cpp"),
]);
export type LocalProviderName = z.infer<typeof localProviderNameSchema>;

const providerStatusItemSchema = z.object({
  provider: providerNameSchema,
  configured: z.boolean(),
  env_var: z.string(),
});
export type ProviderStatusItem = z.infer<typeof providerStatusItemSchema>;

const localEndpointStatusItemSchema = z.object({
  provider: localProviderNameSchema,
  api_base: z.string(),
  configured: z.boolean(),
});
export type LocalEndpointStatusItem = z.infer<
  typeof localEndpointStatusItemSchema
>;

const providerStatusResponseSchema = z.object({
  providers: z.array(providerStatusItemSchema),
  local_endpoints: z.array(localEndpointStatusItemSchema).default([]),
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

const localEndpointTestResponseSchema = z.object({
  reachable: z.boolean(),
  models: z.array(z.string()).default([]),
  message: z.string(),
});
export type LocalEndpointTestResponse = z.infer<
  typeof localEndpointTestResponseSchema
>;

/** Fetch cloud and local provider status. */
export function getProviderStatus(): Promise<ProviderStatusResponse> {
  return requestJson({
    method: "GET",
    path: "/api/settings/providers",
    responseSchema: providerStatusResponseSchema,
  });
}

/** Store a cloud API key in the server's session environment. */
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

/** Validate a cloud API key against the provider. */
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

/** Store a local endpoint URL for the session. */
export function setLocalEndpoint(
  provider: LocalProviderName,
  api_base: string,
): Promise<ProviderStatusResponse> {
  return requestJson({
    method: "POST",
    path: "/api/settings/local-endpoint",
    responseSchema: providerStatusResponseSchema,
    jsonBody: { provider, api_base },
  });
}

/** Test a local endpoint by hitting its /models path. */
export function testLocalEndpoint(
  api_base: string,
): Promise<LocalEndpointTestResponse> {
  return requestJson({
    method: "POST",
    path: "/api/settings/local-endpoint/test",
    responseSchema: localEndpointTestResponseSchema,
    jsonBody: { api_base },
  });
}
