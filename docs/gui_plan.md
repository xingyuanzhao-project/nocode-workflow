# MessyText: Config-Driven Flows & GUI Schema Creator

## Overview

This plan has two phases:

1. **Phase 1 — Config-driven flow builder**: a YAML schema that declaratively
   defines a processing pipeline (flow topology, model, data, output paths),
   a Python builder that reads it and instantiates the existing
   `src/processors.py` objects, and a single entry point
   (`scripts/run_custom_flow.py`) that executes any schema.
2. **Phase 2 — GUI drag-and-drop schema creator**: a web application where
   users visually compose a flow, which serialises to the Phase 1 YAML and can
   be executed from the same backend.

Phase 1 is a hard prerequisite for Phase 2.

Project-wide Python documentation and naming standards are collected in the
appendix at the end of this document so the implementation rules stay
available without interrupting the plan.

---

## Current State

| Aspect | Status |
|--------|--------|
| Building blocks | Well-defined in `src/processors.py`: `MessyTextProcessor`, `MessyTextConversationTurnProcessor`, `LabelExtractor`, `TextLabelsSummaryProcessor`, orchestrators |
| Config externalisation | `config/settings*.yaml`, `config/prompts.json`, `config/taxonomy*.json` exist; flow topology is now externalised via `config/flows/*.yml` consumed by `src/flow_loader.py` + `src/flow_builder.py` |
| Script duplication | 5+ model-specific copies (`run_summary_conversation_{70b,qwen,mistral,gemma,gptoss}.py`) that differ only in `settings_*.yaml` path (same flow logic, different model name). Replaced by `scripts/run_custom_flow.py` with a module-level `flow_config` switch |
| LLM backend | Original scripts use local vLLM via `http://localhost:8000/v1`; the builder also supports `openrouter` and `openai` providers through the same OpenAI-compatible client via `resources[].provider` + `api_key_env` |
| Server component | `messy_text_server/main.py` is a mirror of the batch scripts (uses `src/messy_text_processor.py`, not `src/processors.py`) |
| Phase 1 implementation | Config-driven flow builder is live: `src/flow_loader.py` (Pydantic schema + validators), `src/flow_builder.py` (`FlowRunner`, per-step dispatch), `src/node_registry.py` + `config/node_types.yaml` (processor type registry), `src/io_schema.py` (`IOSchema` → `response_format` + prompt `output_format`), `src/prompt_resolver.py` (`prompts_ref` / inline `prompt` / `prompt_overrides` resolution), `scripts/run_custom_flow.py` (entry point with `--resume` flag). Remaining: Phase 2 GUI. |

> **Audit note (2026-05-21):** The status callouts under each numbered
> section were checked against the code currently in this repo.
> **Implemented** means the described capability exists now.
> **Partially implemented** means the core path exists but some planned
> behavior in that section is still missing or diverges from the plan text.

---

## Phase 1: Config-Driven Flow Builder

### 1.1 Flow Schema Format

> **Status: implemented.** The flow YAML schema is live in
> `src/flow_loader.py`, exercised by `config/flows/*.yml`, and covered by
> `tests/src/test_flow_loader.py`.

A single YAML file defines everything needed to run a pipeline.  Example:

```yaml
# config/flows/conversation_summary.yml

flow:
  schema_version: 1               # bumped when the YAML format changes
  name: conversation_summary
  description: "Conversation-based multi-turn entity-level summary"

  # ── LLM providers (named resources) ─────────────────────────────
  # Each resource has an id that processors reference via `llm: <id>`.
  # For single-LLM pipelines, a shorthand `llm:` block is also
  # accepted — the builder normalises it into a one-entry resources
  # list with id "default".
  #
  # API keys are NEVER stored in YAML.  Use `api_key_env` to name
  # the environment variable that holds the secret.  The builder
  # reads it at startup via:
  #     api_key = os.environ[resource.api_key_env]
  # The .env file at project root is loaded by the builder
  # (via python-dotenv or manual os.environ) and is gitignored.
  resources:
    - id: default
      type: llm_provider
      provider: openrouter            # "local_vllm" | "openrouter" | "openai"
      model: meta-llama/llama-3.1-70b-instruct
      api_base: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY  # read from .env, never stored in YAML
      temperature: 0.0
      max_tokens_summary: 1024
      max_tokens_classification: 256

    # To use local vLLM instead, swap the default resource:
    # - id: default
    #   type: llm_provider
    #   provider: local_vllm
    #   model: hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4
    #   api_base: http://localhost:8000/v1
    #   api_key: dummy
    #   temperature: 0.0
    #   max_tokens_summary: 1024
    #   max_tokens_classification: 256

  # ── Data source & column mapping ─────────────────────────────────
  # The user's CSV can have any column names.  The "column_roles"
  # section maps the user's actual column names to the roles that
  # the pipeline requires.  No column name is hard-coded.
  data:
    input_csv: df_text_by_report.csv
    column_roles:
      text:      text            # column containing raw document text
      entity_id: victim          # column that groups rows into entities
      doc_id:    index           # column identifying each document (unique per row)
      sort_by:   index           # column used to order documents within an entity
      # Optional extra columns the user wants carried through to output:
      # passthrough: [source_url, date_published]

  # ── Taxonomy & prompts (reuse existing config files) ───────────
  taxonomy: config/taxonomy.json
  prompts: config/prompts.json

  # ── Pipeline steps (executed in order) ─────────────────────────
  # Every step declares which unit of analysis it operates on.
  # The builder validates that adjacent steps have compatible units.
  #
  # This example matches run_summary_conversation.py:
  # documents are grouped by entity, then processed sequentially
  # within each entity using two prompts:
  #   - summary_first  (first document, no previous context)
  #   - summary_update (subsequent documents, carries previous_summary)
  steps:
    - type: conversation_summary_first
      unit: document              # each LLM call processes one document
      group_by: entity            # documents are grouped by entity
      # First document in entity (no previous_summary).
      # _get_conversation_summary_args selects prompts.summary_first.
      # Output: ProcessorResult with info_found, relevant_context,
      #         summary_by_item, summary.

    - type: conversation_summary_update
      unit: document              # each LLM call processes one document
      group_by: entity            # documents are grouped by entity
      # Subsequent documents in entity (has previous_summary from
      # the prior turn).
      # _get_conversation_summary_args selects prompts.summary_update.
      # The runner checks info_found on each turn; only informative
      # turns update the running_summary.
      # Output: same ProcessorResult structure, with accumulated
      #         summary_by_item and updated summary.

    # Optional follow-up steps (uncomment to add):
    # - type: classification
    #   unit: document            # classifies the entity-level summary
    #   group_by: entity
    #   keys: all                 # or a subset: [desenlace, vic_grupo_social]

    # Evaluation is NOT a built-in step type. It is composed in YAML by
    # using an existing processor (typically `single_summary`) with a
    # custom `io_schema` and an inline `prompt` that instructs the LLM to
    # act as a judge and return evaluation-shaped output fields (e.g.
    # evaluation_score, evaluation_rationale). See
    # `config/flows/evaluation_only.yml` for a worked example.

  # ── Async / concurrency ────────────────────────────────────────
  async:
    enabled: true
    max_concurrent_rows: 15
    max_concurrent_llm_calls: 50
    max_retries: 5

  # ── Output paths ───────────────────────────────────────────────
  # Custom flows write to results_custom/ to avoid overwriting
  # existing production results in results_down_sized/.
  output:
    summary_csv: results_custom/summary.csv
    results_csv: results_custom/results.csv
    states_csv: results_custom/states.csv
    spans_csv: results_custom/spans.csv
    extend: false

  # ── Misc ───────────────────────────────────────────────────────
  logging:
    file: processing.log
    log_progress: true
  display:
    use_progress_bar: true
```

**LLM shorthand.** For single-LLM pipelines, a flat `llm:` block is accepted
as sugar:

```yaml
flow:
  llm:
    provider: local_vllm
    model: hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4
    api_base: http://localhost:8000/v1
    api_key: dummy
```

The builder normalises this into `resources: [{id: "default", type: llm_provider, ...}]`
so that all downstream code only deals with the `resources` list.  Steps
that omit `llm:` are wired to the resource with `id: "default"`.

### 1.2 Builder Module: `src/flow_builder.py`

> **Status: implemented.** The builder and runner are live in
> `src/flow_builder.py` and exercised by
> `tests/src/test_flow_builder_dispatch.py`.

Responsibilities:

1. **Parse & validate** the YAML against a Pydantic model (schema validation).
2. **Load secrets from `.env`** — at startup, load the project-root `.env`
   file (via `python-dotenv` or manual read) into `os.environ`.  For each
   resource that declares `api_key_env`, resolve the actual key:

   ```python
   from dotenv import load_dotenv
   load_dotenv()  # loads .env into os.environ

   for resource in schema.resources:
       if resource.api_key_env:
           resource.api_key = os.environ[resource.api_key_env]
       # resource.api_key is now the real secret; api_key_env is discarded
   ```

   Provider resolution for the OpenAI-compatible client:

   | `provider` | `api_base` | `api_key` |
   |---|---|---|
   | `local_vllm` | `http://localhost:8000/v1` | `"dummy"` (literal, no env var needed) |
   | `openrouter` | `https://openrouter.ai/api/v1` | Resolved from `api_key_env: OPENROUTER_API_KEY` |
   | `openai` | `https://api.openai.com/v1` | Resolved from `api_key_env: OPENAI_API_KEY` |

   All three use the same `AsyncOpenAI(base_url=..., api_key=...)` client —
   the only difference is which URL and key are plugged in.
3. **Map step types to processor classes**.

   The table below is derived from reading every class in `src/processors.py`
   and every `run_*.py` entry point.  Each row documents what the builder
   must instantiate for a given step type, with the actual constructor
   signatures.

   | `type` value | Class(es) instantiated | Constructor args | Public method(s) called by the runner | Notes |
   |---|---|---|---|---|
   | `single_summary` | `AsyncMessyTextProcessor(client, config, taxonomy, logger, llm_semaphore?)` | config needs `model.name`, `processing.{temperature, max_tokens_summary, max_tokens_classification}`, `prompts` (from prompts.json) ; taxonomy needs `context_definitions`, `label_options` | `await .summarize_text(text, doc_id=) → str` | Per-row, no entity grouping. Calls `_get_summary_args` internally. Returns summary string; structured result stored on `.last_summary_result`. |
   | `conversation_summary_first` | `AsyncMessyTextProcessor(client, config, taxonomy, logger)` → wrapped by `AsyncMessyTextConversationTurnProcessor(processor)` | Same config as above; turn processor just wraps the processor | `await turn_processor.process_turn(raw_text, state, doc_id=) → (summary, updated_state)` | Unit: document, grouped by entity. First document in the entity (no `previous_summary`). `_get_conversation_summary_args` selects `prompts.summary_first`. Returns `ProcessorResult` with `info_found`, `relevant_context`, `summary_by_item` (per-label extractive spans), `summary`. |
   | `conversation_summary_update` | Same `AsyncMessyTextConversationTurnProcessor(processor)` (reused from first step) | Same objects, no re-instantiation | `await turn_processor.process_turn(raw_text, state, doc_id=) → (summary, updated_state)` | Unit: document, grouped by entity. Subsequent documents (has `previous_summary` from prior turn). `_get_conversation_summary_args` selects `prompts.summary_update`, which receives `{previous_summary}`, `{previous_relevant_context}`, `{previous_summary_by_item}` from the prior turn's result. Runner owns `MessyTextConversationState` and a `running_summary` string; only informative turns (`info_found != FALSE`) update `running_summary`. |
   | `label_extraction` | One `AsyncLabelExtractor(client, config, label_key, label_definition, logger, llm_semaphore?)` per taxonomy label | config same as above; `label_key` and `label_definition` come from `taxonomy["context_definitions"].items()` | `await .extract_label(text, previous_spans=None, doc_id=) → ProcessorResult` | Per-document × per-label. Returns `ProcessorResult` with `info_found`, `spans` (array of `{span: str}`), `confidence_score`. Calls `_get_label_extract_args` internally using `prompts.label_spans_extract`. |
   | `label_summary` (hybrid) | `AsyncTextLabelsSummaryProcessor(client, config, taxonomy, logger, llm_semaphore?)` | config and taxonomy same as `single_summary` | `await .summarize_from_labels(text, label_results, previous_summary=, doc_id=) → ProcessorResult` | Per-entity, sequential docs. Takes `Dict[label_key, ProcessorResult]` from extraction. Calls `_get_label_summary_args` using `prompts.label_summary_first` or `prompts.label_summary_update`. Returns `ProcessorResult` with `info_found`, `spans_by_item`, `summary`. |
   | `label_summary` (full_async) | Same `AsyncTextLabelsSummaryProcessor` + `AsyncTextConversationOrchestrator(summary_processor)` | Orchestrator wraps the summary processor | Orchestrator: `await .run_conversation(documents, use_progress_bar=) → (summaries, state)` ; then `await summary_processor.synthesize_from_summaries(per_doc_summaries, doc_id=) → ProcessorResult` | Per-entity, all docs concurrent. Orchestrator fires all doc summaries via `asyncio.gather` (no sequential chaining). Then one synthesis call using `prompts.label_synthesis` reconciles per-doc summaries into a single entity-level summary. |
   | `classification` | `AsyncMessyTextProcessor(client, config, taxonomy, logger, llm_semaphore?)` | Same config as `single_summary` | `await .classify_summary(summary, key, doc_id=) → str` | Per-entity or per-row (depends on what precedes it). Takes the summary string + one taxonomy key. Calls `_get_classification_args` using `prompts.classification`. Returns classification string; structured result on `.last_classification_result`. Iterated over all taxonomy keys (or a subset). |

   The concrete list of processor step types the loader accepts lives in
   `config/node_types.yaml` (category `processor`), surfaced through
   `src.node_registry.get_processor_step_types()`. `StepConfig`'s
   `type`-field validator delegates to that registry, so adding a new
   processor step type is a registry-entry change, not a loader change.

   **Evaluation is not a built-in step type.**  Evaluation is composed as
   YAML by reusing an existing processor (typically `single_summary`)
   with a custom `io_schema` and an inline `prompt` that casts the LLM
   as a judge and produces evaluation-shaped output fields (for example
   `evaluation_score`, `evaluation_rationale`).  `config/flows/evaluation_only.yml`
   is the reference implementation.  The previously-planned local-only
   evaluators (`SummaCEvaluator`, `DefaultMetricsEvaluator`) and the LLM-based
   `AsyncGEvalEvaluator` dispatch are intentionally omitted from the
   builder — users who want those exact metrics keep running the legacy
   `run_evaluation.py` script.

   **Shared data structures:**

   - **`ProcessorResult`** (dataclass): Generic container for any LLM call.
     Fields: `task_name`, `model_name`, `declared_fields` (JSON schema
     properties from `response_format`), `values` (parsed output dict),
     `input_text`, `input_struct`, `output_text`, `output_struct`, `doc_id`,
     `error`, `metadata`. Constructed via `ProcessorResult.from_llm_call(
     task_name=, model_name=, request_kwargs=, response=, doc_id=)`.
     Convenience: `.get(field)`, `.has_field(field)`, `.is_no_info()`.

   - **`MessyTextConversationState`** (dataclass): Tracks `turn_index` (int)
     and `results` (list of `ProcessorResult`). Properties: `.last_result`,
     `.last_summary` (returns `results[-1].get("summary")`). Owned by the
     runner, not the processor.

