/**
 * Round-trip tests for the graph-to-FlowBody codec.
 *
 * Two buckets:
 *
 * 1. For each shipped template under ``config/templates/``: parse
 *    YAML → rehydrate into a graph → reassemble a FlowBody → assert
 *    every semantic field round-trips.
 * 2. For a palette-built graph covering every
 *    :data:`KNOWN_NODE_TYPE_IDS`: build the minimum valid topology
 *    with ``buildDefaultNodeData``, user-fill the required fields,
 *    assert :func:`graphToFlowConfig` produces a body that parses
 *    against :data:`flowBodySchema`.
 * 3. Error paths that would have caught real-world regressions:
 *    missing DataSource, two DataSources, unmapped column roles,
 *    disconnected processor.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { buildDefaultNodeData } from "@/flow_editor/nodes/default_node_data";
import { KNOWN_NODE_TYPE_IDS } from "@/flow_editor/nodes/node_types_registry";
import { flowBodySchema, type FlowBody } from "@/schemas/flow";
import type { NodeTypeEntry } from "@/schemas/node_types";
import { flowConfigToGraph } from "@/serialisation/flow_config_to_graph";
import { graphToFlowConfig } from "@/serialisation/graph_to_flow_config";
import { parseFlowYaml } from "@/serialisation/yaml_codec";
import type { GraphEdge, GraphNode } from "@/stores/graph_store";

const PROJECT_ROOT = resolve(__dirname, "..", "..", "..");

const TEMPLATE_FILENAMES = [
  "label_extraction_summary.yml",
  "flat_summary_classification.yml",
  "full_pipeline.yml",
] as const;

function loadTemplateBody(filename: string): FlowBody {
  return parseFlowYaml(
    readFileSync(resolve(PROJECT_ROOT, "config/templates", filename), "utf8"),
  );
}

function canonicalise(flow_body: FlowBody): Record<string, unknown> {
  const parsed = flowBodySchema.parse(flow_body);
  return {
    schema_version: parsed.schema_version,
    name: parsed.name,
    description: parsed.description,
    resources: parsed.resources.map((resource) => ({
      id: resource.id,
      provider: resource.provider,
      model: resource.model,
      api_base: resource.api_base ?? null,
      api_key_env: resource.api_key_env ?? null,
      temperature: resource.temperature,
      max_tokens_summary: resource.max_tokens_summary,
      max_tokens_classification: resource.max_tokens_classification,
    })),
    data: parsed.data,
    taxonomy: parsed.taxonomy,
    prompts: parsed.prompts,
    steps: parsed.steps.map((step) => ({
      type: step.type,
      unit: step.unit,
      group_by: step.group_by ?? null,
      llm: step.llm ?? null,
      mode: step.mode ?? null,
      keys: step.keys ?? null,
    })),
    output: {
      summary_csv: parsed.output.summary_csv,
      results_csv: parsed.output.results_csv ?? null,
      states_csv: parsed.output.states_csv ?? null,
      spans_csv: parsed.output.spans_csv ?? null,
      extend: parsed.output.extend,
    },
  };
}

describe("template round-trips", () => {
  for (const template_filename of TEMPLATE_FILENAMES) {
    it(`${template_filename} survives graph round-trip`, () => {
      const original_body = loadTemplateBody(template_filename);
      const graph_state = flowConfigToGraph(original_body);
      const reassembled = graphToFlowConfig(
        graph_state.nodes,
        graph_state.edges,
        {
          name: graph_state.flow_metadata.name,
          description: graph_state.flow_metadata.description,
          schema_version: graph_state.flow_settings.schema_version,
          processing_limit: graph_state.flow_settings.processing_limit,
          async_config: graph_state.flow_settings.async_config,
          logging_config: graph_state.flow_settings.logging_config,
          display_config: graph_state.flow_settings.display_config,
        },
      );
      expect(canonicalise(reassembled)).toEqual(canonicalise(original_body));
    });
  }
});

function makeEntry(entry_id: string, category: NodeTypeEntry["category"]): NodeTypeEntry {
  return {
    id: entry_id,
    category,
    label: entry_id,
    description: "",
    default_unit: null,
    consumes: [],
    produces: [],
    llm_backed: false,
    requires_resources: [],
    default_io_schema: null,
    default_prompt_ref: null,
    default_group_by: null,
  };
}

function dropNode(
  entry: NodeTypeEntry,
  overrides: Record<string, unknown> = {},
): GraphNode {
  return {
    id: `${entry.id}_test`,
    type: entry.id,
    position: { x: 0, y: 0 },
    data: { ...buildDefaultNodeData(entry), ...overrides },
  };
}

describe("palette-dropped node renders without crash", () => {
  it("every KNOWN_NODE_TYPE_ID produces a valid default payload", () => {
    for (const node_type_id of KNOWN_NODE_TYPE_IDS) {
      const category: NodeTypeEntry["category"] = [
        "csv_input",
        "csv_output",
        "group_by",
      ].includes(node_type_id)
        ? "data"
        : ["llm_provider", "taxonomy", "prompts"].includes(node_type_id)
          ? "resource"
          : "processor";
      const payload = buildDefaultNodeData(makeEntry(node_type_id, category));
      // Regression guard for the DataSource crash: csv_input must
      // expose a non-null ``column_roles`` so ``Object.values`` never
      // blows up inside :class:`DataSourceNode`.
      if (node_type_id === "csv_input") {
        expect(payload.column_roles).toBeTypeOf("object");
        expect(payload.upload).toBe(null);
      }
      if (node_type_id === "csv_output") {
        expect(payload.summary_csv).toBeTypeOf("string");
      }
      if (node_type_id === "llm_provider") {
        expect(payload.provider).toBe("openrouter");
      }
    }
  });
});

describe("graph assembled from palette drops serialises cleanly", () => {
  it("minimal palette-built flow validates under flowBodySchema", () => {
    const data_source = dropNode(makeEntry("csv_input", "data"), {
      upload: { stored_path: "data/df_text_by_report.csv" },
      column_roles: {
        text: "text",
        entity_id: "victim",
        doc_id: "index",
        sort_by: "index",
      },
    });
    const processor = dropNode(makeEntry("single_summary", "processor"), {
      unit: "row",
    });
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    const taxonomy = dropNode(makeEntry("taxonomy", "resource"));
    const prompts = dropNode(makeEntry("prompts", "resource"));
    const llm_provider = dropNode(makeEntry("llm_provider", "resource"), {
      model: "meta-llama/llama-3.1-70b-instruct",
    });
    const nodes: GraphNode[] = [
      data_source,
      processor,
      csv_output,
      taxonomy,
      prompts,
      llm_provider,
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: data_source.id, target: processor.id },
      { id: "e2", source: processor.id, target: csv_output.id },
    ];
    const body = graphToFlowConfig(nodes, edges, {
      name: "palette built",
      description: "",
    });
    expect(() => flowBodySchema.parse(body)).not.toThrow();
    expect(body.steps.length).toBe(1);
  });
});

describe("graph assembly error paths", () => {
  it("missing DataSource raises a helpful error", () => {
    const processor = dropNode(makeEntry("single_summary", "processor"), {
      unit: "row",
    });
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    expect(() =>
      graphToFlowConfig([processor, csv_output], [], {
        name: "no source",
        description: "",
      }),
    ).toThrow(/csv_input/);
  });

  it("two DataSources raise a helpful error", () => {
    const first = dropNode(makeEntry("csv_input", "data"), {
      upload: { stored_path: "data/df_text_by_report.csv" },
      column_roles: {
        text: "text",
        entity_id: "victim",
        doc_id: "index",
        sort_by: "index",
      },
    });
    const second = { ...first, id: "csv_input_other" };
    const processor = dropNode(makeEntry("single_summary", "processor"), {
      unit: "row",
    });
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    const taxonomy = dropNode(makeEntry("taxonomy", "resource"));
    const prompts = dropNode(makeEntry("prompts", "resource"));
    const llm = dropNode(makeEntry("llm_provider", "resource"), {
      model: "m",
    });
    expect(() =>
      graphToFlowConfig(
        [first, second, processor, csv_output, taxonomy, prompts, llm],
        [],
        { name: "two sources", description: "" },
      ),
    ).toThrow(/exactly one/);
  });

  it("unmapped column roles raise a helpful error", () => {
    const data_source = dropNode(makeEntry("csv_input", "data"), {
      upload: { stored_path: "data/df_text_by_report.csv" },
      column_roles: {},
    });
    const processor = dropNode(makeEntry("single_summary", "processor"), {
      unit: "row",
    });
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    const taxonomy = dropNode(makeEntry("taxonomy", "resource"));
    const prompts = dropNode(makeEntry("prompts", "resource"));
    const llm = dropNode(makeEntry("llm_provider", "resource"), {
      model: "m",
    });
    expect(() =>
      graphToFlowConfig(
        [data_source, processor, csv_output, taxonomy, prompts, llm],
        [
          { id: "e1", source: data_source.id, target: processor.id },
          { id: "e2", source: processor.id, target: csv_output.id },
        ],
        { name: "unmapped", description: "" },
      ),
    ).toThrow(/column role/);
  });

  it("disconnected processor raises a helpful error", () => {
    const data_source = dropNode(makeEntry("csv_input", "data"), {
      upload: { stored_path: "data/df_text_by_report.csv" },
      column_roles: {
        text: "text",
        entity_id: "victim",
        doc_id: "index",
        sort_by: "index",
      },
    });
    const connected_processor = dropNode(
      makeEntry("single_summary", "processor"),
      { unit: "row" },
    );
    const orphan_processor = dropNode(
      makeEntry("classification", "processor"),
      { id: "classification_orphan", unit: "row", keys: "all" },
    );
    orphan_processor.id = "classification_orphan";
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    const taxonomy = dropNode(makeEntry("taxonomy", "resource"));
    const prompts = dropNode(makeEntry("prompts", "resource"));
    const llm = dropNode(makeEntry("llm_provider", "resource"), {
      model: "m",
    });
    expect(() =>
      graphToFlowConfig(
        [
          data_source,
          connected_processor,
          orphan_processor,
          csv_output,
          taxonomy,
          prompts,
          llm,
        ],
        [
          { id: "e1", source: data_source.id, target: connected_processor.id },
          { id: "e2", source: connected_processor.id, target: csv_output.id },
        ],
        { name: "orphan", description: "" },
      ),
    ).toThrow(/not connected/);
  });
});
