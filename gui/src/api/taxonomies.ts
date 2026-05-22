/**
 * API client for the ``/api/taxonomy/*`` endpoints.
 */

import { z } from "zod";

import { requestJson } from "./client";
import {
  taxonomyListSchema,
  taxonomyResponseSchema,
  type TaxonomyList,
  type TaxonomyResponse,
} from "@/schemas/taxonomy";

const noContentSchema = z.unknown().optional();

/** List every saved taxonomy. */
export function listTaxonomies(): Promise<TaxonomyList> {
  return requestJson({
    method: "GET",
    path: "/api/taxonomy",
    responseSchema: taxonomyListSchema,
  });
}

/** Load one taxonomy by id. */
export function getTaxonomy(taxonomyId: string): Promise<TaxonomyResponse> {
  return requestJson({
    method: "GET",
    path: `/api/taxonomy/${encodeURIComponent(taxonomyId)}`,
    responseSchema: taxonomyResponseSchema,
  });
}

/** Create a new taxonomy. */
export function createTaxonomy(
  name: string,
  taxonomy: Record<string, unknown>,
): Promise<TaxonomyResponse> {
  return requestJson({
    method: "POST",
    path: "/api/taxonomy",
    responseSchema: taxonomyResponseSchema,
    jsonBody: { name, taxonomy },
  });
}

/** Overwrite an existing taxonomy. */
export function updateTaxonomy(
  taxonomyId: string,
  name: string,
  taxonomy: Record<string, unknown>,
): Promise<TaxonomyResponse> {
  return requestJson({
    method: "PUT",
    path: `/api/taxonomy/${encodeURIComponent(taxonomyId)}`,
    responseSchema: taxonomyResponseSchema,
    jsonBody: { name, taxonomy },
  });
}

/** Delete a taxonomy. */
export async function deleteTaxonomy(taxonomyId: string): Promise<void> {
  await requestJson({
    method: "DELETE",
    path: `/api/taxonomy/${encodeURIComponent(taxonomyId)}`,
    responseSchema: noContentSchema,
  });
}
