/**
 * API client for the preset flow-template endpoints.
 */

import { requestJson } from "./client";
import {
  flowTemplateDetailSchema,
  flowTemplateListSchema,
  type FlowTemplateDetail,
  type FlowTemplateList,
} from "@/schemas/templates";

/** List every preset flow template that loaded cleanly on the server. */
export function listFlowTemplates(): Promise<FlowTemplateList> {
  return requestJson({
    method: "GET",
    path: "/api/flow/templates",
    responseSchema: flowTemplateListSchema,
  });
}

/** Load one preset template's full body. */
export function getFlowTemplate(templateId: string): Promise<FlowTemplateDetail> {
  return requestJson({
    method: "GET",
    path: `/api/flow/templates/${encodeURIComponent(templateId)}`,
    responseSchema: flowTemplateDetailSchema,
  });
}
