/**
 * Codec from GUI graph state to the server's :class:`FlowBody`.
 *
 * Expects the canvas to hold:
 *
 * - Exactly one CSV input (``csv_input``) node.
 * - At least one :attr:`NodeTypeEntry.category` = ``processor`` node.
 * - Zero or more ``llm_provider`` resource nodes (at least one
 *   required by the server schema — a sensible default is injected
 *   if none exist).
 * - Exactly one ``taxonomy`` and one ``prompts`` resource node.
 * - Exactly one ``csv_output`` sink node.
 *
 * Violations raise :class:`Error` with a message that names the
 * offending invariant so the caller can surface it to the user.
 */

import type {
  AsyncConfig,
  ColumnRoles,
  DisplayConfig,
  FlowBody,
  LLMResource,
  LoggingConfig,
  OutputConfig,
  PromptInline,
  PromptOverride,
  StepConfig,
} from "@/schemas/flow";
import type { GraphEdge, GraphNode } from "@/stores/graph_store";

export interface GraphToFlowOptions {
  /** Human-readable flow name. */
  name: string;
  /** Optional description. */
  description?: string;
  /** Schema version, defaults to 1. */
  schema_version?: number;
  /** Processing limit (cap on entity/row count). */
  processing_limit?: number | null;
  /** Async config carried through from the settings store. */
  async_config?: AsyncConfig;
  /** Logging config carried through from the settings store. */
  logging_config?: LoggingConfig;
  /** Display config carried through from the settings store. */
  display_config?: DisplayConfig;
}

const DEFAULT_ASYNC_CONFIG: AsyncConfig = {
  enabled: true,
  max_concurrent_rows: 15,
  max_concurrent_llm_calls: 50,
  max_retries: 5,
};

const DEFAULT_LOGGING_CONFIG: LoggingConfig = {
  file: "processing.log",
  log_progress: true,
  log_prompts: false,
  log_response: false,
};

const DEFAULT_DISPLAY_CONFIG: DisplayConfig = {
  use_progress_bar: false,
};

/**
 * Convert the current graph + settings into a :class:`FlowBody`.
 *
 * @throws :class:`Error` when the graph violates a required
 *   invariant (missing singleton, orphan processor, etc.).
 */
export function graphToFlowConfig(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: GraphToFlowOptions,
): FlowBody {
  const data_source = requireUniqueByTypeId(nodes, "csv_input");
  const taxonomy_node = requireUniqueByTypeId(nodes, "taxonomy");
  const prompts_node = requireUniqueByTypeId(nodes, "prompts");
  const output_sink = requireUniqueByTypeId(nodes, "csv_output");

  const llm_provider_nodes = nodes.filter(
    (node) => node.data.node_type_id === "llm_provider",
  );
  const resources: LLMResource[] =
    llm_provider_nodes.length > 0
      ? llm_provider_nodes.map(buildResourceFromNode)
      : [buildDefaultOpenRouterResource()];

  const processor_nodes = nodes.filter(
    (node) => node.data.category === "processor",
  );
  if (processor_nodes.length === 0) {
    throw new Error(
      "Graph must contain at least one processor node before it can run.",
    );
  }

  const ordered_processor_nodes = orderProcessorsByGraph(
    data_source,
    processor_nodes,
    edges,
  );

  const input_csv = readDataSourceInputCsv(data_source);
  const column_roles = readDataSourceColumnRoles(data_source);
  const taxonomy_path = readTaxonomyPath(taxonomy_node);
  const prompts_path = readPromptsPath(prompts_node);
  const output_config = buildOutputConfig(output_sink);

  const steps: StepConfig[] = ordered_processor_nodes.map(buildStepFromNode);

  return {
    schema_version: options.schema_version ?? 1,
    name: options.name,
    description: options.description ?? "",
    resources,
    data: {
      input_csv,
      column_roles,
    },
    taxonomy: taxonomy_path,
    prompts: prompts_path,
    steps,
    processing_limit: options.processing_limit ?? null,
    async: options.async_config ?? DEFAULT_ASYNC_CONFIG,
    output: output_config,
    logging: options.logging_config ?? DEFAULT_LOGGING_CONFIG,
    display: options.display_config ?? DEFAULT_DISPLAY_CONFIG,
  };
}

function requireUniqueByTypeId(
  nodes: GraphNode[],
  node_type_id: string,
): GraphNode {
  const candidates = nodes.filter(
    (node) => node.data.node_type_id === node_type_id,
  );
  if (candidates.length === 0) {
    throw new Error(
      `Graph is missing a '${node_type_id}' node. Drop one onto the canvas.`,
    );
  }
  if (candidates.length > 1) {
    throw new Error(
      `Graph contains ${candidates.length} '${node_type_id}' nodes; exactly one is allowed.`,
    );
  }
  return candidates[0]!;
}