4. **Wire objects** — pass `(client, config, taxonomy, logger)` to each
   constructor; connect step outputs to step inputs.
5. **Return a `FlowRunner`** with a single `.run(df)` method.

Estimated size: ~200–300 lines.

#### Key design decisions

- **No new processing logic.** The builder only instantiates and connects
  existing classes. If a step type doesn't map to an existing class, it's out
  of scope.
- **Provider abstraction.** The `provider` field controls which base URL
  and auth scheme to use. All providers (local vLLM, OpenRouter, OpenAI)
  speak the OpenAI-compatible API, so the only difference is `base_url` +
  `api_key`. No new client libraries needed. API keys are never stored in
  YAML — the `api_key_env` field names the environment variable, loaded
  from the project-root `.env` file (which is gitignored).
- **Schema validation with Pydantic.** Each section of the YAML maps to a
  Pydantic model. Invalid schemas fail fast with clear error messages before
  any LLM call is made.
- **Named presets for stop conditions.** The handful of custom stop conditions
  in current scripts (e.g. `is_informative_summary`) become named strings in
  the schema. Complex custom logic stays in Python scripts.

### 1.3 Entry Point: `scripts/run_custom_flow.py`

> **Status: implemented.** The entry script exists in
> `scripts/run_custom_flow.py`; it keeps the module-level `flow_config`
> switch and now also supports `--resume`.

The entry point follows the same pattern as existing scripts
(`run_summary_conversation.py`, `run_processing.py`, etc.): a module-level
variable holds the YAML path, which can be edited directly in the file
before running.  The checked-in script also adds a `--resume` flag without
changing that module-level flow selection pattern.

```python
# scripts/run_custom_flow.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.flow_builder import build_flow

# ── Set the flow YAML to execute ─────────────────────────────────
# Edit this variable to point at the desired flow configuration.
# This mirrors how run_summary_conversation.py uses a module-level
# `settings = "config/settings.yaml"` variable.
flow_config = "config/flows/conversation_summary.yml"

def main():
    flow = build_flow(Path(flow_config))
    flow.run()

if __name__ == "__main__":
    main()
```

This replaces every model-specific script. Instead of duplicating
`run_summary_conversation_70b.py` / `run_summary_conversation_qwen.py`
(which only differ in the `settings` path), you edit `flow_config` to
point at the desired YAML:

```python
flow_config = "config/flows/conversation_summary.yml"
```

The checked-in script wraps this pattern with `argparse` so `--resume`
can thread `resume=True` into `build_flow(...)`.

### 1.4 Migration Path

> **Status: partially implemented.** The unified flow YAMLs and single
> runner exist under `config/flows/` and `scripts/run_custom_flow.py`, but
> the legacy-script/backward-compat migration path described below is not
> preserved in this repo.

The model-specific scripts (`run_summary_conversation_70b.py`,
`run_summary_conversation_qwen.py`, `run_summary_conversation_mistral.py`,
etc.) are **not** different flows.  They all run the same pipeline logic
and only differ in which `settings_*.yaml` they point at (i.e. model name
and output paths).  Under the flow system a single flow YAML handles any
model — you just change the `resources.model` field.

The **actually distinct flows** in the codebase correspond to different
pipeline topologies:

| Flow | Script today | What it does | Flow YAML |
|------|-------------|-------------|-----------|
| **Naive processing** | `run_processing.py` | Per-row single-pass: `summarize_text()` → `classify_summary()` for every taxonomy key.  No entity grouping.  Each row is independent. | `config/flows/naive_processing.yml` |
| **Summary only** | `run_summary.py` | Per-row `summarize_text()`, no classification. | `config/flows/summary_only.yml` |
| **Conversation summary** | `run_summary_conversation.py` | Group by entity → sequential document-level summarization. Two prompts: `summary_first` (first doc, no prior context) and `summary_update` (subsequent docs, receives `previous_summary` + `previous_summary_by_item` from prior turn). Only informative turns (`info_found != FALSE`) update the running summary. | `config/flows/conversation_summary.yml` |
| **Label conversation (hybrid)** | `run_summary_conversation_by_label.py` (with `async.enabled: false`) | Group by entity → for each doc sequentially: all labels extracted concurrently, then one summary call with `previous_summary` chaining.  Preserves turn-by-turn dependency. | `config/flows/label_conversation_hybrid.yml` |
| **Label conversation (full-async)** | `run_summary_conversation_by_label.py` (with `async.enabled: true`) | Group by entity → ALL labels × ALL documents fired concurrently, ALL per-doc summaries concurrent (no chaining), then ONE synthesis call reconciles them into entity-level summary.  Fastest wall-clock time but no sequential context between documents. | `config/flows/label_conversation_full_async.yml` |
| **Classification only** | `run_classification.py` | Reads existing `summary_all_context` column, runs `classify_summary()` per taxonomy key.  No summarization. | `config/flows/classification_only.yml` |
| **Evaluation (LLM-as-judge)** | _(no equivalent in legacy scripts)_ | A `single_summary` step with a custom `io_schema` (e.g. `evaluation_score`, `evaluation_rationale`) and an inline `prompt` that casts the LLM as a judge and scores an existing `summary_all_context` column. The legacy benchmarks (SummaC, G-Eval, default classification metrics) are not wired into the builder; users who need those keep running `run_evaluation.py` directly. | `config/flows/evaluation_only.yml` |

In this repo, the unified flow YAMLs are the active path.  The legacy
scripts/settings described above are historical context rather than a
parallel path still checked in here.  Switching models is just a field
change in the YAML, not a separate flow.

### 1.5 Data Ingestion & Column Mapping

> **Status: partially implemented.** Batch-side `column_roles` mapping is
> live in `src/flow_loader.py` and `src/flow_builder.py`, but the fuller
> upload/mapper validation workflow described below is only partly present.

#### The problem

The current codebase hard-codes three column names everywhere:

| Hard-coded name | Role | Where it appears |
|-----------------|------|------------------|
| `text` | The raw document content fed to the LLM | Every processor's input loop, `str(row.text)` |
| `victim` | The entity that groups multiple documents | `df.groupby("victim")` in every conversation script |
| `index` | Document identifier / sort key within a group | `group_sorted.sort_values(by="index")`, `doc_ids = list(group_sorted["index"])` |

A different user's CSV might have `article_body`, `case_number`,
`report_id`.  Instead of hard-coding these names, the flow YAML exposes
them as configurable parameters in the `column_roles` section of the
`data:` block.  The `flow_builder` resolves the mapping at startup and
passes the resolved names down to every runner loop.  No column name is
hard-coded in the flow builder or the processors.

#### Solution: `column_roles` in the flow schema

The YAML carries a `column_roles` mapping (shown in the example above).
The `flow_builder` reads it once and resolves the user's actual column
names to the internal roles that the pipeline requires.  Internally the
processors never see `"victim"` — they see whatever the user's column is
called, resolved through the mapping.  The processors themselves accept
`text: str` and `doc_id: Any` as arguments — they never access the
DataFrame directly, so column names are fully handled at the
`FlowRunner` layer.

```yaml
data:
  input_csv: my_data.csv
  column_roles:
    text:      article_body       # user's text column
    entity_id: case_number        # user's grouping column
    doc_id:    report_id          # user's document identifier
    sort_by:   published_date     # user's ordering column
```

#### How mapping propagates through the code

Today the scripts do:

```python
texts = [str(t) for t in group_sorted["text"]]
doc_ids = list(group_sorted["index"])
victim_groups = list(df.groupby("victim"))
```

With the column mapping, `flow_builder.py` resolves roles once at startup:

```python
col = schema.data.column_roles
text_col   = col["text"]       # "article_body"
entity_col = col["entity_id"]  # "case_number"
doc_id_col = col["doc_id"]     # "report_id"
sort_col   = col["sort_by"]    # "published_date"

# Then all downstream code uses the resolved names:
entity_groups = list(df.groupby(entity_col))
for entity_id, group_df in entity_groups:
    group_sorted = group_df.sort_values(by=sort_col)
    texts = [str(t) for t in group_sorted[text_col]]
    doc_ids = list(group_sorted[doc_id_col])
```

The processors themselves (`summarize_text`, `extract_label`, etc.) accept
`text: str` and `doc_id: Any` — they never access the DataFrame directly,
so they don't need to know column names.  The mapping is fully handled in
the `FlowRunner` layer that sits between the schema and the processors.

The `recorders.py` functions (`serialize_result_entry`,
`serialize_state_entry`, `flatten_spans_from_state`) currently use
`victim_id` as a parameter name.  This stays as-is — the runner just
passes the value from whatever column the user mapped to `entity_id`.
The output CSV header can use the original column name or a normalised
one, controlled by a config flag.

#### GUI: Column Mapper widget

In Phase 2, when the user uploads a CSV, the Data Source node shows:

```
┌─────────────────────────────────────────────────────────┐
│  📄 Data Source: my_data.csv (1,247 rows, 8 columns)    │
│                                                         │
│  Detected columns:  [preview: first 5 rows shown]       │
│  ┌──────────────────────────────────────────────────┐   │
│  │ article_body  case_number  report_id  pub_date …│   │
│  │ "El día 15…"  VIC-0042     RPT-118    2019-03-… │   │
│  │ "La familia…" VIC-0042     RPT-119    2019-04-… │   │
│  │ "Según el…"   VIC-0107     RPT-220    2020-01-… │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Map columns to roles:                                  │
│                                                         │
│  Text content   [ article_body  ▾ ]  ← dropdown of cols │
│  Entity ID      [ case_number   ▾ ]                     │
│  Document ID    [ report_id     ▾ ]                     │
│  Sort order     [ pub_date      ▾ ]                     │
│                                                         │
│  Passthrough    [+] source_url  [+] author              │
│                                                         │
│  ✅ Mapping valid: 1,247 rows, 83 entities, avg 15 docs │
└─────────────────────────────────────────────────────────┘
```

Implementation details:
- `POST /api/data/upload` accepts the CSV, stores it, returns column names
  + first N rows as JSON.
- The frontend renders dropdowns populated with those column names.
- Validation runs server-side: check for nulls in mapped columns, check
  that `entity_id` + `doc_id` is a unique key, report group statistics.
- The mapping is written into the `column_roles` section of the YAML.

#### Validation rules

| Check | Failure message |
|-------|----------------|
| `text` column exists in CSV | "Column 'article_body' not found in uploaded file" |
| `entity_id` column exists | "Column 'case_number' not found" |
| `doc_id` column exists | "Column 'report_id' not found" |
| No nulls in `text` column | "3 rows have null text — remove or fill before processing" |
| `entity_id` + `doc_id` is unique | "Duplicate (case_number, report_id) found in 2 rows" |
| At least 1 entity with ≥1 document | Sanity check |

### 1.6 Unit of Analysis — How the Pipeline Actually Processes Data

> **Status: partially implemented.** Batch-side unit values,
> adjacent-step validation, and runner dispatch are live in
> `src/flow_loader.py` and `src/flow_builder.py`, but some of the
> stricter validation and GUI affordances described below remain
> incomplete.

This is the core concept the app was built to solve: documents about the
same entity are scattered across rows, and the pipeline must aggregate them
into entity-level summaries and classifications.  The unit of analysis
shifts at specific points in the pipeline, and the flow schema (and GUI)
must make these transitions explicit.

#### Unit transitions in the current code

Tracing through `run_summary_conversation_by_label.py`:

```
INPUT
  │
  │  Unit: ROW (one row = one document)
  │  Each row has: text, entity_id, doc_id
  │
  ▼
df.groupby(entity_col)                          ← UNIT TRANSITION
  │
  │  Unit: ENTITY GROUP (one group = all documents for one entity)
  │  Each group has: N rows, sorted by sort_col
  │
  ▼
For each document in group:                     ← iterating within group
  │
  │  Unit: DOCUMENT (within entity context)
  │
  ├──▶ Label Extraction (per doc × per label)
  │      Unit: DOCUMENT × LABEL
  │      Output: Dict[label_key → ProcessorResult] per document
  │
  ├──▶ Summary (per doc, with previous_summary from prior doc)
  │      Unit: DOCUMENT (but carries entity-level state)
  │      Output: per-document running summary
  │
  ▼
Synthesis (one call per entity)                  ← UNIT TRANSITION
  │
  │  Unit: ENTITY
  │  Input: list of per-document summaries
  │  Output: single entity-level summary
  │
  ▼
Classification (on entity-level summary)
  │
  │  Unit: ENTITY
  │  Output: per-label classification for the entity
  │
  ▼
OUTPUT
  │  Written back to rows:
  │  - Hybrid: per-row running summary (each row gets the summary as of that turn)
  │  - Full-async: every row gets the same synthesised entity-level summary
  │  Plus: entity-level states, document-level results, span-level spans
```

Contrast with `run_processing.py` (flat pipeline):

