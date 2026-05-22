/**
 * Config-tab form for :class:`@/flow_editor/nodes/llm_provider_node.LLMProviderNode`.
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

const providerFormSchema = z.object({
  resource_id: z.string().min(1),
  provider: providerNameSchema,
  model: z.string().min(1),
  api_base: z.string().nullable(),
  api_key_env: z.string().nullable(),
  temperature: z.coerce.number().min(0).max(2),
  max_tokens_summary: z.coerce.number().int().positive(),
  max_tokens_classification: z.coerce.number().int().positive(),
});
type ProviderFormValues = z.infer<typeof providerFormSchema>;

export interface LLMProviderConfigFormProps {
  node: GraphNode;
}

function readInitialValues(node: GraphNode): ProviderFormValues {
  const data = node.data;
  const provider_value =
    typeof data.provider === "string" &&
    (data.provider === "openrouter" || data.provider === "openai")
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
    api_key_env:
      typeof data.api_key_env === "string" ? data.api_key_env : null,
    temperature:
      typeof data.temperature === "number" ? data.temperature : 0,
    max_tokens_summary:
      typeof data.max_tokens_summary === "number"
        ? data.max_tokens_summary
        : 1024,
    max_tokens_classification:
      typeof data.max_tokens_classification === "number"
        ? data.max_tokens_classification
        : 256,
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
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs">
        <span className="font-medium">Model</span>
        <input
          className="rounded-md border bg-background px-2 py-1 text-sm"
          list={`models_for_${current_provider}`}
          placeholder="meta-llama/llama-3.1-70b-instruct"
          {...form.register("model")}
        />
        <datalist id={`models_for_${current_provider}`}>
          {(models_query.data?.models ?? []).map((model_entry) => (
            <option key={model_entry.id} value={model_entry.id}>
              {model_entry.label}
            </option>
          ))}
        </datalist>
        {models_query.isLoading ? (
          <span className="text-muted-foreground">
            Loading model catalogue...
          </span>
        ) : null}
        {models_query.isError ? (
          <span className="text-destructive">
            Could not load model catalogue.
          </span>
        ) : null}
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
          className="rounded-md border bg-background px-2 py-1 text-sm"
          placeholder="OPENROUTER_API_KEY"
          value={form.watch("api_key_env") ?? ""}
          onChange={(event) =>
            form.setValue(
              "api_key_env",
              event.target.value === "" ? null : event.target.value,
              { shouldDirty: true },
            )
          }
        />
        <span className="text-muted-foreground">
          Name of the environment variable the worker reads the key
          from at run time.
        </span>
      </label>

      <div className="grid grid-cols-3 gap-2">
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
          <span className="font-medium">max_tokens summary</span>
          <input
            type="number"
            className="rounded-md border bg-background px-2 py-1 text-sm"
            {...form.register("max_tokens_summary")}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium">max_tokens classification</span>
          <input
            type="number"
            className="rounded-md border bg-background px-2 py-1 text-sm"
            {...form.register("max_tokens_classification")}
          />
        </label>
      </div>
    </form>
  );
}
