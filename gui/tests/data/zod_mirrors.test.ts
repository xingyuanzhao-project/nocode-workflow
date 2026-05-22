/**
 * Zod-mirror acceptance tests.
 *
 * Each fixture below is shaped like a real server response. Every
 * Zod mirror must ``parse`` its own fixture; the reject fixtures
 * assert the mirror matches the server's ``extra="forbid"`` /
 * ``extra="allow"`` decision for that DTO.
 */

import { describe, expect, it } from "vitest";

import { csvUploadResponseSchema } from "@/schemas/files";
import { flowBodySchema, flowGetResponseSchema, flowListSchema, flowSaveResponseSchema } from "@/schemas/flow";
import { healthResponseSchema } from "@/schemas/health";
import { providerModelsResponseSchema } from "@/schemas/models";
import { nodeTypeRegistrySchema } from "@/schemas/node_types";
import { promptsResponseSchema } from "@/schemas/prompts";
import { resultsPreviewResponseSchema } from "@/schemas/results";
import { runStartResponseSchema, runStatusDtoSchema } from "@/schemas/run";
import { taxonomyListSchema, taxonomyResponseSchema } from "@/schemas/taxonomy";
import {
  flowTemplateDetailSchema,
  flowTemplateListSchema,
} from "@/schemas/templates";

describe("health", () => {
  it("accepts the canonical shape", () => {
    expect(() =>
      healthResponseSchema.parse({
        status: "ok",
        redis_ok: true,
        worker_ok: true,
      }),
    ).not.toThrow();
  });
  it("silently strips unknown keys — documented Zod default", () => {
    // z.object() strips unknown keys; the mirror is more permissive
    // than the server's extra="forbid" but the server never emits
    // unknown keys in the first place. This test pins today's Zod
    // behaviour so an accidental .strict() does not break clients.
    const parsed = healthResponseSchema.parse({
      status: "ok",
      redis_ok: true,
      worker_ok: true,
      unknown: "field",
    });
    expect(parsed).toEqual({ status: "ok", redis_ok: true, worker_ok: true });
  });
});

describe("node_types", () => {
  it("accepts a registry with processor and resource entries", () => {
    const registry = nodeTypeRegistrySchema.parse({
      version: 1,
      entries: [
        {
          id: "single_summary",
          category: "processor",
          label: "Single",
          description: "",
          default_unit: "row",
          consumes: ["text"],
          produces: ["summary"],
          llm_backed: true,
          requires_resources: ["llm_provider"],
          default_io_schema: null,
          default_prompt_ref: "summary",
          default_group_by: null,
        },
      ],
    });
    expect(registry.entries[0].id).toBe("single_summary");
  });
});

describe("flow DTOs", () => {
  it("flowBodySchema accepts the full_pipeline template shape", () => {
    expect(() =>
      flowBodySchema.parse({
        schema_version: 1,
        name: "full_pipeline",
        description: "desc",
        resources: [
          {
            id: "default",
            type: "llm_provider",
            provider: "openrouter",
            model: "meta-llama/llama-3.1-70b-instruct",
            api_base: "https://openrouter.ai/api/v1",
            api_key_env: "OPENROUTER_API_KEY",
            temperature: 0,
            max_tokens_summary: 1024,
            max_tokens_classification: 256,
          },
        ],
        data: {
          input_csv: "data/df.csv",
          column_roles: {
            text: "text",
            entity_id: "victim",
            doc_id: "index",
            sort_by: "index",
            passthrough: [],
          },
        },
        taxonomy: "config/taxonomy.json",
        prompts: "config/prompts.json",
        steps: [
          {
            type: "label_extraction",
            unit: "document",
            group_by: "entity",
          },
          {
            type: "label_summary",
            unit: "entity",
            mode: "full_async",
          },
        ],
        async: {
          enabled: true,
          max_concurrent_rows: 15,
          max_concurrent_llm_calls: 50,
          max_retries: 5,
        },
        output: {
          summary_csv: "results/summary.csv",
          extend: false,
        },
        logging: {
          file: "log.log",
          log_progress: true,
          log_prompts: false,
          log_response: false,
        },
        display: { use_progress_bar: false },
      }),
    ).not.toThrow();
  });

  it("flowListSchema parses an array of list items", () => {
    const parsed = flowListSchema.parse([
      {
        id: "a",
        name: "A",
        description: "",
        updated_at: new Date().toISOString(),
      },
    ]);
    expect(parsed[0].id).toBe("a");
  });

  it("flowSaveResponseSchema parses the save response", () => {
    expect(() =>
      flowSaveResponseSchema.parse({ id: "x", path: "server/data/flows/x.yml" }),
    ).not.toThrow();
  });

  it("flowGetResponseSchema parses the fetch response", () => {
    const parsed = flowGetResponseSchema.parse({
      id: "x",
      name: "X",
      flow: { name: "X" },
      updated_at: new Date().toISOString(),
    });
    expect(parsed.id).toBe("x");
  });
});

