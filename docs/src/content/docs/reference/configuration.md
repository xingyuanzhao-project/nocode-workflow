---
title: Configuration
description: Environment variables and settings.
---

## Environment variables

All settings are read from environment variables prefixed with `ACADEMIC_PIPELINE_`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ACADEMIC_PIPELINE_REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `ACADEMIC_PIPELINE_REDIS_BROKER_DB` | `0` | Celery broker DB |
| `ACADEMIC_PIPELINE_REDIS_RESULT_DB` | `1` | Celery result DB |
| `ACADEMIC_PIPELINE_REDIS_APP_DB` | `2` | Application state DB |
| `ACADEMIC_PIPELINE_DATA_DIR` | `server/data` | Runtime data directory |
| `ACADEMIC_PIPELINE_MAX_UPLOAD_BYTES` | `524288000` | Upload size limit (500 MiB) |
| `ACADEMIC_PIPELINE_LOG_LEVEL` | `INFO` | Log level |
| `ACADEMIC_PIPELINE_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |

Settings are loaded by `server.settings.ServerSettings` (Pydantic Settings).
