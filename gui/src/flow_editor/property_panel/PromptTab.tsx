/**
 * Prompt tab of the :mod:`PropertyPanel`.
 *
 * Lets the user choose between three prompt-source modes that
 * :class:`src.flow_loader.StepConfig` accepts:
 *
 * - **Default** — omit :attr:`StepConfig.prompt` and
 *   :attr:`StepConfig.prompts_ref`; the runner falls back to
 *   :attr:`NodeTypeEntry.default_prompt_ref`.
 * - **Reference** — set :attr:`StepConfig.prompts_ref` to a key
 *   defined in ``config/prompts.json``, with optional
 *   :attr:`StepConfig.prompt_overrides` for ``append`` / ``prepend`` /
 *   ``replace`` directives.
 * - **Inline** — fully supply an inline :class:`PromptInline`.
 */

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { getPrompts } from "@/api/prompts";
import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

type PromptMode = "default" | "reference" | "inline";

interface PromptTabState {
  mode: PromptMode;
  prompts_ref: string;
  inline_instructions: string;
  inline_output_format: string;
  overrides_append: string;
  overrides_prepend: string;
  overrides_replace: string;
}

function readPromptTabState(node: GraphNode): PromptTabState {
  const prompt_inline = node.data.prompt;
  const prompts_ref = node.data.prompts_ref;
  const prompt_overrides = node.data.prompt_overrides;
  const mode: PromptMode = prompt_inline
    ? "inline"
    : prompts_ref
      ? "reference"
      : "default";
  return {
    mode,
    prompts_ref: typeof prompts_ref === "string" ? prompts_ref : "",
    inline_instructions:
      prompt_inline &&
      typeof prompt_inline === "object" &&
      Array.isArray(
        (prompt_inline as Record<string, unknown>).instructions,
      )
        ? ((prompt_inline as { instructions: string[] }).instructions).join(
            "\n",
          )
        : "",
    inline_output_format:
      prompt_inline &&
      typeof prompt_inline === "object" &&
      (prompt_inline as Record<string, unknown>).output_format
        ? JSON.stringify(
            (prompt_inline as Record<string, unknown>).output_format,
            null,
            2,
          )
        : "",
    overrides_append: readOverrideList(prompt_overrides, "append"),
    overrides_prepend: readOverrideList(prompt_overrides, "prepend"),
    overrides_replace: readOverrideList(prompt_overrides, "replace"),
  };
}

function readOverrideList(
  source: unknown,
  directive: "append" | "prepend" | "replace",
): string {
  if (!source || typeof source !== "object") {
    return "";
  }
  const directive_value = (source as Record<string, unknown>)[directive];
  if (Array.isArray(directive_value)) {
    return directive_value.map((value) => String(value)).join("\n");
  }
  return "";
}

function writeStateToNode(state: PromptTabState): Record<string, unknown> {
  if (state.mode === "default") {
    return {
      prompt: null,
      prompts_ref: null,
      prompt_overrides: null,
    };
  }
  if (state.mode === "reference") {
    const overrides_payload: Record<string, string[]> = {};
    if (state.overrides_append.trim()) {
      overrides_payload.append = state.overrides_append
        .split("\n")
        .filter((line) => line.length > 0);
    }
    if (state.overrides_prepend.trim()) {
      overrides_payload.prepend = state.overrides_prepend
        .split("\n")
        .filter((line) => line.length > 0);
    }
    if (state.overrides_replace.trim()) {
      overrides_payload.replace = state.overrides_replace
        .split("\n")
        .filter((line) => line.length > 0);
    }
    return {
      prompt: null,
      prompts_ref: state.prompts_ref || null,
      prompt_overrides:
        Object.keys(overrides_payload).length > 0 ? overrides_payload : null,
    };
  }
  let parsed_output_format: unknown = null;
  if (state.inline_output_format.trim()) {
    try {
      parsed_output_format = JSON.parse(state.inline_output_format);
    } catch {
      parsed_output_format = null;
    }
  }
  return {
    prompt: {
      instructions: state.inline_instructions
        .split("\n")
        .filter((line) => line.length > 0),
      output_format: parsed_output_format,
    },
    prompts_ref: null,
    prompt_overrides: null,
  };
}

export interface PromptTabProps {
  node: GraphNode;
}

