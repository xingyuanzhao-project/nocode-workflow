---
description: Guide for authoring graph-style flows in academic_pipeline.
globs:
  - "config/flows/*.yml"
  - "config/templates/*.yml"
  - "server/data/flows/*.yml"
alwaysApply: false
trigger: Whenever you build or modify a flow, read this guide first; When ever flow designs are changed, this guide should be updated.
---

# Flow Building

Use the graph format only. Do not use the old flat `resources/data/processors/output/...` shape.

## Top-Level Shape

Every flow file should be:

```yaml
flow:
  name: my_flow
  description: Short description
  nodes: []
  edges: []
  settings: {}
```

Required rules:

- Exactly one input node: `csv_input` or `json_input`
- At least one `processor` node
- Exactly one output node: `csv_output` or `json_output`
- Flow order comes from `feedforward` edges

## Node Types

### `csv_input` / `json_input`

Purpose: choose the source file.

Use:

```yaml
type: csv_input
config:
  selected_file: data/my_file.csv
  input_columns:
    - text
    - victim
```

Notes:

- `selected_file` is required
- Use project-relative POSIX paths only
- Prefer plain `input_columns: ["col1", "col2"]`
- Legacy `column_roles` still works, but do not use it in new flows

### `processor`

Purpose: one generic LLM-backed processor.

Use:

```yaml
type: processor
config:
  unit: row
  prompt:
    instructions:
      - "Your instruction here."
  io_schema:
    output:
      summary:
        type: string
```

Notes:

- For this project, use `type: processor`
- Do not use legacy processor types like `single_summary`, `classification`, `label_extraction`, `label_summary`, `conversation_summary_first`, or `conversation_summary_update`
- Keep `unit: row`
- Put task meaning in `prompt` and `io_schema`, not in the processor type
- `processor_type` in config selects the registered processor type; the valid runtime value is `processor`

Prompt rules:

- Use `prompt` for inline instructions
- Use `prompts_ref` only if the flow has a valid `settings.prompts` file
- Do not set both `prompt` and `prompts_ref`
- `prompt_overrides` requires `prompts_ref`

### `llm_call`

Purpose: define the LLM resource used by a processor.

Use:

```yaml
type: llm_call
config:
  resource_id: default
  provider: openrouter
  model: meta-llama/llama-3.1-70b-instruct
  api_key_env: OPENROUTER_API_KEY
  temperature: 0.0
  max_tokens: 512
```

Notes:

- Every processor must connect to one `llm_call` node
- If multiple processors share one resource, reuse the same `resource_id` and the same config
- Use `api_key_env` for hosted providers
- Local providers may use dummy keys

### `codebook`

Purpose: attach taxonomy/codebook data to a processor.

Use:

```yaml
type: codebook
config:
  codebook_path: server/data/taxonomies/my_taxonomy.json
```

Or:

```yaml
type: codebook
config:
  codebook_id: my_taxonomy
  selected_keys:
    - key_a
    - key_b
```

Notes:

- Connect it with a `codebook_inquiry` edge
- The runtime supports one effective codebook per flow
- For CLI/local runs, prefer `codebook_path`
- `codebook_id` becomes `taxonomy://...` and depends on server-side resolution

### `csv_output` / `json_output`

Purpose: define output file location.

Use:

```yaml
type: csv_output
config:
  output_path: results_custom/my_flow/output.csv
  output_fields:
    - summary
  extend: false
```

Notes:

- `output_path` is required
- Keep `output_fields` aligned with `processor.config.io_schema.output` keys
- `extend: true` appends while replacing rows for the current model

## Edge Types

### `feedforward`

Defines execution order.

Example:

```yaml
- type: feedforward
  source: input_1
  target: proc_1
```

Use a simple chain:

`input -> processor -> processor -> output`

### `llm_call`

Connects one processor to one LLM node.

```yaml
- type: llm_call
  source: proc_1
  target: llm_1
```

### `codebook_inquiry`

Connects one processor to a codebook node.

```yaml
- type: codebook_inquiry
  source: proc_1
  target: codebook_1
```

## `settings`

Use:

```yaml
settings:
  processing_limit: 10
  async:
    enabled: true
    max_concurrent_rows: 5
    max_concurrent_llm_calls: 5
    max_retries: 3
  logging:
    file: results_custom/my_flow/processing.log
    log_progress: true
  display:
    use_progress_bar: true
  prompts: config/prompts.json
```

Notes:

- `processing_limit` is optional
- `prompts` is flow-level, not per-processor
- If `prompts` does not exist, the runner continues, but `prompts_ref` lookups will not work

## Path Rules

All paths must be:

- project-relative
- POSIX-style
- written with forward slashes

Do not use:

- absolute paths
- Windows drive letters
- backslashes

## Minimal Pattern

Use `config/templates/test_generic_processor.yml` as the reference shape.

When creating a new flow:

1. Create one input node.
2. Create one or more `processor` nodes.
3. Connect each processor to one `llm_call` node.
4. Add a `codebook` node only if the processor needs taxonomy data.
5. Create one output node.
6. Add `feedforward` edges to define order.
7. Put processor behavior in `prompt` and `io_schema`.
8. Keep paths relative and output fields aligned with schema output.
