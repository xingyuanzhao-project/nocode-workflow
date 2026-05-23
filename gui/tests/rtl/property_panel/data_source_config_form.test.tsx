/**
 * DOM assertions for the Data Source config form.
 *
 * This spec focuses on the file-picker state that the property panel
 * derives from ``node.data.selected_file`` plus the backend file list.
 */

import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DataSourceConfigForm } from "@/flow_editor/property_panel/config_forms/DataSourceConfigForm";
import type { GraphNode } from "@/stores/graph_store";

import { renderForUser } from "../_helpers";

const apiMocks = vi.hoisted(() => ({
  listDataFiles: vi.fn(),
  fetchColumnHeaders: vi.fn(),
}));

vi.mock("@/api/files", () => ({
  listDataFiles: apiMocks.listDataFiles,
  fetchColumnHeaders: apiMocks.fetchColumnHeaders,
}));

function buildDataNode(extra: Record<string, unknown> = {}): GraphNode {
  return {
    id: "input_1",
    type: "csv_input",
    position: { x: 0, y: 0 },
    data: {
      node_type_id: "csv_input",
      label: "CSV Input",
      category: "data",
      selected_file: "data/df_text_by_report.csv",
      input_columns: ["text"],
      ...extra,
    },
  };
}

describe("DataSourceConfigForm", () => {
  beforeEach(() => {
    apiMocks.listDataFiles.mockReset();
    apiMocks.fetchColumnHeaders.mockReset();
    apiMocks.listDataFiles.mockResolvedValue({ files: [] });
    apiMocks.fetchColumnHeaders.mockResolvedValue({ columns: [] });
  });

  it("shows the current selected file in the dropdown when the API omits it", async () => {
    renderForUser(<DataSourceConfigForm node={buildDataNode()} />);

    const select = await screen.findByRole("combobox");
    await waitFor(() =>
      expect(select).toHaveValue("data/df_text_by_report.csv"),
    );

    const selected_option = Array.from(
      (select as HTMLSelectElement).options,
    ).find((option) => option.selected);

    expect(selected_option?.value).toBe("data/df_text_by_report.csv");
    expect(selected_option?.text).toBe("df_text_by_report.csv");
  });
});
