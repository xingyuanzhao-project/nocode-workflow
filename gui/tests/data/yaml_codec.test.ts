/**
 * Tests for the YAML <-> FlowBody codec.
 *
 * Parses every shipped template as a round-trip smoke; asserts that
 * malformed YAML throws; asserts :func:`stringifyFlowYaml` is
 * idempotent (parse, stringify, parse, compare).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { flowBodySchema } from "@/schemas/flow";
import { parseFlowYaml, stringifyFlowYaml } from "@/serialisation/yaml_codec";

const PROJECT_ROOT = resolve(__dirname, "..", "..", "..");

const TEMPLATE_FILENAMES = [
  "label_extraction_summary.yml",
  "flat_summary_classification.yml",
  "full_pipeline.yml",
] as const;

describe("parseFlowYaml", () => {
  for (const filename of TEMPLATE_FILENAMES) {
    it(`parses ${filename} into a validated FlowBody`, () => {
      const yaml_text = readFileSync(
        resolve(PROJECT_ROOT, "config/templates", filename),
        "utf8",
      );
      const body = parseFlowYaml(yaml_text);
      expect(body.steps.length).toBeGreaterThan(0);
      expect(body.resources[0].id).toBe("default");
    });
  }

  it("raises on a completely malformed YAML document", () => {
    expect(() => parseFlowYaml("steps: [\n  unterminated")).toThrow();
  });

  it("raises when the body fails schema validation", () => {
    // Valid YAML, invalid flow shape (empty steps).
    const broken_yaml = "flow:\n  name: broken\n  steps: []\n";
    expect(() => parseFlowYaml(broken_yaml)).toThrow();
  });
});

describe("stringifyFlowYaml round-trip", () => {
  it("reparsing a stringified body yields a semantically-equal body", () => {
    const yaml_text = readFileSync(
      resolve(PROJECT_ROOT, "config/templates/full_pipeline.yml"),
      "utf8",
    );
    const first_pass = parseFlowYaml(yaml_text);
    const regenerated_yaml = stringifyFlowYaml(first_pass);
    const second_pass = parseFlowYaml(regenerated_yaml);
    expect(flowBodySchema.parse(second_pass)).toEqual(
      flowBodySchema.parse(first_pass),
    );
  });
});
