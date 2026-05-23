/**
 * Side-effect module that registers every concrete node and edge subclass
 * with the abstract base classes' factory registries.
 *
 * Imported once at app startup (see ``main.tsx``) and once at the top of
 * any test that constructs nodes/edges via :meth:`BaseNode.from_yaml`,
 * :meth:`BaseNode.from_palette`, :meth:`BaseEdge.from_yaml`, or
 * :meth:`BaseEdge.from_connection`. Without this side effect those
 * factory methods throw "Unknown type" because the registry is empty.
 *
 * Re-exports each class so callers can also import them directly without
 * cycling through the model index.
 */

import { BaseEdge } from "./base_edge";
import { BaseNode } from "./base_node";

import { CodebookInquiryEdge } from "./edges/codebook_inquiry_edge";
import { FeedforwardEdge } from "./edges/feedforward_edge";
import { LLMCallEdge } from "./edges/llm_call_edge";

import {
  CodebookNode,
} from "./nodes/codebook_node";
import {
  CSVInputNode,
  DataSourceNode,
  JSONInputNode,
} from "./nodes/data_source_node";
import {
  LLMCallNode,
} from "./nodes/llm_call_node";
import {
  CSVOutputNode,
  JSONOutputNode,
  OutputNode,
} from "./nodes/output_node";
import {
  ProcessorNode,
} from "./nodes/processor_node";

let already_registered = false;

/**
 * Populate the static node/edge registries. Idempotent — safe to call
 * from multiple entry points (app bootstrap, individual test files).
 */
export function register_flow_model_classes(): void {
  if (already_registered) {
    return;
  }

  BaseNode.register("csv_input", CSVInputNode);
  BaseNode.register("json_input", JSONInputNode);
  BaseNode.register("processor", ProcessorNode);
  BaseNode.register("llm_call", LLMCallNode);
  BaseNode.register("codebook", CodebookNode);
  BaseNode.register("csv_output", CSVOutputNode);
  BaseNode.register("json_output", JSONOutputNode);

  BaseEdge.register("feedforward", FeedforwardEdge, "data-out");
  BaseEdge.register("llm_call", LLMCallEdge, "llm-out");
  BaseEdge.register("codebook_inquiry", CodebookInquiryEdge, "cb-out");

  already_registered = true;
}

register_flow_model_classes();

export {
  BaseEdge,
  BaseNode,
  CodebookInquiryEdge,
  CodebookNode,
  CSVInputNode,
  CSVOutputNode,
  DataSourceNode,
  FeedforwardEdge,
  JSONInputNode,
  JSONOutputNode,
  LLMCallEdge,
  LLMCallNode,
  OutputNode,
  ProcessorNode,
};
