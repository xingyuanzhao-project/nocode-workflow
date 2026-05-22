/**
 * DOM assertions for :class:`PromptTab` across the three source
 * modes.
 *
 * The tab derives its visible state from the selected node's data
 * payload. This spec builds each of the three payloads and renders
 * them, asserting the right body appears. The click-then-observe
 * UX lives in e2e where the property panel is fed by the store.
 */

import { describe, expect, it } from "vitest";

import { PromptTab } from "@/flow_editor/property_panel/PromptTab";
import type { GraphNode } from "@/stores/graph_store";

import { renderForUser } from "../_helpers";

function _build_processor_node(extra: Record<string, unknown> = {}): GraphNode {
  return {
    id: "step_1",
    type: "single_summary",
    position: { x: 0, y: 0 },
    data: {
      node_type_id: "single_summary",
      label: "Single",
      category: "processor",
      unit: "row",
      ...extra,
    },
  };
}

describe("PromptTab", () => {
  it("default mode shows three radio options with default selected", () => {
    const { getByLabelText } = renderForUser(
      <PromptTab node={_build_processor_node()} />,
    );
    expect(getByLabelText(/default/i)).toBeChecked();
    expect(getByLabelText(/reference/i)).not.toBeChecked();
    expect(getByLabelText(/inline/i)).not.toBeChecked();
  });

  it("reference mode shows the prompts_ref input", () => {
    const { getByPlaceholderText, getByLabelText } = renderForUser(
      <PromptTab node={_build_processor_node({ prompts_ref: "summary" })} />,
    );
    expect(getByLabelText(/reference/i)).toBeChecked();
    const prompts_ref_input = getByPlaceholderText(/^summary$/i);
    expect(prompts_ref_input).toBeInTheDocument();
    expect(prompts_ref_input).toHaveValue("summary");
  });

  it("inline mode shows the instructions textarea", () => {
    const inline_block = {
      instructions: ["line a", "line b"],
      output_format: { summary: "<text>" },
    };
    const { getByLabelText, getByText } = renderForUser(
      <PromptTab node={_build_processor_node({ prompt: inline_block })} />,
    );
    expect(getByLabelText(/inline/i)).toBeChecked();
    expect(getByText(/Instructions \(one per line\)/i)).toBeInTheDocument();
    expect(getByText(/output_format \(JSON\)/i)).toBeInTheDocument();
  });
});
