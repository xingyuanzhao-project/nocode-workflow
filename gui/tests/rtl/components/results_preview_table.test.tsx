/**
 * DOM assertions for :class:`ResultsPreviewTable`.
 */

import { describe, expect, it } from "vitest";

import { ResultsPreviewTable } from "@/components/ResultsPreviewTable";

import { renderForUser } from "../_helpers";

describe("ResultsPreviewTable", () => {
  it("shows the loading caption", () => {
    const { getByText } = renderForUser(
      <ResultsPreviewTable preview={null} is_loading={true} error={null} />,
    );
    expect(getByText(/Loading preview/i)).toBeInTheDocument();
  });

  it("shows the error message when passed an Error", () => {
    const { getByText } = renderForUser(
      <ResultsPreviewTable
        preview={null}
        is_loading={false}
        error={new Error("boom")}
      />,
    );
    expect(getByText(/boom/)).toBeInTheDocument();
  });

  it("shows 'No preview available yet.' when preview is null and not loading", () => {
    const { getByText } = renderForUser(
      <ResultsPreviewTable preview={null} is_loading={false} error={null} />,
    );
    expect(getByText(/No preview available yet/i)).toBeInTheDocument();
  });

  it("renders the header row and a caption with the total count", () => {
    const { getByText, container } = renderForUser(
      <ResultsPreviewTable
        preview={{
          run_id: "abc",
          artifact_name: "summary",
          columns: ["entity_id", "summary"],
          preview_rows: [
            { entity_id: "alpha", summary: "first row" },
          ],
          total_row_count: 17,
        }}
        is_loading={false}
        error={null}
      />,
    );
    expect(getByText(/Showing 1 of 17 rows/i)).toBeInTheDocument();
    expect(getByText("entity_id")).toBeInTheDocument();
    expect(getByText("first row")).toBeInTheDocument();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
  });
});