```
INPUT
  │
  │  Unit: ROW (one row = one document = one entity)
  │  No grouping.  Each row is independent.
  │
  ├──▶ Summary (per row)
  │      Unit: ROW
  │
  ├──▶ Classification (per row × per label)
  │      Unit: ROW × LABEL
  │
  ▼
OUTPUT
  │  Unit: ROW
  │  Each row gets its own summary + classifications
```

#### What this means for the flow schema

Each step in the YAML declares its `unit`:

```yaml
steps:
  - type: label_extraction
    unit: document              # operates per-document within each entity

  - type: label_summary
    unit: entity                # aggregates across documents → entity-level
    mode: hybrid
    synthesize: true

  - type: classification
    unit: entity                # classifies the entity-level summary
```

The builder validates unit compatibility between adjacent steps:
- `label_extraction` (unit: document) → `label_summary` (unit: entity):
  valid, because `label_summary` is defined as the aggregation step.
- `label_summary` (unit: entity) → `classification` (unit: entity):
  valid, same unit.
- `label_extraction` (unit: document) → `classification` (unit: entity):
  **invalid** — you can't classify an entity-level summary when you only
  have document-level label extractions.  The builder rejects this with:
  "Classification (unit: entity) requires an entity-level summary as input,
  but the previous step outputs document-level label_results."

#### Valid unit values

| Unit | Meaning | What `doc_id` refers to | What `entity_id` refers to |
|------|---------|-------------------------|----------------------------|
| `row` | Each CSV row is independent.  No grouping. | The row identifier | Same as doc_id (1:1) |
| `document` | A single document within an entity group. | The document within the group | The group it belongs to |
| `entity` | One entity (all its documents aggregated). | N/A (entity is the unit) | The entity identifier |

#### How unit awareness changes the flow builder

The `FlowRunner` needs to know the current unit to decide how to loop:

```python
if step.unit == "row":
    # No grouping.  Iterate rows independently.
    for row in df.itertuples():
        result = processor.process(row[text_col], doc_id=row[doc_id_col])

elif step.unit == "document":
    # Grouped.  Iterate documents within each entity.
    for entity_id, group_df in df.groupby(entity_col):
        for doc_id, text in zip(group_df[doc_id_col], group_df[text_col]):
            result = processor.process(text, doc_id=doc_id)

elif step.unit == "entity":
    # Grouped.  One operation per entity (receives all its documents).
    for entity_id, group_df in df.groupby(entity_col):
        results = processor.aggregate(group_df, entity_id=entity_id)
```

The unit also determines what the output looks like:
- `unit: row` → output has same row count as input.
- `unit: document` → output has same row count as input (per-doc result
  written back to each row).
- `unit: entity` → output can be entity-level (one row per entity) or
  broadcast back to all rows of that entity (current behaviour with
  `index_to_summary` dict).

#### GUI: Unit-aware nodes and edges

In Phase 2, the visual graph makes units explicit:

**Colour-coded edges** carry a data schema badge:

```
┌─────────────┐    ROW (1247 rows)     ┌───────────────┐
│ Data Source  │───────────────────────▶│  Group By     │
│ my_data.csv │  text: article_body    │  case_number  │
└─────────────┘  doc_id: report_id     └───────┬───────┘
                                               │
                               ENTITY GROUP    │ (83 entities,
                               (sorted by      │  avg 15 docs)
                                pub_date)      │
                                               ▼
                                    ┌─────────────────┐
                                    │ Label Extraction │
                                    │ unit: document   │
                                    └────────┬────────┘
                                             │
                                  DOCUMENT × LABEL
                                  (1247 × 3 labels)
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Label Summary    │
                                    │ unit: entity     │
                                    │ mode: hybrid     │
                                    └────────┬────────┘
                                             │
                                      ENTITY (83)
                                      summary per entity
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Classification   │
                                    │ unit: entity     │
                                    └────────┬────────┘
                                             │
                                      ENTITY (83)
                                      + classifications
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ CSV Output       │
                                    └─────────────────┘
```

Key GUI behaviours:

1. **The Group By node is mandatory for grouped pipelines.** If the user
   drags a Label Extraction node (unit: document) directly after a Data
   Source node without a Group By in between, the canvas shows an error:
   "Label Extraction operates per-document within an entity group. Add a
   Group By node first to define your entity column."

2. **Edges show the current unit and count.** When the user connects nodes,
   the edge label updates to show what data flows through it:
   `ENTITY GROUP (83 entities, avg 15 docs/entity)`. These counts come from
   the actual uploaded data (the backend computes them at upload time).

3. **The Group By node's property panel is the column mapper.** This is
   where the user selects which column is the entity ID and the sort
   column.  It's not a separate config page — it's the property panel
   of the Group By node on the canvas.

   ```
   ┌─────────────────────────────────────────────────────────────┐
   │  ⚙️  Group By — Properties                                   │
   │                                                              │
   │  Which column groups related documents?       │               │
   │  (e.g. case ID, person ID, project number)    │               │
   │                  [ case_number   ▾ ]                          │
   │                                                              │
   │  Order documents within each group by                        │
   │                  [ pub_date      ▾ ]                          │
   │                                                              │
   │  Preview:                                                      │
   │  ┌────────────┬──────────┬───────────────┐                      │
   │  │ Entity     │ # Docs   │ Date range    │                      │
   │  ├────────────┼──────────┼───────────────┤                      │
   │  │ VIC-0042   │ 12       │ 2019-03 → 20… │                      │
   │  │ VIC-0107   │ 8        │ 2020-01 → 20… │                      │
   │  │ VIC-0231   │ 21       │ 2018-11 → 20… │                      │
   │  │ … (83 total)                          │                      │
   │  └────────────┴──────────┴───────────────┘                      │
   └─────────────────────────────────────────────────────────────────┘
   ```

4. **The Data Source node's property panel is the text-column mapper.**
   The user selects which column contains the text to process and which
   column is the document ID.

   ```
   ┌─────────────────────────────────────────────────────────┐
   │  ⚙️  Data Source — Properties                            │
   │                                                         │
   │  File             my_data.csv (1,247 rows)              │
   │  Text column      [ article_body  ▾ ]                   │
   │  Document ID      [ report_id     ▾ ]                   │
   │  Passthrough cols [+] source_url  [+] author            │
   │                                                         │
   │  Preview (first 3 rows):                                │
   │  ┌────────────────┬────────────┬──────────────────────┐ │
   │  │ report_id      │ case_no    │ article_body         │ │
   │  ├────────────────┼────────────┼──────────────────────┤ │
   │  │ RPT-118        │ VIC-0042   │ "El día 15 de mar…"  │ │
   │  │ RPT-119        │ VIC-0042   │ "La familia denun…"  │ │
   │  │ RPT-220        │ VIC-0107   │ "Según el informe…"  │ │
   │  └────────────────┴────────────┴──────────────────────┘ │
   └─────────────────────────────────────────────────────────┘
   ```

5. **Flat pipeline (no grouping).** If the user's data is one row = one
   entity (no multi-document aggregation needed), they skip the Group By
   node entirely. The pipeline stays at `unit: row` throughout:

   ```
   Data Source → Summary (unit: row) → Classification (unit: row) → Output
   ```

   The summary node's property panel auto-adjusts: when no Group By
   precedes it, it shows single-document summary options.  When a Group By
   precedes it, it shows conversation/sequential/synthesis options.

6. **Unit mismatch validation.** The GUI prevents invalid connections
   in real-time.  If the user tries to connect a `unit: entity` output
   to a `unit: document` input, the edge turns red and a tooltip explains:
   "Classification produces entity-level output (83 entities). Label
   Extraction expects document-level input (1,247 documents). These units
   don't match."

#### How the flat vs grouped decision maps to the YAML

Flat (no `column_roles.entity_id`, no Group By):

```yaml
data:
  input_csv: articles.csv
  column_roles:
    text:   body
    doc_id: article_id

steps:
  - type: summary
    unit: row
  - type: classification
    unit: row
```

Grouped (with `column_roles.entity_id` and Group By):

```yaml
data:
  input_csv: reports.csv
  column_roles:
    text:      article_body
    entity_id: case_number
    doc_id:    report_id
    sort_by:   pub_date

steps:
  - type: label_extraction
    unit: document
  - type: label_summary
    unit: entity
    mode: hybrid
    synthesize: true
  - type: classification
    unit: entity
```

The presence or absence of `entity_id` in `column_roles` is what
determines whether the pipeline is flat or grouped.  The intended rule is
that grouped pipelines require `entity_id`, but the current code still
models `entity_id` as a required `ColumnRoles` field for every flow rather
than enforcing that rule conditionally.

### 1.7 Node Type System

> **Status: partially implemented.** The registry exists in
> `config/node_types.yaml` and `src/node_registry.py`, but only the node
> types needed by the current builder and GUI are implemented.

#### The problem: "node" conflates different things

The plan so far uses "node" loosely for everything on the canvas: a CSV
upload, a grouping operation, an LLM extraction call, a prompt config, an
output file.  These are fundamentally different kinds of things.  A data
source is not a processor.  A taxonomy is not an action.  Mixing them under
one concept makes the architecture unclear and the GUI confusing.

#### Three node categories

Every element on the canvas belongs to exactly one of three categories:

| Category | What it represents | Colour (GUI) | Has prompts? | Has io_schema? |
|----------|--------------------|--------------|-------------|----------------|
| **Data** | A dataset or data state at a point in the pipeline | Blue | No | Yes (describes shape) |
| **Processor** | An operation that transforms data from one state to another | Green | Yes (if LLM-backed) | Yes (defines LLM I/O) |
| **Resource** | A shared config/asset consumed by processors | Grey | No | No |

These categories are **fixed** — they're part of the architecture.  But the
**specific types within each category are extensible**.

#### Node types within each category

Each category has a registry of concrete types.  The registry is a list,
not hard-coded logic.  Adding a new type means adding an entry to the
registry, not changing the app's core code.

**Data nodes** (the things flowing through the pipeline):

| Type | Description | Unit | Shape |
|------|-------------|------|-------|
| `raw_data` | Uploaded CSV, before any processing | row | User's original columns |
| `entity_groups` | Data after grouping by an entity column | entity_group | Groups of rows |
| `label_results` | Per-document extraction results | document × label | `{label_key: ProcessorResult}` per doc |
| `summaries` | Summary text, per-row or per-entity | row \| entity | `{summary: str, info_found: str, ...}` |
| `classifications` | Label classifications applied to summaries | row \| entity | `{label_key: {evidence, result}}` per unit |
| `metrics` | Evaluation scores | row \| entity | `{metric_name: score}` |
| _(future)_ | Any new data state | _(declared)_ | _(declared)_ |

**Processor nodes** (the operations):

| Type | Input data type(s) | Output data type | LLM-backed? |
|------|-------------------|-----------------|-------------|
| `group_by` | `raw_data` | `entity_groups` | No |
| `label_extraction` | `entity_groups` (or `raw_data`) | `label_results` | Yes |
| `label_summary` | `label_results` | `summaries` | Yes |
| `summary` | `raw_data` | `summaries` | Yes |
| `conversation_summary` | `entity_groups` | `summaries` | Yes |
| `synthesis` | `summaries` (per-doc) | `summaries` (per-entity) | Yes |
| `classification` | `summaries` | `classifications` | Yes |
| `csv_output` | any data node | _(file on disk)_ | No |
| _(future)_ | _(declared)_ | _(declared)_ | _(declared)_ |

**Resource nodes** (shared configuration):

| Type | What it provides | Consumed by |
|------|-----------------|-------------|
| `llm_provider` | API client (base_url, model, api_key, temperature) | All LLM-backed processors |
| `taxonomy` | `context_definitions` + `label_options` + `category_merging` | Extraction, classification |
| `prompts` | Shared prompt templates (instructions + output_format) | All LLM-backed processors |
| _(future)_ | _(declared)_ | _(declared)_ |

#### On the canvas: data and processors alternate

A valid pipeline alternates between data nodes and processor nodes, with
resource nodes attached from the side:

```
[taxonomy]─────────────────────────┐
                                   │
[llm_provider]──────────────────┐  │
                                │  │
                                ▼  ▼
  ┌───────────┐   ┌──────────┐   ┌─────────────────┐   ┌──────────────┐
  │ raw_data  │──▶│ group_by │──▶│ label_extraction │──▶│ label_results│
  │  (BLUE)   │   │ (GREEN)  │   │ (GREEN)          │   │ (BLUE)       │
  └───────────┘   └──────────┘   └─────────────────┘   └──────┬───────┘
                                                               │
                                                               ▼
  ┌──────────────┐   ┌────────────────┐   ┌────────────┐   ┌──────────────┐
  │ summaries    │◀──│ label_summary  │◀──│            │   │              │
  │ (BLUE)       │   │ (GREEN)        │   └────────────┘   └──────────────┘
  └──────┬───────┘   └────────────────┘
         │
         ▼
  ┌────────────────┐   ┌──────────────────┐
  │ classification │──▶│ classifications   │──▶ [csv_output]
  │ (GREEN)        │   │ (BLUE)            │    (GREEN)
  └────────────────┘   └──────────────────┘
```

This pattern — data → processor → data → processor → data — is the same
pattern used in dataflow programming (LabVIEW, Max/MSP, Unreal Blueprints).

In the simplified view (what most users will see), data nodes are implicit
— they exist as edge labels rather than explicit boxes.  In the detailed
view, they can be expanded into full nodes for inspection and schema editing.

#### Why this separation matters

1. **Clarity about what you're editing.**  When you click a blue node, you're
   inspecting data (column schema, row counts, sample values).  When you
   click a green node, you're configuring a processor (prompts, LLM
   settings, io_schema).  Different things, different panels.

2. **Processor nodes are swappable.**  You can replace `label_summary`
   (hybrid) with a different `summary` processor without changing the
   surrounding data nodes.  The data contracts (schemas) are the stable
   part; the processors are the interchangeable part.

3. **Extensibility.**  Adding a new processor type (e.g. `translation`,
   `deduplication`, `ner_extraction`) means adding a registry entry that
   declares: what data type it consumes, what data type it produces, whether
   it's LLM-backed, and its default io_schema + default prompt.  No change
   to the canvas/edge/validation core.

