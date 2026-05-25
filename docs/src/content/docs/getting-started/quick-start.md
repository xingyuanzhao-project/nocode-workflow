---
title: Quick Start
description: Run your first processing flow.
---

## Create a flow

1. Open the GUI at `http://127.0.0.1:5173`.
2. Drop a **CSV Input** node onto the canvas.
3. Upload a CSV file with a text column.
4. Add a **Processor** node — configure its prompt and output schema.
5. Connect an **LLM Call** resource node (select provider and model).
6. Add a **CSV Output** node and connect it downstream.

## Run

Click **Run**. The backend dispatches the flow to Celery, processes each row through the LLM, and streams logs back to the GUI via SSE.

## Resume

If a run is interrupted, click **Resume**. The checkpoint picks up from the last completed row.
