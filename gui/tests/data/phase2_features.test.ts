/**
 * Targeted tests for Phase 2 feature additions:
 *
 * - JSON/JSONL extension round-trip through the graph codec.
 * - ``processing_limit`` propagation via the settings store shape.
 * - ``input_file`` alias handling in the Zod ``dataConfigSchema``.
 * - ``costEstimateResponseSchema`` acceptance.
 * - ``passthrough`` field survival in column roles round-trip.
 */

import { describe, expect, it } from "vitest";

import { buildDefaultNodeData } from "@/flow_editor/nodes/default_node_data";
import {
  costEstimateResponseSchema,
  dataConfigSchema,
  flowBodySchema,
  type FlowBody,
} from "@/schemas/flow";
import type { NodeTypeEntry } from "@/schemas/node_types";
import { flowConfigToGraph } from "@/serialisation/flow_config_to_graph";
import { graphToFlowConfig } from "@/serialisation/graph_to_flow_config";
import type { GraphEdge, GraphNode } from "@/stores/graph_store";

function makeEntry(
  entry_id: string,
  category: NodeTypeEntry["category"],
): NodeTypeEntry {
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

function buildMinimalFlowBody(
  input_csv: string,
  processing_limit: number | null = null,
  passthrough: string[] = [],
): FlowBody {
  return flowBodySchema.parse({
    schema_version: 1,
    name: "round_trip_test",
    description: "",
    resources: [
      {
        id: "default",
        type: "llm_provider",
        provider: "openrouter",
        model: "meta-llama/llama-3.1-70b-instruct",
        temperature: 0,
        max_tokens_summary: 1024,
        max_tokens_classification: 256,
      },
    ],
    data: {
      input_csv,
      column_roles: {
        text: "text",
        entity_id: "victim",
        doc_id: "index",
        sort_by: "index",
        passthrough,
      },
    },
    taxonomy: "config/taxonomy.json",
    prompts: "config/prompts.json",
    steps: [{ type: "single_summary", unit: "row" }],
    processing_limit,
    async: {
      enabled: true,
      max_concurrent_rows: 15,
      max_concurrent_llm_calls: 50,
      max_retries: 5,
    },
    output: { summary_csv: "results/summary.csv", extend: false },
    logging: {
      file: "processing.log",
      log_progress: true,
      log_prompts: false,
      log_response: false,
    },
    display: { use_progress_bar: false },
  });
}

describe("JSON/JSONL extension round-trip", () => {
  for (const extension of [".csv", ".json", ".jsonl"] as const) {
    it(`input_csv with ${extension} survives graph round-trip`, () => {
      const input_path = `data/my_data${extension}`;
      const body = buildMinimalFlowBody(input_path);
      expect(body.data.input_csv).toBe(input_path);

      const graph = flowConfigToGraph(body);
      const reassembled = graphToFlowConfig(graph.nodes, graph.edges, {
        name: graph.flow_metadata.name,
        description: graph.flow_metadata.description,
        schema_version: graph.flow_settings.schema_version,
        processing_limit: graph.flow_settings.processing_limit,
      });

      expect(reassembled.data.input_csv).toBe(input_path);
    });
  }
});

describe("input_file alias handling", () => {
  it("dataConfigSchema accepts input_file and maps it to input_csv", () => {
    const parsed = dataConfigSchema.parse({
      input_file: "data/records.jsonl",
      column_roles: {
        text: "text",
        entity_id: "eid",
        doc_id: "did",
        sort_by: "sid",
      },
    });
    expect(parsed.input_csv).toBe("data/records.jsonl");
  });

  it("dataConfigSchema still accepts input_csv directly", () => {
    const parsed = dataConfigSchema.parse({
      input_csv: "data/records.csv",
      column_roles: {
        text: "text",
        entity_id: "eid",
        doc_id: "did",
        sort_by: "sid",
      },
    });
    expect(parsed.input_csv).toBe("data/records.csv");
  });
});

describe("processing_limit propagation", () => {
  it("processing_limit=5 survives graph round-trip", () => {
    const body = buildMinimalFlowBody("data/df.csv", 5);
    expect(body.processing_limit).toBe(5);

    const graph = flowConfigToGraph(body);
    expect(graph.flow_settings.processing_limit).toBe(5);

    const reassembled = graphToFlowConfig(graph.nodes, graph.edges, {
      name: graph.flow_metadata.name,
      description: graph.flow_metadata.description,
      schema_version: graph.flow_settings.schema_version,
      processing_limit: graph.flow_settings.processing_limit,
    });
    expect(reassembled.processing_limit).toBe(5);
  });

  it("processing_limit=null (unlimited) survives round-trip", () => {
    const body = buildMinimalFlowBody("data/df.csv", null);

    const graph = flowConfigToGraph(body);
    expect(graph.flow_settings.processing_limit).toBeNull();

    const reassembled = graphToFlowConfig(graph.nodes, graph.edges, {
      name: graph.flow_metadata.name,
      schema_version: graph.flow_settings.schema_version,
      processing_limit: graph.flow_settings.processing_limit,
    });
    expect(reassembled.processing_limit).toBeNull();
  });
});

describe("passthrough column roles round-trip", () => {
  it("passthrough array survives graph round-trip", () => {
    const passthrough = ["region", "date", "source_id"];
    const body = buildMinimalFlowBody("data/df.csv", null, passthrough);
    expect(body.data.column_roles.passthrough).toEqual(passthrough);

    const graph = flowConfigToGraph(body);
    const reassembled = graphToFlowConfig(graph.nodes, graph.edges, {
      name: graph.flow_metadata.name,
      schema_version: graph.flow_settings.schema_version,
    });
    expect(reassembled.data.column_roles.passthrough).toEqual(passthrough);
  });

  it("empty passthrough defaults to []", () => {
    const body = buildMinimalFlowBody("data/df.csv");
    expect(body.data.column_roles.passthrough).toEqual([]);
  });
});

describe("costEstimateResponseSchema", () => {
  it("accepts a valid cost estimate response", () => {
    const parsed = costEstimateResponseSchema.parse({
      estimated_tokens: 25000,
      estimated_cost_usd: 0.05,
      model: "meta-llama/llama-3.1-70b-instruct",
      step_count: 2,
      message: "Estimated cost for 100 rows: $0.05",
    });
    expect(parsed.estimated_tokens).toBe(25000);
    expect(parsed.estimated_cost_usd).toBe(0.05);
    expect(parsed.model).toBe("meta-llama/llama-3.1-70b-instruct");
    expect(parsed.step_count).toBe(2);
  });

  it("rejects a response missing the model field", () => {
    expect(() =>
      costEstimateResponseSchema.parse({
        estimated_tokens: 25000,
        estimated_cost_usd: 0.05,
        step_count: 2,
        message: "msg",
      }),
    ).toThrow();
  });
});

describe("palette-built graph with .jsonl file serialises cleanly", () => {
  it("flow body validates when data source points to a .jsonl file", () => {
    const data_source = dropNode(makeEntry("csv_input", "data"), {
      upload: { stored_path: "data/records.jsonl" },
      column_roles: {
        text: "body",
        entity_id: "case_id",
        doc_id: "doc_id",
        sort_by: "seq",
      },
    });
    const processor = dropNode(makeEntry("single_summary", "processor"), {
      unit: "row",
    });
    const csv_output = dropNode(makeEntry("csv_output", "data"));
    const taxonomy = dropNode(makeEntry("taxonomy", "resource"));
    const prompts = dropNode(makeEntry("prompts", "resource"));
    const llm = dropNode(makeEntry("llm_provider", "resource"), {
      model: "meta-llama/llama-3.1-70b-instruct",
    });
    const nodes: GraphNode[] = [
      data_source,
      processor,
      csv_output,
      taxonomy,
      prompts,
      llm,
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: data_source.id, target: processor.id },
      { id: "e2", source: processor.id, target: csv_output.id },
    ];
    const body = graphToFlowConfig(nodes, edges, {
      name: "jsonl test",
      description: "",
    });
    expect(() => flowBodySchema.parse(body)).not.toThrow();
    expect(body.data.input_csv).toBe("data/records.jsonl");
  });
});
