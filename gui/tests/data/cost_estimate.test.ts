import { describe, expect, it } from "vitest";

import { costEstimateResponseSchema } from "@/schemas/flow";

describe("costEstimateResponseSchema", () => {
  it("accepts a valid cost estimate response", () => {
    const parsed = costEstimateResponseSchema.parse({
      model: "google/gemini-2.5-flash",
      provider: "openrouter",
      is_local: false,
      model_price_per_million_tokens: 2.5,
      api_calls: 100,
      max_tokens_per_call: 1024,
      estimated_tokens: 102400,
      estimated_cost_usd: 0.256,
      message: "100 API calls × 1,024 max_tokens = ~102,400 tokens",
    });
    expect(parsed.model).toBe("google/gemini-2.5-flash");
    expect(parsed.provider).toBe("openrouter");
    expect(parsed.is_local).toBe(false);
    expect(parsed.model_price_per_million_tokens).toBe(2.5);
    expect(parsed.api_calls).toBe(100);
    expect(parsed.max_tokens_per_call).toBe(1024);
    expect(parsed.estimated_tokens).toBe(102400);
    expect(parsed.estimated_cost_usd).toBe(0.256);
  });

  it("accepts a local-provider estimate with zero price", () => {
    const parsed = costEstimateResponseSchema.parse({
      model: "llama-3.1-8b",
      provider: "ollama",
      is_local: true,
      model_price_per_million_tokens: 0,
      api_calls: 50,
      max_tokens_per_call: 512,
      estimated_tokens: 25600,
      estimated_cost_usd: 0,
      message: "50 API calls × 512 max_tokens = ~25,600 tokens (local)",
    });
    expect(parsed.is_local).toBe(true);
    expect(parsed.model_price_per_million_tokens).toBe(0);
    expect(parsed.estimated_cost_usd).toBe(0);
  });

  it("rejects a response missing the model field", () => {
    expect(() =>
      costEstimateResponseSchema.parse({
        provider: "openrouter",
        is_local: false,
        model_price_per_million_tokens: 2.5,
        api_calls: 100,
        max_tokens_per_call: 1024,
        estimated_tokens: 102400,
        estimated_cost_usd: 0.256,
        message: "msg",
      }),
    ).toThrow();
  });

  it("rejects a response missing is_local", () => {
    expect(() =>
      costEstimateResponseSchema.parse({
        model: "gpt-4o",
        provider: "openai",
        model_price_per_million_tokens: 10.0,
        api_calls: 200,
        max_tokens_per_call: 1024,
        estimated_tokens: 204800,
        estimated_cost_usd: 2.048,
        message: "msg",
      }),
    ).toThrow();
  });

  it("rejects a response missing api_calls", () => {
    expect(() =>
      costEstimateResponseSchema.parse({
        model: "gpt-4o",
        provider: "openai",
        is_local: false,
        model_price_per_million_tokens: 10.0,
        max_tokens_per_call: 1024,
        estimated_tokens: 204800,
        estimated_cost_usd: 2.048,
        message: "msg",
      }),
    ).toThrow();
  });
});
