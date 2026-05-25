---
title: Node Types
description: The node types available in the flow editor.
---

## Categories

### Data nodes

| Node | Purpose |
|------|---------|
| CSV Input | Read rows from an uploaded CSV |
| JSON Input | Read records from a JSON/JSONL file |
| CSV Output | Write results to CSV |
| JSON Output | Write results to JSON |

### Processor nodes

| Node | Purpose |
|------|---------|
| Processor | Generic LLM processing step — configure prompt and output schema per node |

### Resource nodes

| Node | Purpose |
|------|---------|
| LLM Call | OpenAI-compatible chat completions endpoint — provider, model, generation parameters |
| Codebook | Classification taxonomy for label extraction |

Node types are defined in `config/node_types.yaml`. The GUI palette and the flow validator both read from this registry.