#### The node type registry (extensible)

The registry is a JSON/YAML list that both the backend and frontend read.
Adding a new node type means adding an entry — no code changes to the core
app.  Every entry **must** include a `description` field — it is surfaced
in the GUI as a tooltip in the node palette and as a "What does this do?"
header in the property panel.

```yaml
node_types:
  # ── Data nodes ─────────────────────────────────────────
  - id: raw_data
    category: data
    label: "CSV Data"
    description: "Your uploaded CSV file. Map columns to roles before processing."
    default_unit: row
    config_fields:
      - name: input_csv
        type: file
        required: true
      - name: text_column
        type: column_select
        role: text
        required: true
      - name: doc_id_column
        type: column_select
        role: doc_id
        required: true
      - name: passthrough_columns
        type: column_multi_select

  - id: entity_groups
    category: data
    label: "Entity Groups"
    default_unit: entity_group
    config_fields:
      - name: entity_column
        type: column_select
        role: entity_id
        required: true
      - name: sort_column
        type: column_select
        role: sort_by
        required: true

  - id: label_results
    category: data
    label: "Label Results"
    default_unit: document_x_label

  - id: summaries
    category: data
    label: "Summaries"
    default_unit: inherit  # row or entity, depending on upstream

  - id: classifications
    category: data
    label: "Classifications"
    default_unit: inherit

  - id: metrics
    category: data
    label: "Evaluation Metrics"
    default_unit: inherit

  # ── Processor nodes ────────────────────────────────────
  - id: group_by
    category: processor
    label: "Group By"
    description: "Groups rows into entities by a column you choose (e.g. case ID). Required before any multi-document processing."
    consumes: raw_data
    produces: entity_groups
    llm_backed: false

  - id: label_extraction
    category: processor
    label: "Label Extraction"
    description: "Uses an LLM to extract relevant text spans for each taxonomy label from every document."
    consumes: [entity_groups, raw_data]  # can work with or without grouping
    produces: label_results
    llm_backed: true
    requires_resources: [llm_provider, taxonomy]
    default_io_schema:
      output:
        info_found: string
        spans:
          - span: string
        confidence_score: string
    default_prompt_ref: config/prompts.json::label_spans_extract
    config_fields:
      - name: concurrency
        type: select
        options: [async, sync]
        default: async
      - name: labels
        type: multi_select
        source: taxonomy.context_definitions
        default: all

  - id: label_summary
    category: processor
    label: "Label Summary"
    consumes: label_results
    produces: summaries
    llm_backed: true
    requires_resources: [llm_provider]
    default_io_schema:
      output:
        info_found: string
        spans_by_item:
          "{label_key}":
            - span: string
        summary: string
    default_prompt_ref: config/prompts.json::label_summary_first
    config_fields:
      - name: mode
        type: select
        options: [hybrid, full_async]
        default: hybrid
      - name: synthesize
        type: boolean
        default: true

  - id: summary
    category: processor
    label: "Summary (flat)"
    consumes: raw_data
    produces: summaries
    llm_backed: true
    requires_resources: [llm_provider]
    default_io_schema:
      output:
        info_found: string
        relevant_context: [string]
        summary: string
    default_prompt_ref: config/prompts.json::summary

  - id: classification
    category: processor
    label: "Classification"
    consumes: summaries
    produces: classifications
    llm_backed: true
    requires_resources: [llm_provider, taxonomy]
    default_io_schema:
      output:
        evidence: string
        result: string
    default_prompt_ref: config/prompts.json::classification

  # Note: there is intentionally no `evaluation` processor entry.
  # LLM-as-judge evaluation is composed in YAML by combining an
  # existing processor (typically `summary`) with a custom `io_schema`
  # and an inline `prompt`.  See config/flows/evaluation_only.yml.

  - id: csv_output
    category: processor
    label: "CSV Output"
    consumes: [summaries, classifications, metrics]
    produces: null       # terminal node
    llm_backed: false
    config_fields:
      - name: output_path
        type: string
        required: true
      - name: output_unit
        type: select
        options: [per_row, per_entity]
        default: per_row
      - name: extend
        type: boolean
        default: false

  # ── Resource nodes ─────────────────────────────────────
  - id: llm_provider
    category: resource
    label: "LLM Provider"
    description: "An LLM API connection (model, provider, API key). Processors that need an LLM must be wired to one of these."
    config_fields:
      - name: provider
        type: select
        options: [openrouter, openai, local_vllm]
        default: openrouter
      - name: model
        type: string
        required: true
      - name: api_base
        type: string
      - name: api_key_env
        type: string
      - name: temperature
        type: number
        default: 0.0
      - name: max_tokens_summary
        type: number
        default: 1024
      - name: max_tokens_classification
        type: number
        default: 256

  - id: taxonomy
    category: resource
    label: "Taxonomy"
    config_fields:
      - name: file_path
        type: file
        default: config/taxonomy.json

  - id: prompts
    category: resource
    label: "Prompt Templates"
    description: >
      A shared prompt file (e.g. config/prompts.json).  On the canvas this
      node represents the file; processors reference individual keys within
      it via their `prompts_ref` field (e.g. "config/prompts.json::label_spans_extract").
      The resource node exists for visual wiring — connecting it to a processor
      makes that processor's prompt editor pre-populate from this file.  In
      the YAML, the `prompts_ref` shorthand is sufficient; the resource node
      is inferred during graph deserialization.
    config_fields:
      - name: file_path
        type: file
        default: config/prompts.json
```

#### Adding a new processor type (example: future `translation` node)

A user or developer adds this entry to the registry:

```yaml
  - id: translation
    category: processor
    label: "Translation"
    consumes: summaries
    produces: summaries          # same data type, different content
    llm_backed: true
    requires_resources: [llm_provider]
    default_io_schema:
      output:
        translated_text: string
        source_language: string
        target_language: string
    default_prompt_ref: null     # user must provide inline
    config_fields:
      - name: target_language
        type: string
        default: "en"
```

No changes to the canvas, edge validation, or builder core.  The node
appears in the palette, can be dragged onto the canvas, and its
`consumes`/`produces` declarations let the GUI validate connections.

#### GUI: Node palette organised by category

```
┌─ Node Palette ──────────────────────────┐
│                                         │
│  DATA                                   │
│  ┌──────────┐ ┌───────────────────────┐ │
│  │ 🔵 CSV   │ │ 🔵 Entity Groups     │ │
│  │   Data   │ │                       │ │
│  └──────────┘ └───────────────────────┘ │
│  ┌──────────────┐ ┌─────────────────┐   │
│  │ 🔵 Label     │ │ 🔵 Summaries   │   │
│  │   Results    │ │                 │   │
│  └──────────────┘ └─────────────────┘   │
│                                         │
│  PROCESSORS                             │
│  ┌──────────┐ ┌───────────────────────┐ │
│  │ 🟢 Group │ │ 🟢 Label Extraction  │ │
│  │   By     │ │                       │ │
│  └──────────┘ └───────────────────────┘ │
│  ┌──────────────┐ ┌─────────────────┐   │
│  │ 🟢 Label     │ │ 🟢 Summary     │   │
│  │   Summary    │ │   (flat)        │   │
│  └──────────────┘ └─────────────────┘   │
│  ┌──────────────┐ ┌─────────────────┐   │
│  │ 🟢 Classify  │ │ 🟢 CSV Output   │   │
│  └──────────────┘ └─────────────────┘   │
│                                         │
│  RESOURCES                              │
│  ┌──────────────┐ ┌─────────────────┐   │
│  │ ⚪ LLM       │ │ ⚪ Taxonomy    │   │
│  │  Provider    │ │                 │   │
│  └──────────────┘ └─────────────────┘   │
│  ┌──────────────┐                       │
│  │ ⚪ Prompts   │                       │
│  └──────────────┘                       │
└─────────────────────────────────────────┘
```

Connection rules (enforced by the GUI):
- **Data → Processor**: valid if the processor `consumes` that data type.
- **Processor → Data**: valid if the processor `produces` that data type.
- **Resource → Processor**: valid if the processor `requires_resources`
  includes that resource type.
- **Data → Data**: invalid (need a processor in between).
- **Processor → Processor**: invalid (need a data node in between).
- **Resource → Data**: invalid.

#### Canvas display mode

For most users, explicit data nodes add visual clutter.  The MVP uses
**simplified mode only**: data nodes are implicit — they appear as edge
labels, and the canvas shows:

```
CSV Data → Group By → Label Extraction → Label Summary → Classification → CSV Output
```

with edge labels showing the data shape between each step.  Clicking an
edge label opens a read-only panel showing the full data schema at that
point (columns, unit, row count, io_fields).

The underlying model is always data→processor→data, but the simplified
view collapses adjacent data-processor pairs into processor-only display.

> **Future (post-MVP):** A "detailed mode" toggle that expands data nodes
> into full boxes on the canvas.  Deferred because the edge-click
> inspection covers the same need with less visual noise.

#### YAML is the linearized view

The YAML `steps` list contains only processors — data nodes are implicit.
The graph→YAML serializer strips data nodes and writes processors in
topological order.  The YAML→graph deserializer infers data nodes by
reading each processor's `produces` declaration from the registry and
inserting the corresponding data node between steps.  This keeps the
YAML concise while the canvas remains fully typed.

### 1.8 Node I/O Schemas and Prompts

> **Status: implemented.**
>
> - `io_schema` on `StepConfig` (`src/flow_loader.py`) is an optional
>   `IOSchema` (from `src/io_schema.py`) defined as a YAML `input` /
>   `output` `key: type` dict.  `to_response_format()` converts the
>   `output` dict into the OpenAI `response_format` JSON schema, and
>   `to_prompt_output_format_text()` renders the same dict into the
>   human-readable block that used to live in `prompts.json`'s
>   `output_format`.  Inline doctests in `src/io_schema.py` assert the
>   converter reproduces each of the six previously-hardcoded
>   `response_format` dicts byte-for-byte.
> - `prompts_ref`, inline `prompt` (`PromptInline`), and
>   `prompt_overrides` (`PromptOverride` with nested
>   `InstructionOverride` for `prepend` / `append` / `replace`) are
>   declared on `StepConfig`.  `StepConfig.validate_prompt_sources`
>   enforces the mutual-exclusion rule: at most one of
>   (`prompt`, `prompts_ref`, `prompt_overrides`) may be set, and
>   `prompt_overrides` implicitly requires `prompts_ref`.
> - Resolution is performed by `src.prompt_resolver.resolve_step_prompt`
>   in the precedence order documented below (inline
>   `prompt` > `prompts_ref` + `prompt_overrides` > bare `prompts_ref`
>   > processor-type default > legacy `prompts.json` fallback).
> - `FlowRunner._resolve_processor_config_for_step`
>   (`src/flow_builder.py`) layers the resolved `io_schema` and
>   `ResolvedPrompt` onto the resource-level base config as
>   `io_schema_resolved` and `prompt_resolved` before handing the
>   config to the processor.  Each `_get_*_args` method in
>   `src/processors.py` consumes those two keys when present and falls
>   back to the pre-existing `prompts.json` + hardcoded schema behaviour
>   otherwise.  `_get_synthesis_args` intentionally ignores step-level
>   overrides because it runs as an internal reconciliation call whose
>   I/O shape must remain the `label_synthesis` shape even when the
>   surrounding `label_summary` step defines its own schema.

#### The two kinds of "schema" per node

Each processing node deals with two distinct schemas:

1. **Pipeline data schema** — what columnar data flows between nodes in the
   graph (e.g. the `text` column, the `summary_all_context` column, the
   `desenlace_classification` column).  This is what edges carry.
2. **LLM I/O schema** — the JSON structure sent to and received from the LLM
   for a single call.  This is what the `response_format` enforces on the
   model output, and what the prompt's `output_format` shows as an example.

Both should be user-definable as `key: value` dicts.

#### Current state in the code

Every processor currently has these two schemas, but they live in different
places and are defined differently:

| Processor | Prompt key in `prompts.json` | `output_format` (shown to LLM) | `response_format` (enforced JSON schema) |
|-----------|------------------------------|-------------------------------|------------------------------------------|
| Summary | `summary` | `{info_found: str, relevant_context: [str], summary: str}` | Hard-coded in `_get_summary_args()` at line 307 |
| Conversation summary | `summary_first` / `summary_update` | `{info_found: str, relevant_context: [str], summary_by_item: {label: [{span: str}]}, summary: str}` | Hard-coded in `_get_conversation_summary_args()` at line 430 |
| Classification | `classification` | _(none, instructions only)_ | Hard-coded at line 525: `{evidence: str, result: str}` |
| Label extraction | `label_spans_extract` | `{info_found: str, spans: [{span: str}], confidence_score: str}` | Hard-coded at line 1438 |
| Label summary | `label_summary_first` / `label_summary_update` | `{info_found: str, spans_by_item: {...}, summary: str}` | Hard-coded at line 1828 |
| Synthesis | `label_synthesis` | `{info_found: str, summary: str}` | Hard-coded at line 1918 |

The problem: the `output_format` in `prompts.json` and the `response_format`
in Python are **duplicated definitions of the same structure**.  They can
drift out of sync, and neither is user-editable without touching code.

#### Design: each node carries its own `io_schema`

Each processing node in the YAML defines an `io_schema` as a `key: type`
dict.  This single definition is used for **three purposes**:

1. **`response_format`** for the OpenAI API call (auto-generated from the dict).
2. **`output_format`** shown in the prompt to the LLM (auto-generated).
3. **Edge schema** — tells downstream nodes what fields are available.

```yaml
steps:
  - type: label_extraction
    unit: document
    concurrency: async
    io_schema:
      input:
        text: string              # the raw document text (from column_roles.text)
        label_key: string         # which label is being extracted
        label_definition: string  # definition from taxonomy
      output:
        info_found: string        # "TRUE" or "FALSE"
        spans:                    # list of extracted spans
          - span: string
        confidence_score: string  # "0.0" to "1.0"

  - type: label_summary
    unit: entity
    mode: hybrid
    synthesize: true
    io_schema:
      input:
        text: string
        spans_by_item:            # per-label spans from extraction
          "{label_key}":
            - span: string
        previous_summary: string
      output:
        info_found: string
        spans_by_item:
          "{label_key}":
            - span: string
        summary: string

  - type: classification
    unit: entity
    io_schema:
      input:
        summary: string           # the entity-level summary
        question: string          # "What is the {label}?"
        possible_values: string   # from taxonomy.label_options
      output:
        evidence: string
        result: string
```

