---
title: Quick Start
description: Process your first dataset in under five minutes.
---

## 1. Open the app

Go to [academic-pipeline-gui.onrender.com](https://academic-pipeline-gui.onrender.com). No installation or account required.

## 2. Upload a CSV

Click **CSV Input** on the canvas. Upload a file where each row has a text column you want to process (e.g. news articles, open-ended survey responses).

## 3. Add a processing step

Drag a **Processor** node onto the canvas and connect it to the input.

- Write instructions in the prompt panel (e.g. *"Summarise this article in one sentence"*).
- Define the output schema — the fields you want back per row (e.g. `summary: string`).

## 4. Connect an LLM

Drag an **LLM Call** node and attach it to the processor. Select a provider and model (any OpenAI-compatible endpoint via OpenRouter).

## 5. Add a codebook (optional)

For classification tasks, attach a **Codebook** node. Define your label categories and options. The codebook injects into the prompt automatically — the LLM classifies each row against your taxonomy.

## 6. Run

Connect a **CSV Output** node, then click **Run**. Rows process concurrently. Logs stream in real time.

If a run is interrupted, click **Resume** — it picks up from the last completed row.
