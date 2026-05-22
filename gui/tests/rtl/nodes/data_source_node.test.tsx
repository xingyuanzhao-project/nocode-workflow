/**
 * DOM states the DataSource node exposes to the user.
 *
 * The full upload + column-mapping workflow lives in the property
 * panel; this spec only asserts the compact card summary.
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
  it("shows the empty-state caption when no CSV has been uploaded", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: null,
      column_roles: {},
    });
    expect(getByText(/No CSV uploaded yet/i)).toBeInTheDocument();
  });

  it("shows 0 of 4 roles mapped when upload is attached without roles", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: {
        filename: "df.csv",
        row_count: 10,
        columns: [{ name: "text" }, { name: "victim" }],
      },
      column_roles: {},
    });
    expect(getByText(/0\/4 roles mapped/i)).toBeInTheDocument();
  });

  it("shows 4 of 4 roles mapped when the user finished the mapping", () => {
    const { getByText } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: {
        filename: "df.csv",
        row_count: 10,
        columns: [{ name: "text" }],
      },
      column_roles: {
        text: "text",
        entity_id: "victim",
        doc_id: "index",
        sort_by: "index",
      },
    });
    expect(getByText(/4\/4 roles mapped/i)).toBeInTheDocument();
  });

  it("does not crash when column_roles is undefined (regression guard)", () => {
    const { container } = renderCard({
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: null,
    });
    expect(container.textContent).toContain("CSV input");
  });
});
