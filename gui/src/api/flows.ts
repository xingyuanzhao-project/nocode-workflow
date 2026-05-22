/**
 * API client for the ``/api/flow/*`` endpoints.
 *
 * Covers saved-flow CRUD plus ad-hoc / saved run submission and the
 * resume endpoint. The flow body itself is kept as a raw record
 * because the GUI builds it from the graph codec rather than from
 * hand-written typing.
 */

import { z } from "zod";

import { requestJson } from "./client";
import {
  costEstimateResponseSchema,
  flowGetResponseSchema,
  flowListSchema,
  flowSaveResponseSchema,
  type CostEstimateResponse,
  type FlowGetResponse,
  type FlowList,
  type FlowSaveResponse,
} from "@/schemas/flow";
import {
  runStartResponseSchema,
  runStatusDtoSchema,
  type RunStartResponse,
  type RunStatusDTO,
} from "@/schemas/run";

/**
 * Schema used by endpoints that return ``204 No Content``.
 *
 * ``requestJson`` calls this schema with ``undefined`` when the
 * response has no body; the schema therefore has to accept
 * ``undefined`` and produce a typed nil value.
 */
const noContentSchema = z.unknown().optional();

/** Saved-flow list. */
export function listFlows(): Promise<FlowList> {
  return requestJson({
    method: "GET",
    path: "/api/flow/list",
    responseSchema: flowListSchema,
  });
}

/** Load one saved flow by id. */
export function getFlow(flowId: string): Promise<FlowGetResponse> {
  return requestJson({
    method: "GET",
    path: `/api/flow/${encodeURIComponent(flowId)}`,
    responseSchema: flowGetResponseSchema,
  });
}

/** Create a new saved flow. */
export function createFlow(
  name: string,
  flow: Record<string, unknown>,
): Promise<FlowSaveResponse> {
  return requestJson({
    method: "POST",
    path: "/api/flow",
    responseSchema: flowSaveResponseSchema,
    jsonBody: { name, flow },
  });
}

/** Overwrite an existing saved flow. */
export function updateFlow(
  flowId: string,
  name: string,
  flow: Record<string, unknown>,
): Promise<FlowSaveResponse> {
  return requestJson({
    method: "PUT",
    path: `/api/flow/${encodeURIComponent(flowId)}`,
    responseSchema: flowSaveResponseSchema,
    jsonBody: { name, flow },
  });
}

/** Delete a saved flow. */
export async function deleteFlow(flowId: string): Promise<void> {
  await requestJson({
    method: "DELETE",
    path: `/api/flow/${encodeURIComponent(flowId)}`,
    responseSchema: noContentSchema,
  });
}

/** Duplicate a saved flow under a new name. */
export function duplicateFlow(
  flowId: string,
  newName: string,
): Promise<FlowSaveResponse> {
  return requestJson({
    method: "POST",
    path: `/api/flow/${encodeURIComponent(flowId)}/duplicate`,
    responseSchema: flowSaveResponseSchema,
    jsonBody: { new_name: newName },
  });
}

/** Run an ad-hoc (unsaved) flow body. */
export function runAdhocFlow(
  flow: Record<string, unknown>,
): Promise<RunStartResponse> {
  return requestJson({
    method: "POST",
    path: "/api/flow/run",
    responseSchema: runStartResponseSchema,
    jsonBody: { flow },
  });
}

/** Run a saved flow by id. The body carries no payload. */
export function runSavedFlow(flowId: string): Promise<RunStartResponse> {
  return requestJson({
    method: "POST",
    path: `/api/flow/${encodeURIComponent(flowId)}/run`,
    responseSchema: runStartResponseSchema,
  });
}

/** Re-enqueue a previous run by id (resume). */
export function resumeRun(runId: string): Promise<RunStartResponse> {
  return requestJson({
    method: "POST",
    path: `/api/flow/resume/${encodeURIComponent(runId)}`,
    responseSchema: runStartResponseSchema,
  });
}

/** Poll a run's current status. */
export function getRunStatus(runId: string): Promise<RunStatusDTO> {
  return requestJson({
    method: "GET",
    path: `/api/flow/status/${encodeURIComponent(runId)}`,
    responseSchema: runStatusDtoSchema,
  });
}

/** Request a rough cost estimate before starting a run. */
export function estimateCost(
  flow: Record<string, unknown>,
  row_count: number,
  total_characters: number,
): Promise<CostEstimateResponse> {
  return requestJson({
    method: "POST",
    path: "/api/flow/estimate-cost",
    responseSchema: costEstimateResponseSchema,
    jsonBody: { flow, row_count, total_characters },
  });
}
