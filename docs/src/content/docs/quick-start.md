---
title: How it works
description: Every element in the application, explained.
---

Open the app at [nocode-workflow-gui.onrender.com](https://nocode-workflow-gui.onrender.com). No installation or account required.

## Navigation bar

The top bar has five sections:

- **Flows** — list of saved flows. Open, duplicate, or delete. Create a new blank flow from here.
- **Runs** — list of past and active runs with status badges.
- **Data** — upload and manage input files. Download output files.
- **Codebook** — create and manage codebooks to provide context for LLMs.
- **API Keys** — configure LLM provider credentials and local server endpoints.

---

## Data page

Upload input files before building a flow. Accepts `.csv`, `.json`, and `.jsonl`.

The page shows two sections:

- **Input Data** — uploaded files with filename, stored path, row count, and a download link.
- **Output Files** — files produced by completed runs, also downloadable.

Click **Upload file** to add a new file. The stored path shown in the table is used when selecting files inside input nodes on the canvas.

---

## Codebook page

A codebook defines label categories and options that get injected into the LLM prompt.

The list page shows all saved codebooks with name, last updated timestamp, and actions (Open, Delete). Click **Create** to start a new one.

### Codebook editor

The editor has:

- **Name field** — editable codebook title.
- **Label editor** — add, remove, and edit label entries. Each entry has a variable name, definition, data type (`String`, `Binary`, `Category`, `Numeric`, `Integer`), and a context field. Category entries accept a comma-separated list of allowed options. Numeric and integer entries accept range bounds and step size.
- **Import JSON** — load a codebook from a `.json` file.
- **Export JSON** — download the current codebook as `.json`.
- **Save** — persist to the server.

---

## API Keys page

Configure credentials for LLM providers. Two sections:

### Cloud providers

One row per provider: **OpenRouter**, **OpenAI**, **Claude**, **Google**. Each row shows:

- A status badge (Configured / unconfigured).
- The environment variable name the key maps to (e.g. `OPENROUTER_API_KEY`).
- A masked input field to enter or update the key.
- **Test** — validates the key against the provider's API.
- **Save** — stores the key in server memory for the current session.

### Local servers

One row per local provider: **Ollama**, **vLLM**, **llama.cpp**. Each row shows:

- A status badge.
- A URL input with a placeholder for the default endpoint (e.g. `http://localhost:11434/v1` for Ollama).
- **Test** — checks connectivity by hitting the server's `/models` endpoint.
- **Save** — stores the endpoint URL.

---

## Flows page

Lists all saved flows. Each row shows name, description, last updated timestamp, and three actions:

- **Open** — opens the flow in the canvas editor.
- **Duplicate** — creates a copy with "(copy)" appended to the name.
- **Delete** — removes the flow (with confirmation).

Click **New blank flow** to open the editor with an empty canvas.

---

## Flow editor

The editor has four regions: the **node palette** on the left, the **canvas** in the center, the **property panel** on the right, and the **toolbar** at the top.

### Toolbar

- **Flow name** — editable text field.
- **Status label** — shows "unsaved changes", "saved", or "new".
- **Limit** — maximum number of rows to process. Leave empty to process all rows.
- **Undo / Redo** — step through graph edit history.
- **Import YAML** — load a flow from a `.yml` or `.yaml` file.
- **Export YAML** — download the current flow as YAML.
- **Save** — persist to the server.
- **Run** — opens a cost estimate dialog before starting. The dialog shows the model, estimated API calls, token count, and cost. Confirm to start.

### Node palette

Drag nodes from the palette onto the canvas. Three categories:

**Data** — CSV Input, JSON Input, CSV Output, JSON Output.

**Processor** — Processor, the main component to carry out operations.

**Resources** — LLM Call, Codebook.

### Canvas

The center area. Nodes appear as cards with connection handles. Background is a dot grid with zoom controls and a minimap.

Drop a node from the palette. Click a node to open its configuration in the property panel. Draw edges between handles to connect nodes.

---

## Node types

### CSV Input

Select a `.csv` file from previously uploaded data. Choose which columns to pass to the processor.

**Property panel (Config tab):**

| Field | Description |
|---|---|
| Data file | Dropdown of uploaded `.csv` files |
| Input Columns | Add/remove column selectors. Selected columns are passed to the processor as input. |

The card shows the selected filename, or "No file selected."

### JSON Input

For `.json` and `.jsonl` files. The first layer of fields is treated as columns and is selectable. Field selectors are labelled "Input Fields" and "Field Name."

### Processor

The core processing node. Takes input data from the left handle, optionally calls an LLM via the top handle, optionally consults a codebook via the bottom handle, and emits results to the right handle.

The card shows the processing unit (`row`) and the output field names from the schema.

**Property panel has three tabs:**

**Config tab** — shows the processing unit (read-only, always `row`; may support other units of analysis in the future).

**Output Schema tab** — define the fields the LLM returns per row. Each field has:

| Setting | Description |
|---|---|
| Field name | The output field name |
| Required | Checkbox |
| Type | `String`, `Binary`, `Category`, `Numeric`, or `Integer` |
| Options | Comma-separated list of allowed values (shown for Category; disabled for String and Binary) |
| Range start / Range end | Bounds (Numeric and Integer types) |
| Step | Increment (Integer type only) |

Buttons: **Add field**, **Reset to default**.

**Prompt tab** — a text area for instructions sent as the system prompt to the LLM, one instruction per line. If the node uses a shared prompt reference (imported via YAML), a banner shows the reference name and the text area overrides it.

### LLM Call

Defines which LLM provider and model to use. Processors connect to this node via their top handle.

The card shows the resource id, provider, model, temperature, and max_tokens.

**Property panel (Config tab):**

| Field | Description |
|---|---|
| Resource id | Identifier, defaults to `"default"` |
| Provider | `openrouter`, `openai`, `claude`, `google`, `ollama`, `vllm`, `llama_cpp` |
| Model | Combobox loaded from the provider's model catalogue. Type a custom model id if needed. |
| API key env var | Read-only, derived from the provider (e.g. `OPENROUTER_API_KEY`). Configure the key in the API Keys page. |
| Reachable URL | Read-only, shown for local providers only. Configure in the API Keys page. |
| Temperature | Default 0 for better reproducibility |

### Codebook

Attaches a saved codebook to a processor. Processors connect to this node via their bottom handle.

The card shows the codebook id or "not selected."

**Property panel (Config tab):**

| Field | Description |
|---|---|
| Codebook | Dropdown of saved codebooks (create and manage codebooks in the Codebook page) |
| Fields to include in prompt | Checkboxes for each key in the codebook. Only checked fields are injected into the LLM prompt. |

### CSV Output

Writes processing results to a `.csv` file.

The card shows the output path, field names, and append/overwrite mode.

**Property panel (Config tab):**

| Field | Description |
|---|---|
| Output path | File path for the output (default: `results/output.csv`) |
| Output Fields | Add/remove field names. These become column headers in the output file. |
| Append to existing file | Checkbox. When checked, rows are appended instead of overwriting. |

### JSON Output

Writes results to a `.json` file. Same configuration as CSV Output.

---

## Connections

Nodes connect through three edge types. The canvas validates connections and rejects invalid ones.

| Edge type | From | To | Handle positions |
|---|---|---|---|
| Feedforward | Input or Processor (right handle) | Processor or Output (left handle) | Left to right |
| LLM Call | Processor (top handle) | LLM Call (bottom handle) | Top to bottom |
| Codebook Inquiry | Processor (bottom handle) | Codebook (top handle) | Bottom to top |

A typical flow:

```
[Input] → [Processor] → [Output]
               ↑
          [LLM Call]
```

Processors can be chained in sequence. Each processor in the chain can have its own LLM Call and Codebook.

---

## Run page

After clicking **Run** on the toolbar, the app navigates to the run page. The run page shows:

- **Status badge** — `queued`, `running`, `succeeded`, `failed`, or `cancelled`.
- **Progress bar** — completed rows / total rows, elapsed time, estimated time remaining, processing speed (rows/s).
- **Error banner** — shown if the run fails, with the error message.
- **Warnings** — any warnings emitted during processing.
- **Log stream** — live logs from the worker, streamed in real time (left panel).
- **Output preview** — table preview of the first 50 rows of output (right panel, shown when run succeeds).
- **Download output** — button to download the full output file.
- **Resume** — button shown for failed or cancelled runs. Picks up from the last completed row.

---

## Supported file formats

| Direction | Formats |
|---|---|
| Input data | `.csv`, `.json`, `.jsonl` |
| Output data | `.csv`, `.json` |
| Codebook import/export | `.json` |
| Flow import/export | `.yml`, `.yaml` |
