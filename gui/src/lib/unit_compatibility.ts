/**
 * Unit compatibility — only "row" is supported.
 *
 * Kept as a module for interface stability; all transitions between
 * processors are trivially valid since every processor operates on rows.
 */

import type { UnitValue } from "@/schemas/node_types";

export type { UnitValue };

export const VALID_ADJACENT_UNIT_TRANSITIONS: ReadonlyArray<
  readonly [UnitValue, UnitValue]
> = [["row", "row"]] as const;

export function isValidUnitTransition(
  _previous_unit: UnitValue,
  _current_unit: UnitValue,
): boolean {
  return true;
}

export function buildInvalidUnitTransitionMessage(
  previous_node_label: string,
  _previous_unit: UnitValue,
  current_node_label: string,
  _current_unit: UnitValue,
): string {
  return (
    `"${previous_node_label}" cannot feed "${current_node_label}".`
  );
}
