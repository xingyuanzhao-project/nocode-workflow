/**
 * Prompt tab of the :mod:`PropertyPanel`.
 *
 * Single text area for the processor's instructions. Shows an info
 * banner when the node uses a shared prompt reference (prompts_ref)
 * without inline instructions.
 */

import { useCallback, useMemo } from "react";

import { useFlowMetadataStore } from "@/stores/flow_metadata_store";
import { useGraphStore, type GraphNode } from "@/stores/graph_store";

function readInstructions(node: GraphNode): string {
  const prompt = node.data.prompt;
  if (prompt && typeof prompt === "object") {
    const instructions = (prompt as Record<string, unknown>).instructions;
    if (Array.isArray(instructions) && instructions.length > 0) {
      return instructions.map(String).join("\n");
    }
  }
  return "";
}

function readPromptsRef(node: GraphNode): string | null {
  const ref = node.data.prompts_ref;
  return typeof ref === "string" && ref.length > 0 ? ref : null;
}

function writeInstructions(text: string): Record<string, unknown> {
  const lines = text.split("\n").filter((line) => line.length > 0);
  return {
    prompt: { instructions: lines },
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

  const instructions = useMemo(() => readInstructions(node), [node]);
  const prompts_ref = useMemo(() => readPromptsRef(node), [node]);

  const on_change = useCallback(
    (text: string) => {
      update_node_data(node.id, writeInstructions(text));
      set_dirty(true);
    },
    [node.id, update_node_data, set_dirty],
  );

  return (
    <div className="flex flex-col gap-3 text-xs">
      {prompts_ref && !instructions ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
          <p className="font-medium">Using prompt reference: {prompts_ref}</p>
          <p className="mt-1 text-muted-foreground">
            This processor uses a shared prompt template. Write instructions
            below to override it with an inline prompt.
          </p>
        </div>
      ) : null}
      <label className="flex flex-col gap-1">
        <span className="font-medium">Instructions</span>
        <textarea
          className="min-h-[12rem] rounded-md border bg-background px-2 py-1 text-sm font-mono"
          placeholder="Write the processing instructions for this step..."
          value={instructions}
          onChange={(event) => on_change(event.target.value)}
        />
        <span className="text-muted-foreground">
          One instruction per line. These are sent as the system prompt
          to the LLM.
        </span>
      </label>
    </div>
  );
}
