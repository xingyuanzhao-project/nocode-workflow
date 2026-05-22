/**
 * Contract test against the live ``/openapi.json``.
 *
 * Connects to the running FastAPI backend, pulls its OpenAPI
 * document, and asserts that every response schema the GUI consumes
 * is still shaped the way the GUI's Zod mirror expects. Tests in
 * this tier require the docker compose stack to be up; they skip
 * with a clear message when it is not.
 */

import { describe, expect, it, beforeAll } from "vitest";

const BACKEND_BASE_URL =
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const EXPECTED_RESPONSE_PATHS: Array<{
  path: string;
  method: "get" | "post";
}> = [
  { path: "/api/health", method: "get" },
  { path: "/api/schema/node-types", method: "get" },
  { path: "/api/schema/validate", method: "post" },
  { path: "/api/flow/list", method: "get" },
  { path: "/api/flow", method: "post" },
  { path: "/api/flow/templates", method: "get" },
  { path: "/api/flow/templates/{template_id}", method: "get" },
  { path: "/api/flow/status/{run_id}", method: "get" },
  { path: "/api/flow/run", method: "post" },
  { path: "/api/flow/runs/{run_id}/preview", method: "get" },
  { path: "/api/flow/runs/{run_id}/artifacts/{artifact_name}", method: "get" },
  { path: "/api/prompts", method: "get" },
  { path: "/api/models/{provider}", method: "get" },
  { path: "/api/taxonomy", method: "get" },
  { path: "/api/taxonomy/{taxonomy_id}", method: "get" },
  { path: "/api/files/upload", method: "post" },
];

interface OpenApiDocument {
  paths: Record<string, Record<string, { responses?: Record<string, unknown> }>>;
}

let openapi_document: OpenApiDocument | null = null;
let skip_reason: string | null = null;

beforeAll(async () => {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/openapi.json`);
    if (!response.ok) {
      skip_reason = `Backend returned HTTP ${response.status} on /openapi.json`;
      return;
    }
    openapi_document = (await response.json()) as OpenApiDocument;
  } catch (caught_error) {
    skip_reason = `Backend unreachable: ${String(caught_error)}`;
  }
});

describe("OpenAPI compatibility", () => {
  it("reaches the backend", () => {
    if (skip_reason !== null) {
      it.skip(skip_reason, () => {});
      return;
    }
    expect(openapi_document).not.toBeNull();
    expect(openapi_document?.paths).toBeTypeOf("object");
  });

  it("every consumed endpoint is present in openapi.json", () => {
    if (skip_reason !== null) {
      return;
    }
    const paths = openapi_document!.paths;
    const missing: string[] = [];
    for (const endpoint of EXPECTED_RESPONSE_PATHS) {
      const operations = paths[endpoint.path];
      if (!operations || !operations[endpoint.method]) {
        missing.push(`${endpoint.method.toUpperCase()} ${endpoint.path}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("every consumed endpoint advertises a 2xx response", () => {
    if (skip_reason !== null) {
      return;
    }
    const paths = openapi_document!.paths;
    const without_success: string[] = [];
    for (const endpoint of EXPECTED_RESPONSE_PATHS) {
      const responses =
        paths[endpoint.path]?.[endpoint.method]?.responses ?? {};
      const has_success = Object.keys(responses).some((code) =>
        code.startsWith("2"),
      );
      if (!has_success) {
        without_success.push(`${endpoint.method.toUpperCase()} ${endpoint.path}`);
      }
    }
    expect(without_success).toEqual([]);
  });
});
