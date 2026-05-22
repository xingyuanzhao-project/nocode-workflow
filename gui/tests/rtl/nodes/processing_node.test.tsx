/**
 * DOM assertions for :class:`ProcessingNode` under its three
 * unit modes and optional mode/keys fields.
 */

import { describe, expect, it } from "vitest";

import { ProcessingNode } from "@/flow_editor/nodes/processing_node";

import { renderForUser } from "../_helpers";

function renderProcessor(data: Record<string, unknown>) {
  const props = {
    id: "p1",
    type: String(data.node_type_id ?? "single_summary"),
    data,
    selected: false,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
    zIndex: 0,
  } as Record<string, unknown>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return renderForUser(<ProcessingNode {...(props as any)} />);
}

describe("ProcessingNode", () => {
  it("renders row/document/entity unit caption", () => {
    for (const unit of ["row", "document", "entity"] as const) {
      const { container, unmount } = renderProcessor({
        node_type_id: "single_summary",
        label: "Single",
        category: "processor",
        unit,
      });
      expect(container.textContent).toContain("Unit:");
      expect(container.textContent).toContain(unit);
      unmount();
    }
  });

  it("shows mode caption when label_summary step declares mode", () => {
    const { container } = renderProcessor({
      node_type_id: "label_summary",
      label: "Label Summary",
      category: "processor",
      unit: "entity",
      mode: "full_async",
    });
    expect(container.textContent).toContain("Mode:");
    expect(container.textContent).toContain("full_async");
  });

  it("shows override counter when overrides are set", () => {
    const { getByText } = renderProcessor({
      node_type_id: "single_summary",
      label: "Single",
      category: "processor",
      unit: "row",
      has_io_schema_override: true,
      has_prompt_override: true,
    });
    expect(getByText(/2 overrides/i)).toBeInTheDocument();
  });
});