#### How `io_schema` generates `response_format`

The builder converts the `output` dict into a JSON Schema automatically:

```python
# io_schema.output from YAML:
#   info_found: string
#   spans:
#     - span: string
#   confidence_score: string

# Auto-generated response_format:
{
  "type": "json_schema",
  "json_schema": {
    "name": "label_extract",
    "schema": {
      "type": "object",
      "properties": {
        "info_found": {"type": "string"},
        "spans": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {"span": {"type": "string"}},
            "required": ["span"]
          }
        },
        "confidence_score": {"type": "string"}
      },
      "required": ["info_found", "spans", "confidence_score"]
    }
  }
}
```

Type mapping:

| YAML shorthand | JSON Schema type |
|----------------|-----------------|
| `string` | `{"type": "string"}` |
| `number` | `{"type": "number"}` |
| `boolean` | `{"type": "boolean"}` |
| `- field: type` (list) | `{"type": "array", "items": {"type": "object", "properties": ...}}` |
| nested dict | `{"type": "object", "properties": ...}` |

This eliminates the duplication: the YAML `io_schema.output` is the single
source of truth for both `response_format` and the prompt `output_format`.

#### Where do prompts live?

**Answer: on the node.**

Each processing node owns its prompts.  Currently `prompts.json` stores
all prompts in one flat file, keyed by task type.  In the new design, each
node in the YAML can either:

1. **Reference a shared prompt file** (like today):

   ```yaml
   steps:
     - type: label_extraction
       prompts_ref: config/prompts.json::label_spans_extract
   ```

2. **Inline the prompt directly on the node** (for customisation):

   ```yaml
   steps:
     - type: label_extraction
       prompt:
         instructions:
           - "Extract spans from {input_text_label} relevant to label={label}."
           - "Each span must be a full original sentence."
           - "NO APOLOGIES, NO FILLER TEXT."
   ```

3. **Reference + override** (inherit defaults, tweak specific fields):

   ```yaml
   steps:
     - type: label_extraction
       prompts_ref: config/prompts.json::label_spans_extract
       prompt_overrides:
         instructions:
           - append: "Always include the date if mentioned in the span."
   ```

The resolution order is: inline `prompt` > `prompt_overrides` on top of
`prompts_ref` > `prompts_ref` alone > built-in defaults.

This means a user can use the existing `prompts.json` unchanged, or
customise per-node without touching the shared file.

#### Prompt structure per node type

Each prompt has exactly two parts (matching `prompts.json` today):

| Part | Purpose | Editable by user? |
|------|---------|-------------------|
| `instructions` | List of instruction strings with `{placeholder}` template vars | Yes — this is the main thing users customise |
| `io_schema.output` | The k:v dict defining what the LLM must return | Yes — changing this changes the enforced schema |

The `io_schema.input` is not sent to the LLM directly — it documents what
the node receives from the pipeline.  The prompt's `{placeholders}` are
resolved from the input fields.  For example, `{input_text_label}` in the
instructions resolves to the actual column name the user mapped to `text`.

#### GUI: Prompt editor on the node property panel

In Phase 2, when the user clicks a processing node, its property panel has
three tabs:

```
┌──────────────────────────────────────────────────────────┐
│  ⚙️  Label Extraction — Properties                       │
│                                                          │
│  [Config]  [I/O Schema]  [Prompt]                        │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  ┌─ Config ────────────────────────────────────────────┐ │
│  │  Concurrency  [ async ▾ ]                           │ │
│  │  Labels       [☑ desenlace] [☑ vic_grupo_social]    │ │
│  │               [☑ captura_tipo]                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ I/O Schema ────────────────────────────────────────┐ │
│  │                                                     │ │
│  │  Input (read-only, from upstream edge):             │ │
│  │  ┌─────────────────┬──────────┐                     │ │
│  │  │ text            │ string   │                     │ │
│  │  │ label_key       │ string   │                     │ │
│  │  │ label_definition│ string   │                     │ │
│  │  └─────────────────┴──────────┘                     │ │
│  │                                                     │ │
│  │  Output (editable):                 [+ Add field]   │ │
│  │  ┌─────────────────┬──────────┬───┐                 │ │
│  │  │ info_found      │ string   │ ✕ │                 │ │
│  │  │ spans           │ [{span}] │ ✕ │                 │ │
│  │  │ confidence_score│ string   │ ✕ │                 │ │
│  │  └─────────────────┴──────────┴───┘                 │ │
│  │                                                     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Prompt ────────────────────────────────────────────┐ │
│  │  Source: [ config/prompts.json ▾ ]                  │ │
│  │  Key:    label_spans_extract                        │ │
│  │                                                     │ │
│  │  Instructions:                                      │ │
│  │  ┌─────────────────────────────────────────────┐    │ │
│  │  │ 1. Extract spans from {input_text_label}    │    │ │
│  │  │    relevant to label={label}, given the     │    │ │
│  │  │    definition: {label_definition}.           │    │ │
│  │  │ 2. Each span must be a full original        │    │ │
│  │  │    sentence ending in punctuation.           │    │ │
│  │  │ 3. Set confidence_score to [0,1].            │    │ │
│  │  │ 4. NO APOLOGIES, NO FILLER TEXT.             │    │ │
│  │  └─────────────────────────────────────────────┘    │ │
│  │  Available placeholders:                            │ │
│  │  {input_text_label}  {label}  {label_definition}   │ │
│  │  {previous_spans}  {info_found_label}               │ │
│  │                                                     │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

The output schema table is directly editable: the user can add/remove
fields and change types.  When they change the output schema, the
`response_format` sent to the LLM updates automatically, and the edge
leaving this node updates its schema badge to reflect the new fields.

#### How output schema flows to the next node's input

When the user connects Label Extraction → Label Summary:

1. Label Extraction's `io_schema.output` is
   `{info_found, spans: [{span}], confidence_score}`.
2. The edge carries this schema.
3. Label Summary's `io_schema.input` is populated using the registry's
   `input_transform` rule for this step pair.

**Important distinction: pass-through vs. structural transforms.**

For most connections, the upstream output schema flows directly into the
downstream input ("pass-through").  However, some step transitions require
a non-trivial structural transformation — for example, Label Extraction
produces per-document, per-label results, but Label Summary expects a
`spans_by_item: {label_key: [{span}]}` dict that groups results across
documents.  These transformations are **not** auto-inferred; they are
declared explicitly in the registry as an `input_transform` rule:

```yaml
  - id: label_summary
    category: processor
    consumes: label_results
    input_transform:
      type: group_by_label_key
      source_field: spans
      target_field: spans_by_item
```

For step pairs without an `input_transform`, the upstream output schema
is forwarded as-is.  The GUI shows the resolved input as read-only so the
user can see exactly what each node receives.

This makes the pipeline self-documenting: you can look at any edge and see
exactly what k:v fields flow through it.

#### Defaults

Users don't have to define `io_schema` from scratch.  Each node type has a
built-in default that matches the current hard-coded schemas:

| Node type | Default output schema |
|-----------|----------------------|
| Label Extraction | `{info_found: string, spans: [{span: string}], confidence_score: string}` |
| Label Summary | `{info_found: string, spans_by_item: {label: [{span: string}]}, summary: string}` |
| Summary (flat) | `{info_found: string, relevant_context: [string], summary: string}` |
| Conversation Summary | `{info_found: string, relevant_context: [string], summary_by_item: {label: [{span: string}]}, summary: string}` |
| Classification | `{evidence: string, result: string}` |
| Synthesis | `{info_found: string, summary: string}` |

These defaults are loaded when the user first drags a node onto the canvas.
The user can then customise the output fields (add a `sentiment: string`
field, remove `confidence_score`, etc.) and the whole pipeline adjusts.

#### Full YAML example with explicit io_schema

```yaml
flow:
  schema_version: 1
  name: custom_pipeline
  description: "User-customised extraction with extra sentiment field"

  resources:
    - id: default
      type: llm_provider
      provider: openrouter
      model: meta-llama/llama-3.1-70b-instruct
      api_base: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
      temperature: 0.0
      max_tokens_summary: 1024
      max_tokens_classification: 256

  data:
    input_csv: my_data.csv
    column_roles:
      text:      article_body
      entity_id: case_number
      doc_id:    report_id
      sort_by:   pub_date

  taxonomy: config/taxonomy.json

  steps:
    - type: label_extraction
      unit: document
      concurrency: async
      prompts_ref: config/prompts.json::label_spans_extract
      io_schema:
        output:
          info_found: string
          spans:
            - span: string
          confidence_score: string
          sentiment: string          # ← user-added custom field

    - type: label_summary
      unit: entity
      mode: hybrid
      synthesize: true
      prompts_ref: config/prompts.json::label_summary_first
      prompt_overrides:
        instructions:
          - append: "Also note the overall sentiment for each label."
      io_schema:
        output:
          info_found: string
          spans_by_item:
            "{label_key}":
              - span: string
          summary: string
          overall_sentiment: string   # ← user-added, consuming upstream sentiment

    - type: classification
      unit: entity
      prompts_ref: config/prompts.json::classification
      io_schema:
        output:
          evidence: string
          result: string

  async:
    enabled: true
    max_concurrent_rows: 15
    max_concurrent_llm_calls: 50
    max_retries: 5

  output:
    summary_csv: results/summary.csv
    extend: false

  logging:
    file: processing.log
    log_progress: true
```

### 1.9 LLM Configuration, Per-Processor Model Selection, and Free Tier

> **Status: partially implemented.** Named LLM resources, per-step `llm`
> selection, model listing, and `processing_limit` are live, but secure
> BYOK storage, free-tier enforcement, and cost-estimate UX from this
> section are not fully implemented.

#### Per-processor model selection

The current plan has one global `llm_provider` resource node.  But in
practice you might want a cheap/fast model for extraction (Llama 8B) and
a better model for synthesis (Llama 70B or GPT-4o).  The design already
supports this: the user can place **multiple `llm_provider` nodes** on the
canvas and wire each processor to a different one.

```
[LLM: Llama 8B]───────────┐
                           ▼
  raw_data → group_by → label_extraction → label_results
                                                │
[LLM: Llama 70B]──────────┐                    │
                           ▼                    ▼
              summaries ← label_summary ← label_results

[LLM: GPT-4o]─────────────┐
                           ▼
   classifications ← classification ← summaries
```

Each `llm_provider` resource node is independent — different model,
different provider, different API key.  A processor node's
`requires_resources: [llm_provider]` means it needs exactly one LLM
connection, but the user picks which one by drawing the edge.

In the YAML this becomes:

```yaml
resources:
  - id: llm_fast
    type: llm_provider
    provider: openrouter
    model: meta-llama/llama-3.1-8b-instruct
    api_key_source: user       # use the user's stored key
    temperature: 0.0

  - id: llm_strong
    type: llm_provider
    provider: openrouter
    model: meta-llama/llama-3.1-70b-instruct
    api_key_source: user
    temperature: 0.0

  - id: llm_openai
    type: llm_provider
    provider: openai
    model: gpt-4o
    api_key_source: user
    temperature: 0.0

steps:
  - type: label_extraction
    llm: llm_fast              # uses the cheap model
    ...

  - type: label_summary
    llm: llm_strong            # uses the bigger model
    ...

  - type: classification
    llm: llm_openai            # uses OpenAI
    ...
