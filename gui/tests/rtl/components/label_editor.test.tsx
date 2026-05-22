/**
 * DOM assertions for the taxonomy label editor.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";

import {
  LabelEditor,
  labelEntriesFromJson,
  labelEntriesToJson,
  type LabelEntry,
} from "@/components/LabelEditor";

import { renderForUser } from "../_helpers";

describe("labelEntriesFromJson/labelEntriesToJson round-trip", () => {
  it("preserves passthrough keys through both directions", () => {
    const original = {
      desenlace: {
        definition: "Outcome",
        options: ["muerte", "herido"],
        context_definition: "ctx",
        custom_future_field: "keep me",
      },
    };
    const entries = labelEntriesFromJson(original);
    expect(entries[0].passthrough).toEqual({ custom_future_field: "keep me" });
    const regenerated = labelEntriesToJson(entries);
    expect(regenerated).toEqual(original);
  });
});

describe("LabelEditor UI", () => {
  it("adds a new card when 'Add label' is clicked", () => {
    const on_change_mock = vi.fn();
    const { getByRole, getAllByRole } = renderForUser(
      <LabelEditor entries={[]} on_change={on_change_mock} />,
    );
    fireEvent.click(getByRole("button", { name: /Add label/i }));
    expect(on_change_mock).toHaveBeenCalled();
    const next_entries = on_change_mock.mock.calls[0]![0] as LabelEntry[];
    expect(next_entries).toHaveLength(1);
    // Re-render with the new entries so the user actually sees the
    // card in the DOM.
    const { unmount } = renderForUser(
      <LabelEditor entries={next_entries} on_change={() => {}} />,
    );
    // Four inputs + one textarea + a remove button all appear in the
    // new card. Spot-check presence of at least one textbox.
    expect(getAllByRole("textbox").length).toBeGreaterThan(0);
    unmount();
  });

  it("fires on_change when the user types into a key input", () => {
    const entry: LabelEntry = {
      key: "original",
      definition: "",
      options: [],
      context_definition: "",
      passthrough: {},
    };
    const on_change_mock = vi.fn();
    const { getAllByRole } = renderForUser(
      <LabelEditor entries={[entry]} on_change={on_change_mock} />,
    );
    // First textbox is the key input.
    fireEvent.change(getAllByRole("textbox")[0]!, {
      target: { value: "new_key" },
    });
    expect(on_change_mock).toHaveBeenCalled();
  });
});
