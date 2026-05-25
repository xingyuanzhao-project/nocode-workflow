---
title: Flow Engine
description: How flows are loaded, validated, and executed.
---

## Flow lifecycle

1. **Define** — user builds a graph in the GUI (nodes + edges).
2. **Serialize** — the GUI codec converts the graph to a flow YAML.
3. **Validate** — `src.flow_loader.FlowSchema` validates the YAML against the node type registry.
4. **Dispatch** — `server.services.run_dispatcher` writes the YAML to a per-run directory and enqueues a Celery task.
5. **Execute** — `src.flow_builder.build_flow(resume=True)` runs each step, calling the LLM via the configured provider.
6. **Checkpoint** — completed rows are written to `.checkpoint/completed_entities.json`. Resume skips these.

## Prompt construction

The `PromptConstructor` assembles the final prompt from:

- **Base instructions** — user-written text in the processor node.
- **Injection layers** — codebook context, output format schema. Each layer is conditional: absent if its context is empty.
