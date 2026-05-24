/**
 * Typed node for the ``llm_call`` palette item.
 *
 * One LLM Call node is one OpenAI-compatible endpoint. A processor that
 * needs an LLM declares an ``llm_call`` edge from its top handle to the
 * LLM Call node it should use; the runtime builds an ``AsyncOpenAI``
 * client per LLM Call node and dispatches the processor's request to it.
 */

import { BaseNode, type NodeCategory, type NodePosition } from "../base_node";

export type ProviderName =
  | "openrouter"
  | "openai"
  | "claude"
  | "google"
  | "ollama"
  | "vllm"
  | "llama_cpp";

const ALLOWED_PROVIDERS: ReadonlySet<ProviderName> = new Set([
  "openrouter",
  "openai",
  "claude",
  "google",
  "ollama",
  "vllm",
  "llama_cpp",
]);

export class LLMCallNode extends BaseNode {
  readonly node_type = "llm_call";
  readonly category: NodeCategory = "resource";
  readonly label: string = "LLM Call";

  resource_id: string = "default";
  provider: ProviderName = "openrouter";
  model: string = "";
  api_base: string | null = "https://openrouter.ai/api/v1";
  api_key_env: string | null = "OPENROUTER_API_KEY";
  api_key: string | null = null;
  temperature: number = 0;
  max_tokens: number = 1024;

  constructor(
    id: string,
    config: Record<string, unknown> = {},
    position: NodePosition = { x: 0, y: 0 },
  ) {
    super(id, position);
    this.apply_config(config);
  }

  apply_config(config: Record<string, unknown>): void {
    this.resource_id =
      typeof config.resource_id === "string" && config.resource_id.length > 0
        ? config.resource_id
        : "default";

    const provider_value = config.provider;
    this.provider =
      typeof provider_value === "string" &&
      ALLOWED_PROVIDERS.has(provider_value as ProviderName)
        ? (provider_value as ProviderName)
        : "openrouter";

    this.model = typeof config.model === "string" ? config.model : "";

    this.api_base =
      typeof config.api_base === "string" && config.api_base.length > 0
        ? config.api_base
        : null;

    this.api_key_env =
      typeof config.api_key_env === "string" && config.api_key_env.length > 0
        ? config.api_key_env
        : null;

    this.api_key =
      typeof config.api_key === "string" && config.api_key.length > 0
        ? config.api_key
        : null;

    this.temperature =
      typeof config.temperature === "number"
        ? config.temperature
        : typeof config.temperature === "string"
          ? Number.parseFloat(config.temperature) || 0
          : 0;

    this.max_tokens =
      typeof config.max_tokens === "number"
        ? config.max_tokens
        : typeof config.max_tokens === "string"
          ? Number.parseInt(config.max_tokens, 10) || 1024
          : 1024;
  }

  private static readonly PROVIDER_DEFAULT_ENV_VAR: Record<string, string> = {
    openrouter: "OPENROUTER_API_KEY",
    openai: "OPENAI_API_KEY",
    claude: "ANTHROPIC_API_KEY",
    google: "GOOGLE_API_KEY",
  };

  private static readonly LOCAL_PROVIDERS: ReadonlySet<string> = new Set([
    "ollama", "vllm", "llama_cpp",
  ]);

  emit_config(): Record<string, unknown> {
    const out: Record<string, unknown> = {
      resource_id: this.resource_id,
      provider: this.provider,
      model: this.model,
      temperature: this.temperature,
      max_tokens: this.max_tokens,
    };
    if (this.api_base !== null) {
      out.api_base = this.api_base;
    }
    const effective_api_key_env = this.api_key_env
      ?? LLMCallNode.PROVIDER_DEFAULT_ENV_VAR[this.provider]
      ?? null;
    if (effective_api_key_env !== null && !LLMCallNode.LOCAL_PROVIDERS.has(this.provider)) {
      out.api_key_env = effective_api_key_env;
    }
    if (this.api_key !== null) {
      out.api_key = this.api_key;
    }
    return out;
  }

  validate(): string | null {
    if (!this.model || this.model.trim().length === 0) {
      return `LLM Call "${this.id}" has no model id set.`;
    }
    if (this.api_key !== null && this.api_key_env !== null) {
      return `LLM Call "${this.id}" sets both api_key and api_key_env; use exactly one.`;
    }
    return null;
  }

  protected build_data_payload(): Record<string, unknown> {
    return {
      node_type_id: this.node_type,
      label: this.label,
      category: this.category,
      resource_id: this.resource_id,
      provider: this.provider,
      model: this.model,
      api_base: this.api_base,
      api_key_env: this.api_key_env,
      api_key: this.api_key,
      temperature: this.temperature,
      max_tokens: this.max_tokens,
    };
  }
}
