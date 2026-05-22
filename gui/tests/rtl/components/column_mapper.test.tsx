/**
 * DOM assertions for :class:`ColumnMapper`.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";

import { ColumnMapper } from "@/components/ColumnMapper";

import { renderForUser } from "../_helpers";

const SAMPLE_COLUMNS = [
  { name: "text", dtype: "object", sample_values: [] },
  { name: "victim", dtype: "object", sample_values: [] },
  { name: "index", dtype: "int64", sample_values: [] },
];

describe("ColumnMapper", () => {
  it("shows the placeholder prompt when no columns are available", () => {
    const { getByText } = renderForUser(
      <ColumnMapper
        columns={[]}
        column_roles={{}}
        on_change={() => {}}
      />,
    );
    expect(getByText(/Upload a CSV to map columns/i)).toBeInTheDocument();
  });

  it("shows one select per required role once columns exist", () => {
    const { getAllByRole } = renderForUser(
      <ColumnMapper
        columns={SAMPLE_COLUMNS}
        column_roles={{}}
        on_change={() => {}}
      />,
    );
    expect(getAllByRole("combobox")).toHaveLength(4);
  });

  it("invokes on_change when the user picks a column", () => {
    const on_change_mock = vi.fn();
    const { getByText } = renderForUser(
      <ColumnMapper
        columns={SAMPLE_COLUMNS}
        column_roles={{}}
        on_change={on_change_mock}
      />,
    );
    const select = getByText(/Document text/i).closest("label")!.querySelector(
      "select",
    )!;
    fireEvent.change(select, { target: { value: "text" } });
    expect(on_change_mock).toHaveBeenCalledWith("text", "text");
  });
});