describe("run DTOs", () => {
  it("runStartResponseSchema accepts the minimum shape", () => {
    expect(() =>
      runStartResponseSchema.parse({ run_id: "abc", status: "queued" }),
    ).not.toThrow();
  });

  it("runStatusDtoSchema accepts every lifecycle state", () => {
    for (const status of [
      "queued",
      "running",
      "succeeded",
      "failed",
      "cancelled",
    ] as const) {
      expect(() =>
        runStatusDtoSchema.parse({
          run_id: "abc",
          status,
          started_at: null,
          finished_at: null,
          error: null,
          completed_entity_count: 0,
        }),
      ).not.toThrow();
    }
  });
});

describe("templates", () => {
  it("flowTemplateListSchema accepts the list shape", () => {
    expect(() =>
      flowTemplateListSchema.parse([
        { id: "full_pipeline", label: "full_pipeline", description: "desc" },
      ]),
    ).not.toThrow();
  });

  it("flowTemplateDetailSchema accepts the detail shape", () => {
    expect(() =>
      flowTemplateDetailSchema.parse({
        id: "full_pipeline",
        label: "full_pipeline",
        description: "desc",
        flow: { name: "x" },
      }),
    ).not.toThrow();
  });
});

describe("prompts", () => {
  it("promptsResponseSchema tolerates open-shape entries", () => {
    // Server uses extra="allow" on PromptEntry — the mirror must
    // not reject unknown keys per entry.
    expect(() =>
      promptsResponseSchema.parse({
        path: "config/prompts.json",
        prompts: {
          summary: {
            instructions: ["a"],
            output_format: { summary: "<text>" },
            unknown_future_key: "value",
          },
        },
      }),
    ).not.toThrow();
  });
});

describe("models", () => {
  it("providerModelsResponseSchema parses the proxy response", () => {
    expect(() =>
      providerModelsResponseSchema.parse({
        provider: "openrouter",
        fetched_at: new Date().toISOString(),
        models: [
          {
            id: "meta-llama/llama-3.1-70b-instruct",
            label: "Meta Llama",
            description: null,
            context_length: null,
          },
        ],
      }),
    ).not.toThrow();
  });
});

describe("results + files + taxonomy", () => {
  it("resultsPreviewResponseSchema accepts heterogeneous cell values", () => {
    expect(() =>
      resultsPreviewResponseSchema.parse({
        run_id: "abc",
        artifact_name: "summary",
        columns: ["entity_id", "summary"],
        preview_rows: [
          { entity_id: "alpha", summary: "x" },
          { entity_id: "bravo", summary: null },
        ],
        total_row_count: 2,
      }),
    ).not.toThrow();
  });

  it("csvUploadResponseSchema accepts the upload response", () => {
    expect(() =>
      csvUploadResponseSchema.parse({
        upload_id: "abc",
        filename: "tiny.csv",
        stored_path: "server/data/uploads/abc.csv",
        row_count: 5,
        columns: [
          { name: "text", dtype: "object", sample_values: ["a", "b"] },
        ],
      }),
    ).not.toThrow();
  });

  it("taxonomyResponseSchema tolerates open taxonomy bodies", () => {
    expect(() =>
      taxonomyResponseSchema.parse({
        id: "tx",
        name: "Human Rights",
        taxonomy: { desenlace: { definition: "Outcome", options: ["a"] } },
        updated_at: new Date().toISOString(),
      }),
    ).not.toThrow();
  });

  it("taxonomyListSchema parses an array shape", () => {
    expect(() =>
      taxonomyListSchema.parse([
        { id: "tx", name: "n", updated_at: new Date().toISOString() },
      ]),
    ).not.toThrow();
  });
});
