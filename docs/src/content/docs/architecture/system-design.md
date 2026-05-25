---
title: System Design
description: How the backend, worker, and frontend fit together.
---

## Components

| Component | Technology | Port |
|-----------|-----------|------|
| Frontend | React + React Flow (Vite) | 5173 |
| Backend | FastAPI | 8000 |
| Worker | Celery (solo pool) | — |
| Broker / State | Redis (DBs 0–2) | 6379 |

## Data flow

1. The GUI sends flow definitions to the backend via REST.
2. The backend validates the flow YAML and enqueues a Celery task.
3. The worker executes the flow: reads input data, calls the LLM for each row, writes results.
4. Run status and logs stream back to the GUI via SSE.

## Paths

All file paths in flow YAMLs are project-root-relative and POSIX-style. The backend and worker share a common `WORKDIR /app` so the same relative paths resolve identically in both processes.
