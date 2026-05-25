---
title: How it works
description: Every element in the flow editor, explained.
---

Go to [academic-pipeline-gui.onrender.com](https://academic-pipeline-gui.onrender.com). No installation or account required.

## The canvas

The flow editor is a visual canvas where you build processing workflows by dragging nodes from the palette on the left and connecting them with edges. Select any node to configure it in the property panel on the right.

## Node palette

The palette groups nodes into three categories.

### Data nodes

**CSV Input** — Select an uploaded `.csv` file and choose which columns to pass downstream. Configured with a file selector dropdown and a list of input column selectors.

**JSON Input** — Same as CSV Input but for `.json` and `.jsonl` files. The column selectors are labelled "Input Fields."

**CSV Output** — Writes processing results to a `.csv` file. Configured with an output path, a list of output field names, and an append/overwrite toggle.

**JSON Output** — Writes results to a `.json` file. Same configuration as CSV Output.

### Processor nodes

**Processor** — The core processing node. Each processor takes row data from the left, optionally calls an LLM (via the top handle) and optionally consults a codebook (via the bottom handle), then emits results to the right.

Selecting a processor opens three tabs in the property panel:

- **Config** — Shows the processing unit (always `row`).
- **Output Schema** — Define the fields you want back per row. Each field has a name, a data type (`string`, `binary`, `category`, `numeric`, `integer`), and a required flag. Category fields accept a list of allowed options. Numeric and integer fields accept range bounds.
- **Prompt** — Write the instructions the LLM receives for each row, one instruction per line.

### Resource nodes

**LLM Call** — An OpenAI-compatible chat completions endpoint. Configured with a provider (`openrouter`, `openai`, `claude`, `google`, `ollama`, `vllm`, `llama_cpp`), a model selector, and a temperature slider (0–2). The API key environment variable is derived automatically from the provider.

**Codebook** — A taxonomy resource that provides context and guides the LLM. Select a saved codebook from the dropdown and choose which fields to include in the prompt.

## Connections

Nodes connect through typed edges. The canvas enforces valid connections automatically.

- **Feedforward** — Data flows left to right. Connects an input node or processor to the next processor or output node.
- **LLM Call** — Connects from the top handle of a processor to an LLM Call node.
- **Codebook Inquiry** — Connects from the bottom handle of a processor to a Codebook node.

A typical flow:

```
[Input] → [Processor] → [Output]
               ↑    ↓
          [LLM Call] [Codebook]
```

Processors can be chained in sequence. Each processor in the chain can have its own LLM Call and Codebook.

## Toolbar

The top toolbar provides workflow-level controls:

- **Flow name** — Editable title for your flow.
- **Limit** — Maximum number of rows to process. Leave empty to process all rows.
- **Undo / Redo** — Step through graph edit history.
- **Import YAML** — Load a flow from a `.yml` or `.yaml` file.
- **Export YAML** — Download the current flow as YAML.
- **Save** — Persist the flow to the server.
- **Run** — Opens a cost estimate dialog showing the model, estimated API calls, tokens, and cost. Confirm to start the run.

## Property panel

Click any node on the canvas to open its configuration in the right panel. The panel shows:

- A header with the node category and label.
- A **Delete** button to remove the node and its connected edges.
- One to three tabs depending on the node type (Config, Output Schema, Prompt).

## Running and results

After clicking **Run** and confirming the cost estimate, rows process concurrently against the selected model. Results are downloadable from the run page. If a run is interrupted, use **Resume** on the run page to pick up from the last completed row.

## Supported file formats

| Direction | Formats |
|---|---|
| Input | `.csv`, `.json`, `.jsonl` |
| Output | `.csv`, `.json` |
| Flow import/export | `.yml`, `.yaml` |
