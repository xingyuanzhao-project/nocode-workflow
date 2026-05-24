/**
 * API Keys page — cloud key management and local endpoint config.
 *
 * Cloud providers (OpenRouter, OpenAI): set API keys via masked input.
 * Local providers (Ollama, vLLM, llama.cpp): set base URL and test
 * connectivity by hitting the ``/models`` endpoint.
 */

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getProviderStatus,
  setApiKey,
  setLocalEndpoint,
  testApiKey,
  testLocalEndpoint,
  type ApiKeyTestResponse,
  type LocalEndpointStatusItem,
  type LocalEndpointTestResponse,
  type LocalProviderName,
  type ProviderName,
  type ProviderStatusItem,
} from "@/api/settings";
import { Button } from "@/components/ui/button";

const CLOUD_PROVIDER_LABELS: Record<ProviderName, string> = {
  openrouter: "OpenRouter",
  openai: "OpenAI",
  claude: "Claude",
  google: "Google",
};

const LOCAL_PROVIDER_LABELS: Record<LocalProviderName, string> = {
  ollama: "Ollama",
  vllm: "vLLM",
  llama_cpp: "llama.cpp",
};

export default function SettingsPage(): JSX.Element {
  const query_client = useQueryClient();

  const status_query = useQuery({
    queryKey: ["provider-status"],
    queryFn: getProviderStatus,
  });

  const invalidate = () =>
    query_client.invalidateQueries({ queryKey: ["provider-status"] });

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col gap-6 overflow-auto p-6">
      <div>
        <h1 className="text-xl font-semibold">API Keys</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage API keys and endpoints for LLM providers. Cloud keys are
          stored in the server&apos;s memory for this session only. Local
          endpoints connect directly without authentication.
        </p>
      </div>

      {status_query.isLoading ? (
        <div className="text-sm text-muted-foreground">
          Loading provider status...
        </div>
      ) : status_query.error ? (
        <div className="rounded-md border border-destructive bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Failed to load provider status.
        </div>
      ) : (
        <>
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Cloud providers
            </h2>
            <div className="flex flex-col gap-4">
              {status_query.data?.providers.map((provider_item) => (
                <CloudProviderRow
                  key={provider_item.provider}
                  provider_item={provider_item}
                  on_saved={invalidate}
                />
              ))}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Local Server
            </h2>
            <p className="mb-3 text-xs text-muted-foreground">
              Connect to Ollama, vLLM, or llama.cpp servers running on
              your machine. All use the OpenAI-compatible API format.
            </p>
            <div className="flex flex-col gap-4">
              {(status_query.data?.local_endpoints ?? []).map(
                (endpoint_item) => (
                  <LocalEndpointRow
                    key={endpoint_item.provider}
                    endpoint_item={endpoint_item}
                    on_saved={invalidate}
                  />
                ),
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

interface CloudProviderRowProps {
  provider_item: ProviderStatusItem;
  on_saved: () => void;
}

function CloudProviderRow({
  provider_item,
  on_saved,
}: CloudProviderRowProps): JSX.Element {
  const [key_input, set_key_input] = useState("");
  const [test_result, set_test_result] =
    useState<ApiKeyTestResponse | null>(null);

  const save_mutation = useMutation({
    mutationFn: () => setApiKey(provider_item.provider, key_input),
    onSuccess: () => {
      set_key_input("");
      set_test_result(null);
      on_saved();
    },
  });

  const test_mutation = useMutation({
    mutationFn: () => testApiKey(provider_item.provider, key_input),
    onSuccess: (response) => set_test_result(response),
  });

  const handle_save = useCallback(() => {
    if (key_input.trim()) save_mutation.mutate();
  }, [key_input, save_mutation]);

  const handle_test = useCallback(() => {
    if (key_input.trim()) {
      set_test_result(null);
      test_mutation.mutate();
    }
  }, [key_input, test_mutation]);

  const label = CLOUD_PROVIDER_LABELS[provider_item.provider];

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold">{label}</h3>
        <StatusBadge configured={provider_item.configured} />
        <span className="ml-auto text-xs text-muted-foreground">
          env: {provider_item.env_var}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          type="password"
          className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground"
          placeholder={`Enter ${label} API key`}
          value={key_input}
          onChange={(event) => {
            set_key_input(event.target.value);
            set_test_result(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") handle_save();
          }}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handle_test}
          disabled={!key_input.trim() || test_mutation.isPending}
        >
          {test_mutation.isPending ? "Testing..." : "Test"}
        </Button>
        <Button
          size="sm"
          onClick={handle_save}
          disabled={!key_input.trim() || save_mutation.isPending}
        >
          {save_mutation.isPending ? "Saving..." : "Save"}
        </Button>
      </div>

      {test_result ? (
        <div
          className={`mt-2 rounded-md px-3 py-1.5 text-xs ${
            test_result.valid
              ? "bg-green-50 text-green-700"
              : "bg-destructive/10 text-destructive"
          }`}
        >
          {test_result.message}
        </div>
      ) : null}

      {save_mutation.error ? (
        <div className="mt-2 rounded-md bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Failed to save key. Check the server connection.
        </div>
      ) : null}
    </div>
  );
}

interface LocalEndpointRowProps {
  endpoint_item: LocalEndpointStatusItem;
  on_saved: () => void;
}

function LocalEndpointRow({
  endpoint_item,
  on_saved,
}: LocalEndpointRowProps): JSX.Element {
  const [url_input, set_url_input] = useState(
    endpoint_item.configured ? endpoint_item.api_base : "",
  );
  const [test_result, set_test_result] =
    useState<LocalEndpointTestResponse | null>(null);

  const save_mutation = useMutation({
    mutationFn: () => setLocalEndpoint(endpoint_item.provider, url_input),
    onSuccess: () => {
      set_test_result(null);
      on_saved();
    },
  });

  const test_mutation = useMutation({
    mutationFn: () => testLocalEndpoint(url_input),
    onSuccess: (response) => set_test_result(response),
  });

  const handle_save = useCallback(() => {
    if (url_input.trim()) save_mutation.mutate();
  }, [url_input, save_mutation]);

  const handle_test = useCallback(() => {
    if (url_input.trim()) {
      set_test_result(null);
      test_mutation.mutate();
    }
  }, [url_input, test_mutation]);

  const label = LOCAL_PROVIDER_LABELS[endpoint_item.provider];

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold">{label}</h3>
        <StatusBadge configured={endpoint_item.configured} />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          type="text"
          className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm font-mono placeholder:text-muted-foreground"
          placeholder={endpoint_item.api_base}
          value={url_input}
          onChange={(event) => {
            set_url_input(event.target.value);
            set_test_result(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") handle_save();
          }}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handle_test}
          disabled={!url_input.trim() || test_mutation.isPending}
        >
          {test_mutation.isPending ? "Testing..." : "Test"}
        </Button>
        <Button
          size="sm"
          onClick={handle_save}
          disabled={!url_input.trim() || save_mutation.isPending}
        >
          {save_mutation.isPending ? "Saving..." : "Save"}
        </Button>
      </div>

      {test_result ? (
        <div
          className={`mt-2 rounded-md px-3 py-1.5 text-xs ${
            test_result.reachable
              ? "bg-green-50 text-green-700"
              : "bg-destructive/10 text-destructive"
          }`}
        >
          {test_result.message}
        </div>
      ) : null}

      {save_mutation.error ? (
        <div className="mt-2 rounded-md bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Failed to save endpoint. Check the server connection.
        </div>
      ) : null}
    </div>
  );
}

function StatusBadge({
  configured,
}: {
  configured: boolean;
}): JSX.Element | null {
  if (!configured) return null;
  return (
    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
      Configured
    </span>
  );
}
