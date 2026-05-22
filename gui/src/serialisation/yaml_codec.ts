/**
 * YAML <-> FlowBody codec.
 *
 * Thin wrapper around :mod:`js-yaml` plus :mod:`@/schemas/flow` so
 * the import / export / template-load paths share one validated
 * entry point. Every parsed YAML is validated against
 * :data:`flowBodySchema` before it touches any Zustand store, and
 * every serialised YAML round-trips through the same schema first.
 */

import yaml from "js-yaml";

import { flowBodySchema, type FlowBody } from "@/schemas/flow";

/**
 * Parse a YAML string into a validated :class:`FlowBody`.
 *
 * Accepts either the full document shape
 * (``{"flow": {...}}`` like the files under ``config/flows/``) or
 * the bare flow body shape (what the API layer submits to
 * ``POST /api/schema/validate``).
 *
 * @param text - YAML text to parse.
 * @returns Validated :class:`FlowBody`.
 * @throws :class:`yaml.YAMLException` on invalid YAML or a
 *   :class:`ZodError` when the body fails validation.
 */
export function parseFlowYaml(text: string): FlowBody {
  const raw_document = yaml.load(text) ?? {};
  const candidate_body =
    raw_document &&
    typeof raw_document === "object" &&
    "flow" in (raw_document as Record<string, unknown>)
      ? (raw_document as Record<string, unknown>).flow
      : raw_document;
  return flowBodySchema.parse(candidate_body);
}

/**
 * Serialise a :class:`FlowBody` to YAML.
 *
 * Writes the ``flow:`` envelope so the output matches the on-disk
 * files under ``config/flows/``. Key order is preserved with
 * ``sortKeys: false`` so diffs stay reviewable.
 *
 * @param flow_body - Validated flow body.
 * @returns YAML text.
 */
export function stringifyFlowYaml(flow_body: FlowBody): string {
  return yaml.dump(
    { flow: flow_body },
    {
      sortKeys: false,
      noRefs: true,
      lineWidth: 120,
    },
  );
}
