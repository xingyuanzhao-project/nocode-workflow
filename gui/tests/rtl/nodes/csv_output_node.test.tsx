/**
 * DOM assertions for :class:`CSVOutputNode`.
 */

import { describe, expect, it } from "vitest";

import { CSVOutputNode } from "@/flow_editor/nodes/csv_output_node";

import { renderForUser } from "../_helpers";

function render(data: Record<string, unknown>) {
  const props = {
    id: "out_1",
    type: "csv_output",
    data,
    selected: false,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
    zIndex: 0,
  } as Record<string, unknown>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return renderForUser(<CSVOutputNode {...(props as any)} />);
}

describe("CSVOutputNode", () => {
  it("shows 1 of 4 artifacts when only summary_csv is set", () => {
    const { getByText } = render({
      node_type_id: "csv_output",
      label: "CSV output",
      category: "data",
      summary_csv: "results/summary.csv",
      results_csv: null,
      states_csv: null,
      spans_csv: null,
      extend: false,
    });
    expect(getByText(/1\/4 artifacts enabled/i)).toBeInTheDocument();
    expect(getByText(/Overwrite/i)).toBeInTheDocument();
  });

  it("shows 4 of 4 artifacts and Append caption when all slots are set", () => {
    const { getByText } = render({
      node_type_id: "csv_output",
      label: "CSV output",
      category: "data",
      summary_csv: "results/summary.csv",
      results_csv: "results/results.csv",
      states_csv: "results/states.csv",
      spans_csv: "results/spans.csv",
      extend: true,
    });
    expect(getByText(/4\/4 artifacts enabled/i)).toBeInTheDocument();
    expect(getByText(/Append/i)).toBeInTheDocument();
  });
});
