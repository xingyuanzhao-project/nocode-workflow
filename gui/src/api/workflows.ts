/**
 * API client for the workflow (preset flow) endpoints.
 */

import { requestJson } from "./client";
import {
  workflowDetailSchema,
  workflowListSchema,
  type WorkflowDetail,
  type WorkflowList,
} from "@/schemas/workflows";

/** List every preset workflow that loaded cleanly on the server. */
export function listWorkflows(): Promise<WorkflowList> {
  return requestJson({
    method: "GET",
    path: "/api/flow/workflows",
    responseSchema: workflowListSchema,
  });
}

/** Load one preset workflow's full body. */
export function getWorkflow(workflowId: string): Promise<WorkflowDetail> {
  return requestJson({
    method: "GET",
    path: `/api/flow/workflows/${encodeURIComponent(workflowId)}`,
    responseSchema: workflowDetailSchema,
  });
}
