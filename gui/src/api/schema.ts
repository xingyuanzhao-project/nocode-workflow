/**
 * API client for the ``/api/schema/*`` endpoints.
 *
 * Covers:
 *
 * - ``GET /api/schema/node-types``
 * - ``POST /api/schema/validate``
 */

import { requestJson } from "./client";
import {
  flowValidationResponseSchema,
  type FlowValidationResponse,
} from "@/schemas/flow";
import {
  nodeTypeRegistrySchema,
  type NodeTypeRegistry,
} from "@/schemas/node_types";

/**
 * Fetch the node-type registry that drives the palette and property
 * panel.
 */
export function getNodeTypes(): Promise<NodeTypeRegistry> {
  return requestJson({
    method: "GET",
    path: "/api/schema/node-types",
    responseSchema: nodeTypeRegistrySchema,
  });
}

/**
 * Validate a raw flow body against the server's Pydantic schema.
 *
 * @param flow - Raw flow body (the value under the YAML's ``flow:``
 *   key). The server rewraps it in ``{"flow": ...}`` before calling
 *   :class:`src.flow_loader.FlowSchema.model_validate`.
 */
export function validateFlow(
  flow: Record<string, unknown>,
): Promise<FlowValidationResponse> {
  return requestJson({
    method: "POST",
    path: "/api/schema/validate",
    responseSchema: flowValidationResponseSchema,
    jsonBody: { flow },
  });
}
