/**
 * Settings page for runtime API-key management.
 *
 * Lets the user set ``OPENROUTER_API_KEY`` and ``OPENAI_API_KEY`` in
 * the server's process environment for the current session. Keys are
 * NOT persisted to disk — a server restart clears them.
 *
 * Each provider row shows whether a key is currently configured, a
 * masked input for entering a new key, a "Test" button that validates
 * the key against the provider's ``/models`` endpoint, and a "Save"
 * button that stores the key for the session.
 */

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getProviderStatus,
  setApiKey,
  testApiKey,
  type ApiKeyTestResponse,
  type ProviderName,
  type ProviderStatusItem,
} from "@/api/settings";
import { Button } from "@/components/ui/button";

const PROVIDER_LABELS: Record<ProviderName, string> = {
  openrouter: "OpenRouter",
  openai: "OpenAI",
};

export default function SettingsPage(): JSX.Element {
  const query_client = useQueryClient();

  const status_query = useQuery({
    queryKey: ["provider-status"],
    queryFn: getProviderStatus,
  });

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col gap-6 overflow-auto p-6">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage API keys for LLM providers. Keys are stored in the
          server&apos;s memory for this session only and are not written
          to disk.
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
        <div className="flex flex-col gap-4">
          {status_query.data?.providers.map((provider_item) => (
            <ProviderKeyRow
              key={provider_item.provider}
              provider_item={provider_item}
              on_saved={() =>
                query_client.invalidateQueries({
                  queryKey: ["provider-status"],
                })
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ProviderKeyRowProps {
  provider_item: ProviderStatusItem;
  on_saved: () => void;
}

function ProviderKeyRow({
  provider_item,
  on_saved,
}: ProviderKeyRowProps): JSX.Element {
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
    if (key_input.trim()) {
      save_mutation.mutate();
    }
  }, [key_input, save_mutation]);

  const handle_test = useCallback(() => {
    if (key_input.trim()) {
      set_test_result(null);
      test_mutation.mutate();
    }
  }, [key_input, test_mutation]);

  const label = PROVIDER_LABELS[provider_item.provider];

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold">{label}</h2>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            provider_item.configured
              ? "bg-green-100 text-green-700"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {provider_item.configured ? "Configured" : "Not configured"}
        </span>
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
            if (event.key === "Enter") {
              handle_save();
            }
          }}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={handle_test}
          disabled={!key_input.trim() || test_mutation.isPending}
        >
          {test_mutation.isPending ? "Testing..." : "Test Connection"}
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