export function PromptTab({ node }: PromptTabProps): JSX.Element {
  const update_node_data = useGraphStore((state) => state.update_node_data);
  const set_dirty = useFlowMetadataStore((state) => state.set_dirty);
  const prompts_query = useQuery({
    queryKey: ["prompts-registry"],
    queryFn: getPrompts,
    staleTime: 5 * 60_000,
  });

  const current_state = useMemo(() => readPromptTabState(node), [node]);

  const apply_state = useCallback(
    (next_state: PromptTabState) => {
      update_node_data(node.id, writeStateToNode(next_state));
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  const prompt_keys = Object.keys(prompts_query.data?.prompts ?? {});

  return (
    <div className="flex flex-col gap-3 text-xs">
      <fieldset className="flex flex-col gap-1">
        <legend className="text-xs font-medium">Prompt source</legend>
        {(["default", "reference", "inline"] as const).map((option) => (
          <label key={option} className="flex items-center gap-2">
            <input
              type="radio"
              name="prompt-mode"
              checked={current_state.mode === option}
              onChange={() =>
                apply_state({ ...current_state, mode: option })
              }
            />
            <span className="capitalize">{option}</span>
            <span className="text-muted-foreground">
              {option === "default"
                ? "Registered default prompt for this step type."
                : option === "reference"
                  ? "Pick a key from config/prompts.json and optionally override lines."
                  : "Fully inline instructions and output_format."}
            </span>
          </label>
        ))}
      </fieldset>

      {current_state.mode === "reference" ? (
        <div className="flex flex-col gap-3 rounded-md border bg-card p-3">
          <label className="flex flex-col gap-1">
            <span className="font-medium">prompts_ref key</span>
            <input
              list="prompts_ref_keys"
              className="rounded-md border bg-background px-2 py-1 text-sm"
              placeholder="summary"
              value={current_state.prompts_ref}
              onChange={(event) =>
                apply_state({
                  ...current_state,
                  prompts_ref: event.target.value,
                })
              }
            />
            <datalist id="prompts_ref_keys">
              {prompt_keys.map((prompt_key) => (
                <option key={prompt_key} value={prompt_key} />
              ))}
            </datalist>
          </label>

          <PromptOverrideTextArea
            label="append"
            value={current_state.overrides_append}
            onChange={(next_value) =>
              apply_state({ ...current_state, overrides_append: next_value })
            }
          />
          <PromptOverrideTextArea
            label="prepend"
            value={current_state.overrides_prepend}
            onChange={(next_value) =>
              apply_state({ ...current_state, overrides_prepend: next_value })
            }
          />
          <PromptOverrideTextArea
            label="replace"
            value={current_state.overrides_replace}
            onChange={(next_value) =>
              apply_state({ ...current_state, overrides_replace: next_value })
            }
          />
        </div>
      ) : null}

      {current_state.mode === "inline" ? (
        <div className="flex flex-col gap-3 rounded-md border bg-card p-3">
          <label className="flex flex-col gap-1">
            <span className="font-medium">Instructions (one per line)</span>
            <textarea
              className="min-h-[8rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
              placeholder="If the input is empty, set info_found='FALSE'..."
              value={current_state.inline_instructions}
              onChange={(event) =>
                apply_state({
                  ...current_state,
                  inline_instructions: event.target.value,
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium">output_format (JSON)</span>
            <textarea
              className="min-h-[6rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
              placeholder='{"summary": "<text>", "info_found": "<TRUE|FALSE>"}'
              value={current_state.inline_output_format}
              onChange={(event) =>
                apply_state({
                  ...current_state,
                  inline_output_format: event.target.value,
                })
              }
            />
          </label>
        </div>
      ) : null}

      <details className="rounded-md border bg-card p-3 text-xs">
        <summary className="cursor-pointer font-medium">
          Placeholder reference
        </summary>
        <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
          <li>
            <code>{"{input_text_label}"}</code>
          </li>
          <li>
            <code>{"{related_context_label}"}</code>
          </li>
          <li>
            <code>{"{info_found_label}"}</code>
          </li>
          <li>
            <code>{"{relevant_context_label}"}</code>
          </li>
          <li>
            <code>{"{summary_label}"}</code>
          </li>
          <li>
            <code>{"{previous_summary}"}</code>
          </li>
          <li>
            <code>{"{previous_summary_by_item}"}</code>
          </li>
          <li>
            <code>{"{previous_relevant_context}"}</code>
          </li>
          <li>
            <code>{"{possible_values}"}</code>
          </li>
        </ul>
      </details>
    </div>
  );
}

interface PromptOverrideTextAreaProps {
  label: string;
  value: string;
  onChange: (next_value: string) => void;
}

function PromptOverrideTextArea({
  label,
  value,
  onChange,
}: PromptOverrideTextAreaProps): JSX.Element {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-medium">{label} (one per line)</span>
      <textarea
        className="min-h-[3rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
