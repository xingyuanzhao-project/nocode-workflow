/**
 * Config-tab form for :class:`LLMCallNode`.
 *
 * The model dropdown is fed by ``GET /api/models/{provider}`` via
 * :mod:`@/api/models`. Users can type a model id by hand if the
 * provider's catalogue lacks it.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";

import { getProviderModels } from "@/api/models";
import { useAutoSaveNodeData } from "../node_update_helpers";
import type { GraphNode } from "@/stores/graph_store";
import {
  providerNameSchema,
  type ProviderName,
} from "@/schemas/models";
import { Combobox } from "@/components/ui/combobox";

const providerFormSchema = z.object({
  resource_id: z.string().min(1),
  provider: providerNameSchema,
  model: z.string().min(1),
  api_base: z.string().nullable(),
  api_key_env: z.string().nullable(),
  temperature: z.coerce.number().min(0).max(2),
  max_tokens: z.coerce.number().int().positive(),
});
type ProviderFormValues = z.infer<typeof providerFormSchema>;

const PROVIDER_ENV_VAR: Record<string, string> = {
  openrouter: "OPENROUTER_API_KEY",
  openai: "OPENAI_API_KEY",
};

const LOCAL_PROVIDERS = new Set(["local_vllm", "ollama", "vllm", "llama_cpp"]);

export interface LLMProviderConfigFormProps {
  node: GraphNode;
}

function readInitialValues(node: GraphNode): ProviderFormValues {
  const data = node.data;
  const valid_providers = [
    "openrouter",
    "openai",
    "local_vllm",
    "ollama",
    "vllm",
    "llama_cpp",
  ];
  const provider_value =
    typeof data.provider === "string" &&
    valid_providers.includes(data.provider)
      ? (data.provider as ProviderName)
      : "openrouter";
  return {
    resource_id:
      typeof data.resource_id === "string" && data.resource_id.length > 0
        ? data.resource_id
        : "default",
    provider: provider_value,
    model: typeof data.model === "string" ? data.model : "",
    api_base: typeof data.api_base === "string" ? data.api_base : null,
    api_key_env: PROVIDER_ENV_VAR[provider_value] ?? null,
    temperature: typeof data.temperature === "number" ? data.temperature : 0,
    max_tokens: typeof data.max_tokens === "number" ? data.max_tokens : 1024,
  };
}

export function LLMProviderConfigForm({
  node,
}: LLMProviderConfigFormProps): JSX.Element {
  const form = useForm<ProviderFormValues>({
    resolver: zodResolver(providerFormSchema),
    defaultValues: readInitialValues(node),
  });

  useEffect(() => {
    form.reset(readInitialValues(node));
  }, [node.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useAutoSaveNodeData(node.id, form.watch);

  const current_provider = form.watch("provider");

  useEffect(() => {
    const derived = PROVIDER_ENV_VAR[current_provider] ?? null;
    form.setValue("api_key_env", derived, { shouldDirty: true });
  }, [current_provider]); // eslint-disable-line react-hooks/exhaustive-deps
  const models_query = useQuery({
    queryKey: ["provider-models", current_provider],
    queryFn: () => getProviderModels(current_provider),
    staleTime: 5 * 60_000,
    enabled: Boolean(current_provider),
  });

  return (
    <form className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Resource id</span>
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm"
          placeholder="default"
          {...form.register("resource_id")}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Provider</span>
        <select
          className="rounded-md border bg-background px-2 py-1 text-sm"
          {...form.register("provider")}
        >
          <option value="openrouter">openrouter</option>
          <option value="openai">openai</option>
          <option value="local_vllm">local_vllm</option>
          <option value="ollama">ollama</option>
          <option value="vllm">vllm</option>
          <option value="llama_cpp">llama_cpp</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Model</span>
        <Combobox
          options={(models_query.data?.models ?? []).map((m) => ({
            value: m.id,
            label: m.label,
          }))}
          value={form.watch("model")}
          onChange={(val) =>
            form.setValue("model", val, { shouldDirty: true })
          }
          placeholder="openrouter/auto"
          loading={models_query.isLoading}
          loadingText="Loading model catalogue…"
          errorText={
            models_query.isError
              ? "Could not load model catalogue."
              : undefined
          }
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">API base URL</span>
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm"
          placeholder="https://openrouter.ai/api/v1"
          value={form.watch("api_base") ?? ""}
          onChange={(event) =>
            form.setValue(
              "api_base",
              event.target.value === "" ? null : event.target.value,
              { shouldDirty: true },
            )
          }
        />
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">API key env var</span>
        <input
          className="rounded-md border bg-muted px-2 py-1 text-sm text-muted-foreground"
          readOnly
          disabled
          value={form.watch("api_key_env") ?? (LOCAL_PROVIDERS.has(current_provider) ? "(not required)" : "")}
        />
        <span className="text-muted-foreground">
          Derived from provider. Configure the key in the API Keys page.
        </span>
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">Temperature</span>
          <input
            type="number"
            step="0.05"
            className="rounded-md border bg-background px-2 py-1 text-sm"
            {...form.register("temperature")}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">max_tokens</span>
          <input
            type="number"
            className="rounded-md border bg-background px-2 py-1 text-sm"
            {...form.register("max_tokens")}
          />
        </label>
      </div>
    </form>
  );
}