function readDataSourceInputCsv(data_source: GraphNode): string {
  const upload = data_source.data.upload;
  if (
    upload &&
    typeof upload === "object" &&
    typeof (upload as Record<string, unknown>).stored_path === "string"
  ) {
    return String((upload as Record<string, unknown>).stored_path);
  }
  const direct_path = data_source.data.input_csv;
  if (typeof direct_path === "string" && direct_path.length > 0) {
    return direct_path;
  }
  throw new Error(
    "DataSource node has no stored file path. Upload a data file (CSV, JSON, or JSONL) in its property panel.",
  );
}

function readDataSourceColumnRoles(data_source: GraphNode): ColumnRoles {
  const raw_roles = data_source.data.column_roles;
  if (!raw_roles || typeof raw_roles !== "object" || Array.isArray(raw_roles)) {
    throw new Error(
      "DataSource node is missing column_roles; open its property panel and map columns.",
    );
  }
  const roles_record = raw_roles as Record<string, unknown>;
  const required_role_names = [
    "text",
    "entity_id",
    "doc_id",
    "sort_by",
  ] as const;
  const resolved: Partial<ColumnRoles> = {};
  for (const role_name of required_role_names) {
    const role_value = roles_record[role_name];
    if (typeof role_value !== "string" || role_value.length === 0) {
      throw new Error(
        `DataSource column role '${role_name}' is not mapped.`,
      );
    }
    resolved[role_name] = role_value;
  }
  const passthrough_raw = roles_record.passthrough;
  const passthrough: string[] = Array.isArray(passthrough_raw)
    ? passthrough_raw.map((value) => String(value))
    : [];
  return {
    text: resolved.text as string,
    entity_id: resolved.entity_id as string,
    doc_id: resolved.doc_id as string,
    sort_by: resolved.sort_by as string,
    passthrough,
  };
}

function readTaxonomyPath(taxonomy_node: GraphNode): string {
  const taxonomy_id = taxonomy_node.data.taxonomy_id;
  if (typeof taxonomy_id === "string" && taxonomy_id.length > 0) {
    return `taxonomy://${taxonomy_id}`;
  }
  const taxonomy_path = taxonomy_node.data.taxonomy_path;
  if (typeof taxonomy_path === "string" && taxonomy_path.length > 0) {
    return taxonomy_path;
  }
  throw new Error(
    "Taxonomy node has no path or id. Open its property panel and fill in one.",
  );
}

function readPromptsPath(prompts_node: GraphNode): string {
  const prompts_path = prompts_node.data.prompts_path;
  if (typeof prompts_path === "string" && prompts_path.length > 0) {
    return prompts_path;
  }
  throw new Error(
    "Prompts node has no path. Open its property panel and fill in one.",
  );
}

function buildOutputConfig(output_sink: GraphNode): OutputConfig {
  const data = output_sink.data;
  const summary_csv = data.summary_csv;
  if (typeof summary_csv !== "string" || summary_csv.length === 0) {
    throw new Error(
      "CSVOutput node is missing summary_csv; open its property panel.",
    );
  }
  return {
    summary_csv,
    results_csv:
      typeof data.results_csv === "string" && data.results_csv.length > 0
        ? data.results_csv
        : null,
    states_csv:
      typeof data.states_csv === "string" && data.states_csv.length > 0
        ? data.states_csv
        : null,
    spans_csv:
      typeof data.spans_csv === "string" && data.spans_csv.length > 0
        ? data.spans_csv
        : null,
    extend: Boolean(data.extend),
  };
}

function buildResourceFromNode(node: GraphNode): LLMResource {
  const data = node.data;
  const provider_value = data.provider;
  if (
    provider_value !== "openrouter" &&
    provider_value !== "openai" &&
    provider_value !== "local_vllm"
  ) {
    throw new Error(
      `LLMProvider node has invalid provider=${String(provider_value)}`,
    );
  }
  const resource_id =
    typeof data.resource_id === "string" && data.resource_id.length > 0
      ? data.resource_id
      : "default";
  const model =
    typeof data.model === "string" && data.model.length > 0 ? data.model : "";
  if (!model) {
    throw new Error(
      `LLMProvider node (id=${resource_id}) is missing a model.`,
    );
  }
  return {
    id: resource_id,
    type: "llm_provider",
    provider: provider_value,
    model,
    api_base:
      typeof data.api_base === "string" && data.api_base.length > 0
        ? data.api_base
        : null,
    api_key: null,
    api_key_env:
      typeof data.api_key_env === "string" && data.api_key_env.length > 0
        ? data.api_key_env
        : null,
    temperature:
      typeof data.temperature === "number" ? data.temperature : 0,
    max_tokens_summary:
      typeof data.max_tokens_summary === "number"
        ? data.max_tokens_summary
        : 1024,
    max_tokens_classification:
      typeof data.max_tokens_classification === "number"
        ? data.max_tokens_classification
        : 256,
  };
}

