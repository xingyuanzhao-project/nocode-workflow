/**
 * Unit compatibility table mirroring
 * :data:`src.flow_loader.VALID_ADJACENT_UNIT_TRANSITIONS`.
 *
 * The flow loader rejects flows whose adjacent processor steps
 * violate these rules; the GUI enforces the same rules client-side
 * so the user sees the mismatch while drawing the edge instead of
 * after submitting the flow for validation.
 *
 * Any change to ``src/flow_loader.py`` must be mirrored here and
 * vice versa; the vitest suite under ``tests/serialisation`` checks
 * the table matches the server-emitted catalog at runtime.
 */

import type { UnitValue } from "@/schemas/node_types";

export type { UnitValue };

/**
 * Allowed ``(previous_unit, current_unit)`` pairs between
 * neighbouring processing steps.
 */
export const VALID_ADJACENT_UNIT_TRANSITIONS: ReadonlyArray<
  readonly [UnitValue, UnitValue]
> = [
  ["row", "row"],
  ["document", "document"],
  ["document", "entity"],
  ["entity", "entity"],
] as const;

/**
 * Look up the unit-pair in the table.
 *
 * @param previous_unit - Unit of the upstream step.
 * @param current_unit - Unit of the downstream step.
 * @returns ``true`` when the pair appears in
 *   :data:`VALID_ADJACENT_UNIT_TRANSITIONS`.
 */
export function isValidUnitTransition(
  previous_unit: UnitValue,
  current_unit: UnitValue,
): boolean {
  return VALID_ADJACENT_UNIT_TRANSITIONS.some(
    ([from_unit, to_unit]) =>
      from_unit === previous_unit && to_unit === current_unit,
  );
}

/**
 * Return a human-readable error message for an invalid unit pair.
 *
 * Matches the shape of the message the server would emit from
 * :meth:`src.flow_loader.FlowConfig.validate_adjacent_unit_transitions`,
 * so the GUI's rejection reason is consistent with the server's.
 */
export function buildInvalidUnitTransitionMessage(
  previous_node_label: string,
  previous_unit: UnitValue,
  current_node_label: string,
  current_unit: UnitValue,
): string {
  return (
    `"${previous_node_label}" (${previous_unit}) cannot feed ` +
    `"${current_node_label}" (${current_unit}). ` +
    `Allowed transitions: ` +
    VALID_ADJACENT_UNIT_TRANSITIONS.map(
      ([from_unit, to_unit]) => `${from_unit}\u2192${to_unit}`,
    ).join(", ") +
    "."
  );
}
