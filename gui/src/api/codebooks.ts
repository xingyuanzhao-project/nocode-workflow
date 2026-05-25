/**
 * API client for the ``/api/codebook/*`` endpoints.
 */

import { z } from "zod";

import { requestJson } from "./client";
import {
  codebookListSchema,
  codebookResponseSchema,
  type CodebookList,
  type CodebookResponse,
} from "@/schemas/codebook";

const noContentSchema = z.unknown().optional();

/** List every saved codebook. */
export function listCodebooks(): Promise<CodebookList> {
  return requestJson({
    method: "GET",
    path: "/api/codebook",
    responseSchema: codebookListSchema,
  });
}

/** Load one codebook by id. */
export function getCodebook(codebookId: string): Promise<CodebookResponse> {
  return requestJson({
    method: "GET",
    path: `/api/codebook/${encodeURIComponent(codebookId)}`,
    responseSchema: codebookResponseSchema,
  });
}

/** Create a new codebook. */
export function createCodebook(
  name: string,
  codebook: Record<string, unknown>,
): Promise<CodebookResponse> {
  return requestJson({
    method: "POST",
    path: "/api/codebook",
    responseSchema: codebookResponseSchema,
    jsonBody: { name, codebook },
  });
}

/** Overwrite an existing codebook. */
export function updateCodebook(
  codebookId: string,
  name: string,
  codebook: Record<string, unknown>,
): Promise<CodebookResponse> {
  return requestJson({
    method: "PUT",
    path: `/api/codebook/${encodeURIComponent(codebookId)}`,
    responseSchema: codebookResponseSchema,
    jsonBody: { name, codebook },
  });
}

/** Delete a codebook. */
export async function deleteCodebook(codebookId: string): Promise<void> {
  await requestJson({
    method: "DELETE",
    path: `/api/codebook/${encodeURIComponent(codebookId)}`,
    responseSchema: noContentSchema,
  });
}