function buildDefaultOpenRouterResource(): LLMResource {
  return {
    id: "default",
    type: "llm_provider",
    provider: "openrouter",
    model: "meta-llama/llama-3.1-70b-instruct",
    api_base: "https://openrouter.ai/api/v1",
    api_key: null,
    api_key_env: "OPENROUTER_API_KEY",
    temperature: 0,
    max_tokens_summary: 1024,
    max_tokens_classification: 256,
  };
}

function buildStepFromNode(processor_node: GraphNode): StepConfig {
  const data = processor_node.data;
  const unit = data.unit;
  if (unit !== "row" && unit !== "document" && unit !== "entity") {
    throw new Error(
      `Processor node ${processor_node.id} has invalid unit=${String(unit)}`,
    );
  }
  const step: StepConfig = {
    type: String(data.node_type_id ?? ""),
    unit,
    group_by:
      typeof data.group_by === "string" && data.group_by.length > 0
        ? data.group_by
        : null,
    llm:
      typeof data.llm_resource_id === "string" && data.llm_resource_id.length > 0
        ? data.llm_resource_id
        : null,
    mode:
      typeof data.mode === "string" && data.mode.length > 0 ? data.mode : null,
    keys: parseKeysField(data.keys),
    io_schema:
      data.io_schema && typeof data.io_schema === "object"
        ? ({
            output: (data.io_schema as Record<string, unknown>).output ?? {},
            ...(data.io_schema as Record<string, unknown>),
          } as StepConfig["io_schema"])
        : null,
    prompts_ref:
      typeof data.prompts_ref === "string" && data.prompts_ref.length > 0
        ? data.prompts_ref
        : null,
    prompt: normalisePromptInline(data.prompt),
    prompt_overrides: normalisePromptOverrides(data.prompt_overrides),
  };
  return step;
}

function normalisePromptInline(raw: unknown): PromptInline | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const instructions = Array.isArray(record.instructions)
    ? record.instructions.map((value) => String(value))
    : [];
  const output_format =
    record.output_format && typeof record.output_format === "object"
      ? (record.output_format as Record<string, unknown>)
      : null;
  return {
    instructions,
    output_format,
  };
}

function normalisePromptOverrides(raw: unknown): PromptOverride | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const result: PromptOverride = {};
  for (const directive of ["append", "prepend", "replace"] as const) {
    const directive_value = record[directive];
    if (Array.isArray(directive_value)) {
      result[directive] = directive_value.map((value) => String(value));
    }
  }
  return Object.keys(result).length > 0 ? result : null;
}

function parseKeysField(raw: unknown): unknown {
  if (raw === null || raw === undefined) {
    return null;
  }
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) {
      return null;
    }
    if (trimmed === "all") {
      return "all";
    }
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  return raw;
}

function orderProcessorsByGraph(
  data_source: GraphNode,
  processor_nodes: GraphNode[],
  edges: GraphEdge[],
): GraphNode[] {
  const processor_by_id = new Map<string, GraphNode>();
  for (const node of processor_nodes) {
    processor_by_id.set(node.id, node);
  }
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const bucket = adjacency.get(edge.source) ?? [];
    bucket.push(edge.target);
    adjacency.set(edge.source, bucket);
  }
  const visited = new Set<string>();
  const ordered: GraphNode[] = [];
  const frontier: string[] = [data_source.id];
  while (frontier.length > 0) {
    const current_id = frontier.shift() as string;
    if (visited.has(current_id)) {
      continue;
    }
    visited.add(current_id);
    const candidate_processor = processor_by_id.get(current_id);
    if (candidate_processor) {
      ordered.push(candidate_processor);
    }
    for (const neighbour_id of adjacency.get(current_id) ?? []) {
      frontier.push(neighbour_id);
    }
  }
  const unvisited_processor_ids = processor_nodes
    .filter((node) => !visited.has(node.id))
    .map((node) => node.id);
  if (unvisited_processor_ids.length > 0) {
    throw new Error(
      `Processor nodes ${unvisited_processor_ids.join(", ")} are not connected to the DataSource.`,
    );
  }
  return ordered;
}
