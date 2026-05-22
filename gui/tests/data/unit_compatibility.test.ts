/**
 * 4x4 truth table for :func:`isValidUnitTransition`.
 *
 * Mirrors the authoritative table in :mod:`src.flow_loader` so a
 * change on either side breaks exactly one test and points at the
 * other file.
 */

import { describe, expect, it } from "vitest";

import {
  VALID_ADJACENT_UNIT_TRANSITIONS,
  buildInvalidUnitTransitionMessage,
  isValidUnitTransition,
  type UnitValue,
} from "@/lib/unit_compatibility";

const UNIT_VALUES: ReadonlyArray<UnitValue> = [
  "row",
  "document",
  "entity",
] as const;

describe("isValidUnitTransition", () => {
  it("agrees with the VALID_ADJACENT_UNIT_TRANSITIONS table for every pair", () => {
    for (const from_unit of UNIT_VALUES) {
      for (const to_unit of UNIT_VALUES) {
        const table_entry = VALID_ADJACENT_UNIT_TRANSITIONS.some(
          (pair) => pair[0] === from_unit && pair[1] === to_unit,
        );
        expect(isValidUnitTransition(from_unit, to_unit)).toBe(table_entry);
      }
    }
  });

  it("accepts exactly the four expected pairs", () => {
    const accepted_pairs: Array<[UnitValue, UnitValue]> = [];
    for (const from_unit of UNIT_VALUES) {
      for (const to_unit of UNIT_VALUES) {
        if (isValidUnitTransition(from_unit, to_unit)) {
          accepted_pairs.push([from_unit, to_unit]);
        }
      }
    }
    expect(accepted_pairs.sort()).toEqual(
      [
        ["row", "row"],
        ["document", "document"],
        ["document", "entity"],
        ["entity", "entity"],
      ].sort(),
    );
  });
});

describe("buildInvalidUnitTransitionMessage", () => {
  it("names both endpoints and lists allowed transitions", () => {
    const message = buildInvalidUnitTransitionMessage(
      "Source Node",
      "row",
      "Target Node",
      "entity",
    );
    expect(message).toContain("Source Node");
    expect(message).toContain("Target Node");
    expect(message).toContain("row");
    expect(message).toContain("entity");
    expect(message).toContain("row\u2192row");
    expect(message).toContain("document\u2192entity");
  });
});
