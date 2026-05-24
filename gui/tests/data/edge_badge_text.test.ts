import { describe, expect, it } from "vitest";

import {
  buildEdgeBadgeText,
  type EdgeEndpointSummary,
} from "@/flow_editor/edges/edge_badge_text";

function buildEndpoint(
  overrides: Partial<EdgeEndpointSummary>,
): EdgeEndpointSummary {
  return {
    node_type_id: null,
    category: null,
    unit: null,
    ...overrides,
  };
}

describe("buildEdgeBadgeText", () => {
  it("labels data source -> processor edges as Feed Forward", () => {
    expect(
      buildEdgeBadgeText(
        buildEndpoint({
          node_type_id: "csv_input",
          category: "data",
        }),
        buildEndpoint({
          node_type_id: "processor",
          category: "processor",
          unit: "row",
        }),
      ),
    ).toBe("Feed Forward");
  });

  it("labels processor -> resource edges as Call", () => {
    expect(
      buildEdgeBadgeText(
        buildEndpoint({
          node_type_id: "processor",
          category: "processor",
          unit: "row",
        }),
        buildEndpoint({
          node_type_id: "llm_call",
          category: "resource",
        }),
      ),
    ).toBe("Call");
  });

  it("labels processor -> processor edges as Feed Forward", () => {
    expect(
      buildEdgeBadgeText(
        buildEndpoint({
          node_type_id: "processor",
          category: "processor",
          unit: "row",
        }),
        buildEndpoint({
          node_type_id: "processor",
          category: "processor",
          unit: "row",
        }),
      ),
    ).toBe("Feed Forward");
  });

  it("labels processor -> output edges as Save", () => {
    expect(
      buildEdgeBadgeText(
        buildEndpoint({
          node_type_id: "processor",
          category: "processor",
          unit: "row",
        }),
        buildEndpoint({
          node_type_id: "json_output",
          category: "data",
        }),
      ),
    ).toBe("Save");
  });

  it("falls back to the original source -> target label for unmatched pairs", () => {
    expect(
      buildEdgeBadgeText(
        buildEndpoint({
          node_type_id: "llm_call",
          category: "resource",
        }),
        buildEndpoint({
          node_type_id: "csv_output",
          category: "data",
        }),
      ),
    ).toBe("resource \u2192 data");
  });
});
