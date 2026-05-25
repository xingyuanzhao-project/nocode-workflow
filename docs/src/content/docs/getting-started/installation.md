---
title: Installation
description: Set up Academic Pipeline locally.
---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Redis (bundled Windows binary at `tools/redis/`, or system install)

## Clone and install

```bash
git clone https://github.com/xingyuanzhao-project/academic-pipeline.git
cd academic-pipeline
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

```bash
pip install -r requirements.txt -r server/requirements.txt
cd gui && npm ci && cd ..
```

## Start the app

```bash
python run.py
```

This starts Redis, the FastAPI backend, the Celery worker, and the Vite frontend. The browser opens automatically at `http://127.0.0.1:5173`.
