/**
 * DOM states the DataSource node exposes to the user.
 *
 * The file picker lives in the property panel; this spec only asserts
 * the compact card summary.
 */

import { describe, expect, it } from "vitest";

import { DataSourceNode } from "@/flow_editor/nodes/data_source_node";

import { renderForUser } from "../_helpers";

function renderCard(data: Record<string, unknown>) {
  const props = {
    id: "csv_input_1",
    type: "csv_input",
    data,
    selected: false,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
    zIndex: 0,
  } as Record<string, unknown>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return renderForUser(<DataSourceNode {...(props as any)} />);
}

describe("DataSourceNode card summary", () => {
  it("shows the empty-state caption when no file has been selected", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: null,
    });
    expect(getByText(/No file selected/i)).toBeInTheDocument();
  });

  it("shows the filename when a file is uploaded", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: {
        filename: "df.csv",
        row_count: 10,
        columns: [{ name: "text" }, { name: "victim" }],
      },
    });
    expect(getByText("df.csv")).toBeInTheDocument();
  });

  it("shows the filename when selected_file is set", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      selected_file: "data/df_text_by_report.csv",
    });
    expect(getByText("df_text_by_report.csv")).toBeInTheDocument();
  });
});