```

#### User brings their own API key

Users should never paste API keys into the YAML or into a text field that
gets saved to the database.  Keys are stored separately, per-user, in a
secure credential store.

**How it works:**

1. The GUI has a **Settings > API Keys** page (accessible from the top nav
   or from any LLM Provider node):

   ```
   ┌─────────────────────────────────────────────────────────┐
   │  ⚙️  API Keys                                           │
   │                                                         │
   │  OpenRouter    [sk-or-v1-••••••••••••3f2a]  [✓ Valid]   │
   │                [ Paste new key ]  [ Test ]  [ Remove ]  │
   │                                                         │
   │  OpenAI        [ Not configured ]                       │
   │                [ Paste new key ]  [ Test ]              │
   │                                                         │
   │  Local vLLM    [ http://localhost:8000/v1 ]             │
   │                (no key needed)                           │
   │                                                         │
   │  Keys are stored encrypted on the server and never      │
   │  appear in exported YAML files.                         │
   └─────────────────────────────────────────────────────────┘
   ```

2. **Storage**: keys are stored server-side, encrypted at rest, associated
   with the user's session (or account, if multi-user).  They are never
   written to YAML, flow configs, or logs.

3. **In the YAML**, the `llm_provider` uses `api_key_source: user` to
   indicate "use whatever key this user has stored for this provider."
   When running from CLI (`run_custom_flow.py`), it falls back to
   `api_key_env: OPENROUTER_API_KEY` (env var).

4. **Validation**: the "Test" button on the settings page makes a
   lightweight API call (e.g. list models) to verify the key works before
   the user starts a run.

#### LLM Provider node: model picker

When the user clicks an LLM Provider resource node on the canvas, its
property panel shows a model picker — not a free-text field:

```
┌─────────────────────────────────────────────────────────┐
│  ⚪ LLM Provider — Properties                           │
│                                                         │
│  Name        [ llm_fast                ]                │
│                                                         │
│  Provider    [ OpenRouter ▾ ]                           │
│              Key status: ✓ configured                   │
│                                                         │
│  Model       [ 🔍 Search models...              ]      │
│              ┌──────────────────────────────────┐       │
│              │ meta-llama/llama-3.1-8b     $0.06│       │
│              │ meta-llama/llama-3.1-70b    $0.40│       │
│              │ meta-llama/llama-3.1-405b   $2.00│       │
│              │ mistralai/mistral-large     $2.00│       │
│              │ openai/gpt-4o              $2.50│       │
│              │ anthropic/claude-3.5-sonnet $3.00│       │
│              └──────────────────────────────────┘       │
│                                                         │
│  Temperature [ 0.0          ]                           │
│  Max tokens  [ 1024         ]  (summary)                │
│              [ 256          ]  (classification)          │
│                                                         │
│  Cost estimate for this flow:                           │
│  ~1,247 docs × avg 500 tokens = ~624K tokens            │
│  ≈ $0.04 input + $0.04 output = $0.08 total             │
└─────────────────────────────────────────────────────────┘
```

The model list is fetched live from the provider's API:
- OpenRouter: `GET https://openrouter.ai/api/v1/models`
- OpenAI: `GET https://api.openai.com/v1/models`
- Local vLLM: `GET http://localhost:8000/v1/models`

The list shows model name + price per million tokens, so the user can make
an informed choice.

#### Free trial tier

Users who don't bring their own API key can still try the app.  The
backend has a house OpenRouter key (budget-capped) that provides limited
free processing.

**Rules:**

| | Free tier (no key) | BYOK (user's key) |
|---|---|---|
| Processing limit | **5 entities** (grouped pipeline) / **5 rows** (flat pipeline) | Unlimited (user pays) |
| Model | Fixed: `meta-llama/llama-3.1-8b-instruct` | Any model from their provider |
| Provider | OpenRouter (house key) | User's choice |
| Multiple LLM nodes | No (one fixed LLM) | Yes |
| Runs per day | 3 | Unlimited |
| Export YAML | Yes | Yes |

**GUI: Processing limit selector**

The processing limit is a top-level setting on the toolbar, not buried in
config.  The label changes dynamically based on whether the pipeline is
grouped ("Entities") or flat ("Rows"):

```
┌─ Toolbar ──────────────────────────────────────────────────────────────┐
│  [Save] [Load] [Export YAML]  │  Entities: [ 5 ▾ ]  │  [▶ Run Flow]  │
│                               │  ┌──────────────┐   │                 │
│                               │  │ 5  (free)    │   │                 │
│                               │  │ 50           │   │                 │
│                               │  │ 100          │   │                 │
│                               │  │ 500          │   │                 │
│                               │  │ All (1,247)  │   │                 │
│                               │  └──────────────┘   │                 │
└────────────────────────────────────────────────────────────────────────┘
```

(For flat pipelines without a Group By node, the label reads "Rows" instead
of "Entities".)

When no API key is configured:
- The dropdown shows only "5 (free)" and the other options are grayed out
  with a tooltip: "Add your API key in Settings to process more rows."
- The LLM Provider node on the canvas is auto-populated with the house
  model and locked (read-only, greyed-out fields).
- A banner at the top says: "Free trial: 5 rows with Llama 8B.
  [Add API key] to unlock all models and row limits."

When an API key is configured:
- All options in the dropdown are available.
- The LLM Provider node is fully editable.
- The cost estimate updates as the user changes the row limit.

**In the YAML:**

```yaml
flow:
  processing_limit: 5        # null = process all; unit depends on pipeline type
  ...
```

The `flow_builder` respects this.  For grouped pipelines it limits the
number of entity groups (consistent with the existing `summary_row_limit`
in `settings.yaml`).  For flat pipelines it limits rows:

```python
if schema.flow.processing_limit is not None:
    if is_grouped:
        entity_ids = df[entity_col].unique()[:schema.flow.processing_limit]
        df = df[df[entity_col].isin(entity_ids)]
    else:
        df = df.head(schema.flow.processing_limit)
```

This ensures that in grouped pipelines, every selected entity is processed
completely (all its documents), rather than slicing arbitrary rows that
might leave entities half-processed.

**Backend enforcement:**

The free tier is enforced server-side, not just in the GUI:

```python
@app.post("/api/flow/run")
async def run_flow(flow_config: FlowConfig, user: User):
    has_own_key = user.has_api_key(flow_config.llm_provider)

    if not has_own_key:
        if flow_config.processing_limit is None or flow_config.processing_limit > 5:
            flow_config.processing_limit = 5
        flow_config.llm_provider = HOUSE_LLM_CONFIG
        if user.runs_today >= 3:
            raise HTTPException(429, "Free tier: 3 runs per day. Add your API key for unlimited runs.")
```

**Cost protection even for BYOK users:**

The GUI shows a cost estimate before the user hits "Run":

```
┌─────────────────────────────────────────────────────┐
│  Ready to run: label_conversation_70b               │
│                                                     │
│  Rows to process:  500 of 1,247                     │
│  Steps:            3 (extract → summarize → classify)│
│  LLM calls:        ~500 × 3 labels + 500 + 500     │
│                    = ~2,500 calls                    │
│  Estimated tokens:  ~1.2M input, ~300K output       │
│  Estimated cost:    ~$0.60 (Llama 70B on OpenRouter) │
│                                                     │
│  [ Cancel ]                        [ ▶ Run Flow ]   │
└─────────────────────────────────────────────────────┘
```

#### How per-processor model selection maps to the flow YAML

When each processor uses a different model, the YAML uses named resources:

```yaml
flow:
  name: multi_model_pipeline
  row_limit: null

  resources:
    - id: llm_extract
      type: llm_provider
      provider: openrouter
      model: meta-llama/llama-3.1-8b-instruct
      api_key_source: user
      temperature: 0.0
      max_tokens_summary: 1024

    - id: llm_summarize
      type: llm_provider
      provider: openrouter
      model: meta-llama/llama-3.1-70b-instruct
      api_key_source: user
      temperature: 0.0
      max_tokens_summary: 1024

  data:
    input_csv: my_data.csv
    column_roles:
      text:      article_body
      entity_id: case_number
      doc_id:    report_id
      sort_by:   pub_date

  taxonomy: config/taxonomy.json

  steps:
    - type: label_extraction
      unit: document
      llm: llm_extract               # ← cheap model for extraction
      concurrency: async
      ...

    - type: label_summary
      unit: entity
      llm: llm_summarize             # ← strong model for synthesis
      mode: hybrid
      synthesize: true
      ...

    - type: classification
      unit: entity
      llm: llm_summarize             # ← reuse same strong model
      ...
```

If `llm` is omitted from a step, it uses the first (or only) `llm_provider`
resource as the default.

### 1.10 Error Handling, Checkpointing, and Resume

> **Status: partially implemented.** Entity-level resume exists in
> `src/flow_builder.py` and `scripts/run_custom_flow.py`, and the server
> can re-dispatch runs, but the fuller retry/checkpoint/progress UX
> described below is only partly implemented.

Long-running pipelines (hundreds of entities, thousands of LLM calls) will
inevitably encounter failures: rate limits, network timeouts, transient API
errors, or budget exhaustion.  The flow runner must handle these gracefully.

#### Per-call retry

Every LLM call uses exponential backoff with jitter:

```python
for attempt in range(max_retries):
    try:
        result = await client.chat.completions.create(...)
        break
    except (RateLimitError, APITimeoutError, APIConnectionError) as e:
        if attempt == max_retries - 1:
            raise
        wait = min(2 ** attempt + random.uniform(0, 1), 60)
        await asyncio.sleep(wait)
```

`max_retries` is configurable in the YAML `async` block (default: 5).

#### Entity-level checkpointing

After each entity completes all its pipeline steps, the runner writes its
results to a checkpoint file:

```
results_down_sized/70b/.checkpoint/
├── completed_entities.json    # list of entity_ids successfully processed
├── partial_results.csv        # accumulated output rows
└── run_meta.json              # flow hash, timestamp, last entity processed
```

If a run is interrupted (crash, timeout, user cancel), the checkpoint
records which entities succeeded.

#### Resume

A "Resume" button in the GUI (or `--resume` flag in CLI) re-runs only
incomplete entities:

```python
# CLI — edit the module-level `flow_config` in run_custom_flow.py
# to point at the YAML, then:
python scripts/run_custom_flow.py --resume

# Under the hood, main() calls:
#   args = parse_cli_args()
#   build_flow(Path(flow_config), resume=args.resume).run()

# Backend (Phase 2)
@app.post("/api/flow/resume/{run_id}")
async def resume_flow(run_id: str, user: User):
    checkpoint = load_checkpoint(run_id)
    flow = build_flow(checkpoint.flow_config, resume=True)
    flow.run(df)
```

The GUI shows the run status with a progress bar that accounts for already-
completed entities.  When a run finishes with partial failures, the status
page shows:

```
✓ 78 / 83 entities completed
✗ 5 entities failed (rate limit after retry exhaustion)
  [▶ Resume]  [↓ Download partial results]
```

#### Failure modes

| Failure | Behaviour |
|---------|-----------|
| Single LLM call fails after retries | Entity marked as failed; other entities continue |
| API key invalid / revoked | Run stops immediately; no retry (user must fix key) |
| Budget exceeded (OpenRouter) | Run stops; partial results saved; user notified |
| Server killed (Render sleep / OOM) | Checkpoint on disk; user can resume |

### 1.11 Effort & Risk

| Item | Effort | Risk |
|------|--------|------|
| Pydantic schema models (column_roles + unit + io_schema + prompt resolution + named resources) | 2 days | Low |
| `flow_builder.py` (parser + wiring + column mapping + io_schema→response_format + per-step LLM resolution) | 3–4 days | Medium — io_schema→JSON Schema conversion needs careful testing |
| Checkpointing + resume logic | 2 days | Medium — edge cases around partial entity completion |
| `run_custom_flow.py` entry point | 0.5 day | Low |
| Migration of existing settings to flow YAMLs | 0.5 day | Low |
| **Total** | **~8 days** | |

---

## Phase 2: GUI Schema Creator

### 2.1 Architecture

> **Status: implemented.** The React Flow + FastAPI architecture described
> here exists in `gui/src/flow_editor/*` and `server/app.py`.

```
┌──────────────────────────────────────────────────────────────┐
│                     Browser (React)                          │
│                                                              │
│  ┌────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ Node       │  │ Canvas           │  │ Property Panel  │  │
│  │ Palette    │  │ (React Flow)     │  │ (forms per      │  │
│  │            │  │ drag-drop nodes  │  │  node type)     │  │
│  │ - Extract  │  │ connect edges    │  │                 │  │
│  │ - Summary  │  │                  │  │ model, temp,    │  │
│  │ - Classify │  │                  │  │ prompts, paths  │  │
│  │ - Evaluate │  │                  │  │                 │  │
│  └────────────┘  └──────────────────┘  └─────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ Toolbar: [Save YAML] [Load YAML] [Run Flow] [View Logs] ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────┬───────────────────────────────────┘
                           │  REST API (HTTPS)
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              Backend (FastAPI on Render)                      │
│                                                              │
│  /api/schema/node-types    → returns available node types    │
│  /api/schema/validate      → validates a flow YAML           │
│  /api/flow/run             → executes a validated flow       │
│  /api/flow/status/:id      → poll job status / stream logs   │
│  /api/flow/results/:id     → first 20 rows of output (preview)│
│  /api/flow/list            → list saved flow configs         │
│  POST /api/flow/save       → save a new flow config          │
│  PUT  /api/flow/:id        → update an existing flow         │
│  DELETE /api/flow/:id      → delete a flow                   │
│  POST /api/flow/:id/dup    → duplicate a flow                │
│  /api/taxonomy             → returns taxonomy.json           │
│  POST /api/taxonomy        → create a new taxonomy           │
│  PUT  /api/taxonomy/:id    → update a taxonomy               │
│  /api/prompts              → returns prompts.json            │
│                                                              │
│  Uses: src/flow_builder.py (Phase 1)                         │
│        src/processors.py                                     │
│        OpenRouter API for LLM calls                          │
└──────────────────────────────────────────────────────────────┘
                           │
                           │  HTTPS (OpenAI-compatible)
                           ▼
                 ┌─────────────────────┐
                 │   OpenRouter.ai     │
                 │                     │
                 │ Llama 3.1 70B       │
                 │ Qwen, Mistral, etc. │
                 │ GPT-4o, Claude      │
                 └─────────────────────┘
```

### 2.2 Why OpenRouter (not local vLLM)

> **Status: implemented.** OpenRouter support is live through
> `src/flow_loader.py`, `server/services/model_list_proxy.py`, and
> `server/routes/settings.py`.

The current codebase uses a local vLLM server (`http://localhost:8000/v1`),
which works for batch runs on your own GPU machine. Once the app is hosted on
Render (or any cloud PaaS), there is no local GPU. You need a remote LLM API.

| Option | Pros | Cons |
|--------|------|------|
| **OpenRouter** | Single API key for 100+ models (Llama, Mistral, Qwen, GPT-4o, Claude). OpenAI-compatible endpoint — zero code changes to `processors.py`. Pay-per-token, no idle cost. | Adds per-token cost. Latency higher than local vLLM. |
| OpenAI directly | Most reliable. | Only OpenAI models. More expensive per token than open models on OpenRouter. |
| Together.ai / Fireworks.ai | Good open-model hosting. | Smaller model selection than OpenRouter. |
| Self-hosted GPU (RunPod, Lambda) | Full control, can run vLLM. | You're back to managing infrastructure. Idle cost. |

**Recommendation: OpenRouter** as the default provider for the hosted app. The
`llm.provider` field in the flow schema means the same `processors.py` code
works with any backend — just swap `base_url`.

The only code change needed in `src/processors.py`: none. The `OpenAI` /
`AsyncOpenAI` client already accepts arbitrary `base_url`. OpenRouter's
endpoint is `https://openrouter.ai/api/v1` and the API key goes in the
`Authorization` header, same as OpenAI.

### 2.3 Platform & Tooling Choices

> **Status: implemented.** The chosen stack is present: React/Vite/React
> Flow in `gui/package.json`, FastAPI/CORS in `server/app.py`, and
> Celery/Redis in `server/celery_app.py`.

#### Frontend

| Component | Tool | Why |
|-----------|------|-----|
| Framework | **React 18** (TypeScript) | Dominant ecosystem for node editors. React Flow requires React. |
| Node editor | **React Flow** (reactflow.dev) | MIT-licensed, well-maintained, built for exactly this use case. Handles drag-drop, edge connections, zoom/pan, minimap. |
| UI components | **shadcn/ui** | Copy-paste Tailwind components. No runtime dependency. Clean look. |
| Form generation | **React Hook Form + Zod** | Pydantic schema → JSON Schema → Zod schema → auto-generated forms. Type-safe validation on the client side. |
| State management | **Zustand** | Lightweight, no boilerplate. React Flow's official examples use it. |
| Build tool | **Vite** | Fast dev server, ESM-native, standard for new React projects. |
| YAML serialisation | **js-yaml** | Read/write YAML in the browser for import/export. |

#### Backend

| Component | Tool | Why |
|-----------|------|-----|
| Framework | **FastAPI** | Already Python. Async-native. Auto-generates OpenAPI docs. Your existing code is async. |
| Task queue | **Celery + Redis** (or **FastAPI BackgroundTasks** for MVP) | Flow execution can take minutes. Must not block the HTTP request. Celery gives retry, monitoring, result backend. For MVP, FastAPI's background tasks + polling endpoint is sufficient. |
| Schema validation | **Pydantic v2** (already in requirements.txt) | Same models used by `flow_builder.py`. Backend validates before execution. |
| WebSocket (optional) | **FastAPI WebSocket** | Stream execution logs to the browser in real-time instead of polling. Nice-to-have. |
| CORS | **FastAPI CORSMiddleware** | Required because the React static site and the FastAPI web service run on different origins. Without this, every browser API call is blocked. |

#### Hosting

| Component | Platform | Why | Cost |
|-----------|----------|-----|------|
| Backend (FastAPI) | **Render — Web Service** | Free tier available. Auto-deploy from GitHub. Supports Python. No Docker required (but Dockerfile supported). | Free tier: 750 hrs/mo. Starter: $7/mo. |
| | | **Warning:** free tier services sleep after 15 min of inactivity; cold-start takes ~30 s. Long-running flows may be killed mid-execution. Use the Starter plan ($7/mo) for production workloads. | |
| Frontend (React) | **Render — Static Site** | Same platform. Free tier. Automatic builds from `gui/` subfolder. | Free. |
| Redis (if using Celery) | **Render — Redis** | Managed Redis on the same platform. | Free tier: 25MB. $10/mo for 100MB. |
| File storage (CSVs) | **Render Disk** or **S3-compatible (Cloudflare R2)** | User-uploaded CSVs and result CSVs need persistent storage. Render Disk is simplest. R2 is cheaper for larger volumes. | Render Disk: $0.25/GB/mo. R2: free egress, $0.015/GB/mo storage. |
| Database (flow configs) | **SQLite on Render Disk** (MVP) or **Render PostgreSQL** | Store saved flow schemas, run history, user sessions. SQLite is fine for single-instance MVP. | SQLite: free. Postgres: $7/mo. |
| LLM API | **OpenRouter** | See 2.2 above. | Pay-per-token. Llama 70B: ~$0.40/M input, $0.40/M output. |

#### Alternative: Vercel (frontend) + Railway (backend)

If Render's free tier limits are too tight:

| Component | Platform | Cost |
|-----------|----------|------|
| Frontend | Vercel (free tier) | Free |
| Backend | Railway ($5/mo) | $5/mo + usage |
| Redis | Railway (addon) | Included |

Either stack works. Render is simpler (one platform for everything).

### 2.4 Data Flow: From Drag-Drop to Execution

> **Status: implemented.** The graph-to-YAML-to-runner pipeline is live via
> `gui/src/serialisation/*`, `server/workers/flow_task.py`, and the run
> pages in `gui/src/pages/`.

```
User drags nodes → React Flow graph state (Zustand)
                          │
                          ▼
        serialiseGraphToYAML(nodes, edges)
                          │
                          ▼
           Flow YAML (same format as Phase 1)
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     Download as .yml          POST /api/flow/run
     (offline use)                    │
                                      ▼
                           flow_builder.build_flow(yaml)
                                      │
                                      ▼
                             FlowRunner.run(df)
                                      │
                                      ▼
                           processors.py classes
                                      │
                                      ▼
                             OpenRouter API
                                      │
                                      ▼
                             Results CSV → /api/flow/status/:id
                                      │
                                      ▼
                             /api/flow/results/:id
                             (first 20 rows as JSON for in-app preview)
                                      │
                                      ▼
                             User previews results in GUI
                             → [Download full CSV]
```

### 2.5 Node Type Registry & Edge Schema

> **Status: partially implemented.** The registry endpoint and unit-aware
> edge rendering exist, but the full `EdgeSchema` /
> `consumes`-driven validation described below is only partly implemented.

The backend exposes a `GET /api/schema/node-types` endpoint that returns the
full registry from section 1.7 as JSON.  The frontend reads this at startup
to populate the node palette, validate connections, and render property
panels.  Because the registry is data (not code), adding a new node type
on the backend immediately makes it available in the GUI — no frontend
deployment needed.

#### Edge schema propagation

Each edge carries a **data schema** that updates as the user connects nodes.
Since the graph alternates data → processor → data, every edge represents
a data state:

```typescript
interface EdgeSchema {
  data_type: string;         // registry data node id: "raw_data", "entity_groups", "label_results", etc.
  unit: "row" | "entity_group" | "document" | "document_x_label" | "entity";
  row_count: number;         // from actual uploaded data
  entity_count?: number;     // after Group By
  label_count?: number;      // after Label Extraction
  columns: {
    [role: string]: {        // "text", "entity_id", "doc_id", "sort_by"
      source_column: string; // user's actual column name
      dtype: string;         // "string", "int", "datetime"
    }
  };
  io_fields: {               // from the upstream processor's io_schema.output
    [field_name: string]: string;  // e.g. {"info_found": "string", "spans": "[{span}]"}
  };
}
```

The GUI uses `EdgeSchema.data_type` + the downstream processor's `consumes`
field to validate connections.  If `data_type` is not in the processor's
`consumes` list, the connection is rejected with a message explaining what
data types the processor accepts.

### 2.6 Preset Flow Templates

> **Status: implemented.** Templates are live in `config/templates/`,
> exposed by `server/routes/templates.py`, and surfaced in
> `gui/src/components/NewFlowDialog.tsx`.

New users should not face a blank canvas.  The app ships with three built-in
templates that cover the most common pipeline shapes.  Templates are regular
flow YAML files stored in `config/templates/` on the backend.

| Template | Pipeline shape | Target user |
|----------|---------------|-------------|
| **Label Extraction + Summary** | CSV Data → Group By → Label Extraction → Label Summary → CSV Output | Grouped multi-document analysis (the primary use case) |
| **Flat Summary + Classification** | CSV Data → Summary → Classification → CSV Output | One row = one entity, no grouping |
| **Full Pipeline** | CSV Data → Group By → Label Extraction → Label Summary → Classification → Evaluation → CSV Output | All steps enabled; for experienced users |

When a user clicks "New Flow", they see:

```
┌─────────────────────────────────────────────────────────────┐
│  Create a new flow                                          │
│                                                             │
│  Start from a template:                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ ● Label Extraction + Summary (grouped)              │    │
│  │   Best for: multiple documents per entity            │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ ○ Flat Summary + Classification                     │    │
│  │   Best for: one document = one entity                │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ ○ Full Pipeline (all steps)                         │    │
│  │   Extraction + summary + classification + evaluation │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ ○ Blank canvas                                      │    │
│  │   Start from scratch                                 │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  [ Cancel ]                              [ Create Flow ]    │
└─────────────────────────────────────────────────────────────┘
```

After selecting a template and clicking "Create Flow", the canvas loads
with the pre-wired nodes.  The user then uploads their CSV, maps columns,
and configures LLM settings.  All nodes are fully editable — the template
is a starting point, not a locked configuration.

### 2.7 Taxonomy Editor

> **Status: partially implemented.** Taxonomy CRUD exists in the backend
> and GUI, but the in-node property-panel editor described below is only
> partly realised.

New users on the hosted app cannot reference a server-side `taxonomy.json`
file path.  The Taxonomy resource node includes an in-app editor for
creating and managing taxonomies.

When the user clicks a Taxonomy resource node, its property panel shows:

```
┌─────────────────────────────────────────────────────────────┐
│  ⚪ Taxonomy — Properties                                    │
│                                                              │
│  Name   [ my_taxonomy             ]                          │
│                                                              │
│  Labels:                                      [+ Add label]  │
│  ┌────────────────┬───────────────────────────────────┬───┐  │
│  │ desenlace      │ Outcome of the event              │ ✎ │  │
│  │                │ Options: muerte, herido, ileso     │ ✕ │  │
│  ├────────────────┼───────────────────────────────────┼───┤  │
│  │ captura_tipo   │ Type of capture or detention       │ ✎ │  │
│  │                │ Options: captura, retencion, ...   │ ✕ │  │
│  ├────────────────┼───────────────────────────────────┼───┤  │
│  │ grupo_social   │ Social group of the victim         │ ✎ │  │
│  │                │ Options: campesino, indigena, ...  │ ✕ │  │
│  └────────────────┴───────────────────────────────────┴───┘  │
│                                                              │
│  [Import JSON]  [Export JSON]                                │
└─────────────────────────────────────────────────────────────┘
```

Each label has:
- **Key** (machine name, e.g. `desenlace`)
- **Definition** (human description, used in LLM prompts)
- **Options** (valid classification values for this label)
- **Context definition** (detailed extraction guidance, used by label
  extraction prompts)

The editor supports:
- Add / edit / delete individual labels
- Import a complete taxonomy from a JSON file (for users migrating from
  the CLI workflow)
- Export the current taxonomy as JSON

Backend endpoints:
- `POST /api/taxonomy` — create a new taxonomy (stored in DB, not filesystem)
- `PUT /api/taxonomy/:id` — update an existing taxonomy
- `GET /api/taxonomy/:id` — fetch a taxonomy by ID
- `GET /api/taxonomy` — list all taxonomies for the current user

In the flow YAML, hosted taxonomies are referenced by ID rather than file
path:

```yaml
taxonomy: taxonomy://my_taxonomy    # hosted taxonomy
# or
taxonomy: config/taxonomy.json      # local file (CLI mode)
```

### 2.8 UX Approach: All Features Visible

> **Status: partially implemented.** Tabbed property panels, palette
> descriptions, and template-based onboarding exist, but some of the
> richer discoverability copy and validation guidance described below are
> still missing.

The GUI takes a power-user approach: all features (node palette, I/O schema
editor, prompt editor, unit badges, resource nodes) are visible from the
start.  There is no "beginner mode" that hides advanced capabilities.

Discoverability is handled through:
- **Tooltips**: every node type in the palette shows its `description`
  (from the registry) on hover.
- **Property panel headers**: each node's property panel starts with a
  "What does this do?" line pulled from the registry `description`.
- **Preset templates** (section 2.6): new users start from a working
  template rather than a blank canvas, so they see a functional pipeline
  before they need to understand every node type.
- **Validation messages**: when the user makes an invalid connection, the
  error message explains *why* in plain language (e.g. "Label Extraction
  expects grouped data. Add a Group By node first.").

### 2.9 Security Considerations

> **Status: partially implemented.** Declarative flow execution and
> env-based secret handling exist, but the broader auth, encrypted key
> storage, upload policy, and rate-limit controls in this section are only
> partly implemented.

| Concern | Mitigation |
|---------|------------|
| API keys in YAML | Never store keys in YAML. Use `api_key_env` to reference env vars. Backend reads from `os.environ`. GUI has a "secrets" settings page that sets env vars on the server (or uses Render's env var config). |
| User-uploaded CSVs | Validate file size (max 50MB), file type (CSV only), and column names before processing. Sandbox uploads in per-user directories. |
| Arbitrary code execution | The flow schema is declarative — it only maps to pre-defined step types. No `eval()` or dynamic code. |
| Multi-tenancy | MVP is single-user. For multi-user: add auth (Render supports OAuth), per-user storage, and rate limiting on `/api/flow/run`. |
| Cost control | OpenRouter supports per-key spend limits. Backend enforces max rows per run (configurable). |

### 2.10 Detailed Effort Breakdown

> **Status: partially implemented.** Most major rows in this breakdown now
> exist in code and tests, but encrypted API-key storage, free-tier
> enforcement, and richer edge-schema UX remain unfinished.

| Component | Effort | Dependencies |
|-----------|--------|--------------|
| **Phase 1 (prerequisite)** | | |
| Pydantic schema models (column_roles, unit, io_schema, prompt resolution, named resources) | 2 days | pydantic (already installed) |
| `src/flow_builder.py` (parser + wiring + column mapping + io_schema→response_format + per-step LLM) | 3–4 days | Schema models + existing `src/processors.py` |
| Checkpointing + resume logic (entity-level checkpoint, `--resume` CLI flag) | 2 days | `flow_builder.py` |
| `scripts/run_custom_flow.py` | 0.5 day | `flow_builder.py` |
| Flow YAML migration (settings → flows) | 0.5 day | `flow_builder.py` |
| **Phase 2 — Backend** | | |
| FastAPI app scaffold (`/api/*` endpoints, CORSMiddleware) | 1–2 days | FastAPI, uvicorn |
| CSV upload + column detection + validation | 1–2 days | pandas, Render Disk or S3 |
| API key management (store/encrypt/validate per user) | 1–2 days | cryptography, Render env vars |
| Free tier enforcement (processing limit cap, run cap, house key) | 1 day | Server-side middleware |
| Model list proxy (fetch from OpenRouter/OpenAI, cache) | 0.5 day | httpx |
| Node type registry endpoint (with unit + default io_schema + default prompts + descriptions) | 1 day | Pydantic models from Phase 1 |
| Flow validation endpoint (unit compat + io_schema compat between nodes) | 1–2 days | `flow_builder.py` |
| Flow execution + background task + resume endpoint | 1–2 days | Celery+Redis or BackgroundTasks |
| Flow CRUD (save / update / delete / duplicate) | 1 day | SQLite or PostgreSQL |
| Results preview endpoint (`/api/flow/results/:id`, first 20 rows) | 0.5 day | |
| File download (full results CSV) | 0.5 day | |
| Taxonomy CRUD (create / update / list) | 1 day | SQLite or PostgreSQL |
| **Phase 2 — Frontend** | | |
| React + Vite + React Flow scaffold | 1 day | Node.js, npm |
| Node palette + drag-drop canvas | 2–3 days | React Flow |
| Undo/redo (Zustand temporal middleware) | 0.5 day | Zustand |
| Column mapper UI (Data Source + Group By panels, plain-language labels) | 2–3 days | React Hook Form, column data from backend |
| Unit-aware edge rendering (badges, schema propagation, validation) | 1–2 days | React Flow custom edges |
| LLM Provider panel (model picker with live list + pricing) | 1–2 days | Backend model list proxy |
| API Keys settings page | 1 day | Encrypted storage, test endpoint |
| Processing limit selector + free tier UX (grayed options, banner) | 0.5 day | |
| Cost estimator (pre-run confirmation dialog) | 0.5 day | Token estimation heuristic |
| I/O Schema editor (editable k:v table on each node) | 2–3 days | React Hook Form, dynamic form rows |
| Prompt editor panel (instructions editor + placeholder reference) | 1–2 days | Code editor component (Monaco or textarea) |
| Property panel framework (tabs: Config / I/O Schema / Prompt) | 1–2 days | React Hook Form, Zod |
| Taxonomy editor (in-app label CRUD + import/export JSON) | 1 day | Backend taxonomy endpoints |
| YAML export/import | 1 day | js-yaml |
| Run flow + log viewer + results preview table | 1–2 days | WebSocket or polling |
| My Flows page (list / open / duplicate / delete saved flows) | 1 day | Backend flow CRUD |
| New Flow dialog (template selection) | 0.5 day | Backend template list |
| **Phase 2 — Deployment** | | |
| Render setup (backend + frontend + Redis) | 0.5 day | Render account |
| OpenRouter house key + budget cap config | 0.5 day | OpenRouter account |
| CI/CD (GitHub Actions → Render auto-deploy) | 0.5 day | GitHub |
| **Total Phase 1** | **~8 days** | |
| **Total Phase 2** | **~30–40 days** | |
| **Grand Total** | **~38–48 days** | |

### 2.11 Lighter Alternative: Streamlit Form (instead of full GUI)

> **Status: not implemented.** This repo chose the React/FastAPI path;
> there is no Streamlit alternative app checked in.

If a full React node editor is overkill for the current use case (mostly
linear pipelines), a Streamlit app provides 80% of the value at 20% effort:

```
┌───────────────────────────────────────────────────────────┐
│  Streamlit App (on Render)                                │
│                                                           │
│  Step 1: Upload CSV → preview columns + first rows        │
│  Step 2: Map columns:                                     │
│          Text column     [ article_body  ▾ ]              │
│          Document ID     [ report_id     ▾ ]              │
│  Step 3: Grouping?                                        │
│          ☑ Group by entity                                │
│          Entity column   [ case_number   ▾ ]              │
│          Sort column     [ pub_date      ▾ ]              │
│          → "83 entities, avg 15 docs/entity"              │
│  Step 4: Select model (dropdown)                          │
│  Step 5: Pick pipeline type                               │
│          ○ Label extraction + summary (grouped)           │
│          ○ Single-pass summary (flat)                     │
│          ○ Summary + classification                       │
│  Step 6: Configure (temp, tokens, labels to extract)      │
│  Step 7: [Run] → progress bar                             │
│  Step 8: Download results CSV                             │
│                                                           │
│  [Export as YAML] [Load YAML]                             │
└───────────────────────────────────────────────────────────┘
```

| Aspect | Streamlit | React + React Flow |
|--------|-----------|-------------------|
| Effort | 2–3 days on top of Phase 1 | ~30–40 days on top of Phase 1 |
| Hosting | Render or Streamlit Community Cloud (free) | Render (static + web service) |
| Node editor | No (form-based) | Yes (full drag-drop) |
| Custom topologies | Limited (predefined pipeline shapes) | Full DAG support |
| Best for | Linear pipelines, quick config, current team | Non-technical users, complex branching flows, product demo |

### 2.12 Recommended Project Layout

> **Status: partially implemented.** The repo broadly matches this layout
> (`src/`, `config/`, `server/`, `gui/`, `render.yaml`), but several names
> and file placements differ from the plan.

```
messy_text/
├── src/
│   ├── processors.py           # existing (unchanged)
│   ├── flow_builder.py         # NEW (Phase 1)
│   ├── flow_loader.py          # NEW (reads + validates flow YAML via Pydantic)
│   └── ...
├── config/
│   ├── flows/                  # NEW (Phase 1)
│   │   ├── label_conversation_70b.yml
│   │   ├── label_conversation_qwen.yml
│   │   └── single_processing_8b.yml
│   ├── templates/              # NEW (Phase 2) — preset flow templates
│   │   ├── label_extraction_summary.yml
│   │   ├── flat_summary_classification.yml
│   │   └── full_pipeline.yml
│   ├── settings*.yaml          # existing (kept for backward compat)
│   ├── prompts.json
│   └── taxonomy*.json
├── scripts/
│   ├── run_custom_flow.py      # NEW (Phase 1)
│   └── ...                     # existing scripts (kept)
├── server/                     # NEW (Phase 2)
│   ├── app.py                  # FastAPI app
│   ├── routes/
│   │   ├── schema.py           # /api/schema/* endpoints
│   │   ├── flow.py             # /api/flow/* CRUD + run + resume
│   │   ├── taxonomy.py         # /api/taxonomy/* CRUD
│   │   └── files.py            # /api/files/* (upload/download)
│   ├── tasks.py                # background flow execution + checkpointing
│   ├── Dockerfile
│   └── requirements.txt
├── gui/                        # NEW (Phase 2)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Canvas.tsx      # React Flow wrapper
│   │   │   ├── NodePalette.tsx
│   │   │   ├── PropertyPanel.tsx
│   │   │   ├── FlowManager.tsx # My Flows page (list/open/dup/delete)
│   │   │   ├── TaxonomyEditor.tsx # in-app taxonomy CRUD
│   │   │   ├── ResultsPreview.tsx # post-run output table
│   │   │   ├── NewFlowDialog.tsx  # template picker
│   │   │   └── LogViewer.tsx
│   │   ├── nodes/              # custom node components
│   │   │   ├── DataSourceNode.tsx
│   │   │   ├── LLMProviderNode.tsx
│   │   │   ├── ProcessingNode.tsx
│   │   │   └── OutputNode.tsx
│   │   ├── store/              # Zustand stores
│   │   ├── lib/
│   │   │   ├── serialise.ts    # graph ↔ YAML conversion
│   │   │   └── api.ts          # backend API client
│   │   └── types/
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── render.yaml                 # NEW — Render Blueprint (IaC)
└── ...
```

### 2.13 Render Blueprint (`render.yaml`)

> **Status: partially implemented.** A Render blueprint exists in
> `render.yaml`, but it is explicitly marked not yet deployed and differs
> from the exact example below.

Infrastructure-as-code for one-command deployment:

```yaml
services:
  - type: web
    name: messy-text-api
    runtime: python
    buildCommand: pip install -r server/requirements.txt
    startCommand: uvicorn server.app:app --host 0.0.0.0 --port 8000
    envVars:
      - key: OPENROUTER_API_KEY
        sync: false                # set manually in Render dashboard
      - key: DATABASE_URL
        fromDatabase:
          name: messy-text-db
          property: connectionString
    disk:
      name: messy-text-data
      mountPath: /data
      sizeGB: 1

  - type: web
    name: messy-text-gui
    runtime: static
    buildCommand: cd gui && npm ci && npm run build
    staticPublishPath: gui/dist
    headers:
      - path: /*
        name: Cache-Control
        value: public, max-age=3600
    routes:
      - type: rewrite
        source: /*
        destination: /index.html

  - type: redis
    name: messy-text-redis
    plan: free
    maxmemoryPolicy: allkeys-lru

databases:
  - name: messy-text-db
    plan: free
```

### 2.14 Suggested Implementation Order

> **Status: implemented.** The major deliverables listed in this sequence
> now exist across `src/`, `server/`, `gui/`, and the test suite, with the
> remaining gaps called out in earlier status notes.

```
Week 1:  Phase 1 — flow_loader.py (Pydantic models: column_roles, unit
         validation, io_schema definition, prompt resolution logic,
         schema_version).  io_schema → JSON Schema converter.

Week 2:  Phase 1 cont. — flow_builder.py (with LLM shorthand
         normalisation), run_custom_flow.py.  Entity-level checkpointing
         + --resume flag.  Migrate 2–3 existing settings to flow YAMLs.
         Verify locally that generated response_format matches current
         hard-coded ones.

Week 3:  Phase 2 backend — FastAPI scaffold (with CORSMiddleware), CSV
         upload + column detection, node-type registry (with descriptions,
         unit, default io_schema, default prompts, input_transform rules),
         validate endpoint (unit + io_schema compatibility), flow CRUD,
         taxonomy CRUD, resume endpoint.

Week 4:  Phase 2 frontend — React + React Flow scaffold, node palette
         (with description tooltips), canvas + undo/redo.  Data Source
         node with column mapper (plain-language labels).  Group By node
         with entity preview.  Unit-aware edge rendering with schema
         badges (click to inspect).

Week 5:  I/O Schema editor (editable k:v table).  Prompt editor panel.
         Three-tab property panel framework (Config / I/O Schema / Prompt).
         Taxonomy editor (in-app CRUD + import/export).

Week 6:  YAML export/import.  Run flow + log viewer + results preview
         table.  Processing limit selector (entity-aware).  My Flows page
         (list / open / duplicate / delete).  New Flow dialog with
         template selection.

Week 7:  Deploy to Render.  End-to-end test with OpenRouter.  Preset
         flow templates.  File download.

Buffer:  1 week for polish, edge cases, auth (if needed).
```

---

## Open Questions

1. **Auth**: Is the app single-user (just you) or multi-user? Single-user
   simplifies everything (no auth, no per-user storage). Multi-user needs
   OAuth + user isolation + per-user file storage for uploaded CSVs.
2. **Evaluation on hosted**: SummaC requires a GPU (`device: "cuda"` in
   settings). On Render (CPU-only), evaluation steps either need to be
   disabled, switched to `device: "cpu"` (slow), or run separately on a GPU
   machine. This affects which steps are available in the GUI.
3. **Data sensitivity**: If the CSVs contain sensitive victim data, hosting on
   a third-party platform needs careful consideration (encryption at rest,
   access controls, data residency).  Uploaded CSVs must be sandboxed per
   user and auto-deleted after a configurable retention period.
4. **Cost budget**: OpenRouter charges per token. A full run of ~500 entities
   with Llama 70B might cost $5–20 depending on document length. Is there a
   per-run budget cap?
5. **Column type detection**: Should the backend auto-detect column types
   (datetime for sort, numeric for IDs) and suggest role mappings, or leave
   it fully manual?  Auto-detect is a nice-to-have but adds complexity
   (date format parsing, handling mixed types).
6. **Output schema**: When the pipeline runs at `unit: entity`, should the
   output CSV be one row per entity (collapsed), or broadcast back to all
   original rows (current behaviour)?  The plan supports both via the
   `output_unit` field on the CSV Output node, but the default matters for
   user expectations.

---

## Appendix: Project-Wide Python Documentation and Naming Standards

These standards apply to Python code across the project. The same rules apply
to schema modules, processors, builders, helpers, validators, utilities, and
other Python files.

Each Python module should be written as a self-explanatory unit, not just a
container of classes and functions. The file should follow these rules:

1. **Module-level docstring is mandatory.** It must explain:
   - what the module contains, including classes, functions, helpers,
     validators, enums, dataclasses, and constants when relevant,
   - how those objects relate to one another,
   - how the rest of the system uses the module,
   - what invariants the module enforces.
2. **Every object must have a Google-style docstring.**
   - Every Pydantic model, enum, dataclass, and helper object must explain its
     purpose.
   - Model docstrings must document fields in an `Attributes:` section.
   - If the object exposes important behavior, that behavior must also be
     registered in a `Methods:` section.
   - If an object exists only to support another object, say that explicitly.
3. **Every method must have a Google-style docstring.**
   - Include `Args:` with parameter names and types.
   - Include `Returns:` with the concrete return type and meaning.
   - Include `Raises:` when validation, parsing, or normalisation can fail.
   - This applies to validators, class methods, parsing helpers, and schema
     conversion helpers.
4. **Variable names must be meaningful, domain-based, and non-conflating.**
   - Do not use single-letter placeholders except for conventional loop indexes
     where the meaning is obvious and local.
   - Do not hardwire literal values into variable names.
   - Do not reuse the raw value as the variable name.
   - Prefer names that describe the role in the domain, such as
     `entity_column_name`, `document_identifier_column`,
     `llm_provider_config`, `validated_step_config`, or
     `processing_result_row`.

Use Google-style docstrings consistently. The minimum expected shapes are:

```python
"""Describe the purpose and usage of this module.

This module contains the main objects, helpers, and validation rules for its
part of the system. Other modules import these objects to perform application
logic, and the docstring should explain the module's responsibility, object
relationships, and important guarantees.
"""
```

For objects:

```python
class FlowStepConfig(BaseModel):
    """Describe one processing step declared in a configuration model.

    Attributes:
        type: str. The registered step type used by the builder to choose a
            processor implementation.
        unit: str. The unit of analysis consumed by this step.
        group_by: str | None. The grouping rule applied before the step runs.

    Methods:
        validate_group_by: Validate that the grouping mode is compatible with
            the step type.
    """
```

For methods:

```python
def validate_group_by(self, group_by: str | None) -> str | None:
    """Validate that the grouping mode is compatible with the step type.

    Args:
        group_by (str | None): The grouping mode declared in the YAML step
            definition.

    Returns:
        str | None: The validated grouping mode, or `None` when grouping is not
        required.

    Raises:
        ValueError: If the grouping mode is invalid for the current step type.
    """
```

Naming examples:

- Bad: `v = "Jone"`
- Bad: `jone = "jone"`
- Good: `victim = "jone"`
- Good: `entity = "jone"`

Across project Python code, prefer role-revealing names over generic ones. For
example, use `entity_column_name` instead of `value`, `schema_config` instead of
`data`, and `normalised_resource_config` instead of `resource`.
