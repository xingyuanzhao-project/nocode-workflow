/**
 * Codec from a server :class:`FlowBody` to the GUI graph.
 *
 * Reverses :func:`graphToFlowConfig`: fans the flow out into a
 * canonical canvas layout (DataSource → processors → CSVOutput,
 * with the LLM providers, taxonomy, and prompts floating below the
 * main chain), and returns the nodes/edges ready to feed
 * :class:`@/stores/graph_store`.
 */

import type {
  AsyncConfig,
  DisplayConfig,
  FlowBody,
  LoggingConfig,
} from "@/schemas/flow";
import type { GraphEdge, GraphNode } from "@/stores/graph_store";

export interface FlowToGraphResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  flow_metadata: {
    name: string;
    description: string;
  };
  flow_settings: {
    schema_version: number;
    processing_limit: number | null;
    async_config: AsyncConfig;
    logging_config: LoggingConfig;
    display_config: DisplayConfig;
  };
}

const DATA_SOURCE_X = 40;
const PROCESSOR_CHAIN_X_START = 360;
const PROCESSOR_CHAIN_X_STEP = 260;
const OUTPUT_X_OFFSET = 260;
const RESOURCES_Y_OFFSET = 200;
const RESOURCES_X_START = 40;
const RESOURCES_X_STEP = 240;

function buildEdgeId(source_id: string, target_id: string): string {
  return `edge_${source_id}__${target_id}`;
}

function buildDataSourceNode(flow_body: FlowBody): GraphNode {
  return {
    id: "csv_input_main",
    type: "csv_input",
    position: { x: DATA_SOURCE_X, y: 40 },
    data: {
      node_type_id: "csv_input",
      label: "CSV input",
      category: "data",
      upload: { stored_path: flow_body.data.input_csv },
      column_roles: flow_body.data.column_roles,
    },
  };
}

function buildProcessorNode(
  step_index: number,
  step_body: FlowBody["steps"][number],
): GraphNode {
  return {
    id: `step_${step_index}_${step_body.type}`,
    type: step_body.type,
    position: {
      x: PROCESSOR_CHAIN_X_START + step_index * PROCESSOR_CHAIN_X_STEP,
      y: 40,
    },
    data: {
      node_type_id: step_body.type,
      label: step_body.type,
      category: "processor",
      unit: step_body.unit,
      group_by: step_body.group_by ?? null,
      llm_resource_id: step_body.llm ?? null,
      mode: step_body.mode ?? null,
      keys: step_body.keys ?? null,
      io_schema: step_body.io_schema ?? null,
      prompts_ref: step_body.prompts_ref ?? null,
      prompt: step_body.prompt ?? null,
      prompt_overrides: step_body.prompt_overrides ?? null,
      has_io_schema_override: Boolean(step_body.io_schema),
      has_prompt_override: Boolean(step_body.prompt || step_body.prompt_overrides),
    },
  };
}

function buildCsvOutputNode(
  flow_body: FlowBody,
  last_processor_index: number,
): GraphNode {
  return {
    id: "csv_output_main",
    type: "csv_output",
    position: {
      x:
        PROCESSOR_CHAIN_X_START +
        (last_processor_index + 1) * PROCESSOR_CHAIN_X_STEP +
        OUTPUT_X_OFFSET / 8,
      y: 40,
    },
    data: {
      node_type_id: "csv_output",
      label: "CSV output",
      category: "data",
      summary_csv: flow_body.output.summary_csv,
      results_csv: flow_body.output.results_csv ?? null,
      states_csv: flow_body.output.states_csv ?? null,
      spans_csv: flow_body.output.spans_csv ?? null,
      extend: flow_body.output.extend ?? false,
    },
  };
}

function buildTaxonomyNode(flow_body: FlowBody, slot_index: number): GraphNode {
  const raw_taxonomy = flow_body.taxonomy;
  const is_hosted = raw_taxonomy.startsWith("taxonomy://");
  return {
    id: "taxonomy_main",
    type: "taxonomy",
    position: {
      x: RESOURCES_X_START + slot_index * RESOURCES_X_STEP,
      y: RESOURCES_Y_OFFSET,
    },
    data: {
      node_type_id: "taxonomy",
      label: "Taxonomy",
      category: "resource",
      taxonomy_id: is_hosted
        ? raw_taxonomy.slice("taxonomy://".length)
        : null,
      taxonomy_path: is_hosted ? "" : raw_taxonomy,
    },
  };
}

function buildPromptsNode(flow_body: FlowBody, slot_index: number): GraphNode {
  return {
    id: "prompts_main",
    type: "prompts",
    position: {
      x: RESOURCES_X_START + slot_index * RESOURCES_X_STEP,
      y: RESOURCES_Y_OFFSET,
    },
    data: {
      node_type_id: "prompts",
      label: "Prompts",
      category: "resource",
      prompts_path: flow_body.prompts,
    },
  };
}

function buildLlmProviderNodes(flow_body: FlowBody, start_slot: number): GraphNode[] {
  return flow_body.resources.map((resource, resource_index) => ({
    id: `llm_provider_${resource.id}`,
    type: "llm_provider",
    position: {
      x:
        RESOURCES_X_START + (start_slot + resource_index) * RESOURCES_X_STEP,
      y: RESOURCES_Y_OFFSET,
    },
    data: {
      node_type_id: "llm_provider",
      label: `LLM: ${resource.id}`,
      category: "resource",
      resource_id: resource.id,
      provider: resource.provider,
      model: resource.model,
      api_base: resource.api_base ?? null,
      api_key_env: resource.api_key_env ?? null,
      temperature: resource.temperature,
      max_tokens_summary: resource.max_tokens_summary,
      max_tokens_classification: resource.max_tokens_classification,
    },
  }));
}

export function flowConfigToGraph(flow_body: FlowBody): FlowToGraphResult {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  const data_source_node = buildDataSourceNode(flow_body);
  nodes.push(data_source_node);

  const processor_nodes: GraphNode[] = flow_body.steps.map(
    (step_body, step_index) => buildProcessorNode(step_index, step_body),
  );
  for (const processor_node of processor_nodes) {
    nodes.push(processor_node);
  }

  let upstream_id = data_source_node.id;
  for (const processor_node of processor_nodes) {
    edges.push({
      id: buildEdgeId(upstream_id, processor_node.id),
      source: upstream_id,
      target: processor_node.id,
      type: "unit_aware",
    });
    upstream_id = processor_node.id;
  }

  const csv_output_node = buildCsvOutputNode(
    flow_body,
    processor_nodes.length - 1,
  );
  nodes.push(csv_output_node);
  edges.push({
    id: buildEdgeId(upstream_id, csv_output_node.id),
    source: upstream_id,
    target: csv_output_node.id,
    type: "unit_aware",
  });

  const taxonomy_node = buildTaxonomyNode(flow_body, 0);
  const prompts_node = buildPromptsNode(flow_body, 1);
  const llm_provider_nodes = buildLlmProviderNodes(flow_body, 2);

  nodes.push(taxonomy_node, prompts_node, ...llm_provider_nodes);

  return {
    nodes,
    edges,
    flow_metadata: {
      name: flow_body.name,
      description: flow_body.description,
    },
    flow_settings: {
      schema_version: flow_body.schema_version ?? 1,
      processing_limit: flow_body.processing_limit ?? null,
      async_config: flow_body.async,
      logging_config: flow_body.logging,
      display_config: flow_body.display,
    },
  };
}
