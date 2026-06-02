# server/ — nocode-workflow backend

FastAPI web process + Celery worker process, sharing Redis (for Celery
broker/result backend and application run status) and the filesystem
(for flow YAMLs, taxonomy JSONs, uploaded CSVs, and per-run artefacts).

## Layout (one responsibility per folder)

```
server/
  app.py                  FastAPI application factory.
  celery_app.py           Celery application factory + signal wiring.
  settings.py             ServerSettings (pydantic-settings).
  logging_config.py       JSON log formatter installer.
  redis_client.py         Application-owned Redis connection pool.
  dependencies.py         FastAPI Depends providers.
  errors.py               HTTP exception handlers.
  requirements.txt        Server-only runtime deps.
  Dockerfile              Single image used by both the web and the
                          worker container (command is declared per
                          docker-compose service, not in the image).

  storage/
    paths.py              ServerPaths (top-level directory layout).
    run_paths.py          RunPaths (per-run directory layout).

  schemas/                HTTP DTOs.
    node_types.py
    flow.py
    taxonomy.py
    run.py
    files.py
    health.py
    errors.py

  services/               Domain logic. Wraps src/ abstractions.
    node_catalog.py       Wraps src.node_registry.
    flow_validation.py    Wraps src.flow_loader.FlowSchema.
    flow_repository.py    CRUD over flow YAMLs on disk.
    taxonomy_repository.py CRUD over taxonomy JSONs on disk.
    csv_uploader.py       Accepts user-uploaded CSVs.
    run_registry.py       Redis-backed run status store.
    run_dispatcher.py     Writes per-run YAMLs and enqueues Celery tasks.

  workers/                Celery task bodies and signal handlers.
    flow_task.py          Calls src.flow_builder.build_flow(resume=True).
    signals.py            task_prerun / task_success / task_failure wiring.

  routes/                 HTTP routers. Thin; delegate to services.
    schema.py             /api/schema/*
    flow.py               /api/flow/*
    taxonomy.py           /api/taxonomy/*
    files.py              /api/files/*
    health.py             /api/health

  data/                   Runtime artefacts. Git-ignored.
    flows/                Saved flow YAMLs.
    taxonomies/           Saved taxonomy JSONs.
    uploads/              User-uploaded CSVs.
    runs/<run_id>/        Per-run artefacts (flow.yml, summary.csv,
                          results.csv, states.csv, spans.csv,
                          worker.log, .checkpoint/).
```

Abstraction rule: only `server/services/node_catalog.py`,
`server/services/flow_validation.py`, and
`server/workers/flow_task.py` are allowed to import from `src.*`.

## Redis DB layout

One Redis instance, three logical DBs:

| DB | Purpose                                 | Owner                          |
|----|-----------------------------------------|--------------------------------|
| 0  | Celery broker queue                     | Celery                         |
| 1  | Celery result backend                   | Celery                         |
| 2  | Application run status (`RunRegistry`)  | `server.services.run_registry` |

## Local dev workflow (one terminal)

Prereqs: Docker Desktop (or any Docker + Compose host).

```powershell
docker compose up --build
```

Starts Redis, the FastAPI web process, and the Celery worker, all as
containers built from the single `server/Dockerfile`. The web
container runs `uvicorn --reload` over bind-mounted `./src` and
`./server`, so edits on the host show up live without rebuilding. The
worker does not auto-reload; restart it with
`docker compose restart celery_worker` after editing worker code.

Open http://localhost:8000/docs to exercise the endpoints.

Follow per-service logs:

```powershell
docker compose logs -f web
docker compose logs -f celery_worker
docker compose logs -f redis
```

### Why containerise the web process too

Running both the web and the worker in the same image pins the dev
environment to match the Render deployment layout: same Python
interpreter, same Linux filesystem semantics, same POSIX path style,
same bind-mount root at `/app`. Flow YAMLs stay portable because
every filesystem field (`input_csv`, `output.*_csv`, `logging.file`,
`taxonomy`, `prompts`) is validated as project-root-relative POSIX
by `src.flow_loader._validate_project_relative_posix_path`, so the
same YAML resolves to the same absolute paths in every process.

### Using the project `.venv` on the host

The host `.venv` is still required to run the CLI entry point
(`scripts/run_custom_flow.py`) and any diagnostic scripts. Activate it
with `\.venv\Scripts\Activate.ps1`. The web and worker themselves no
longer read from the host `.venv` — they install their dependencies
from `requirements.txt` and `server/requirements.txt` during image
build.

## Endpoints (MVP)

### Node catalog & validation

- `GET  /api/schema/node-types` — list registered node types.
- `POST /api/schema/validate` — validate a raw flow dict.

### Flow CRUD

- `GET    /api/flow/list`
- `POST   /api/flow`
- `GET    /api/flow/{flow_id}`
- `PUT    /api/flow/{flow_id}`
- `DELETE /api/flow/{flow_id}`
- `POST   /api/flow/{flow_id}/duplicate`

### Flow runs

- `POST /api/flow/run` — ad-hoc run of an unsaved flow.
- `POST /api/flow/{flow_id}/run` — run a saved flow.
- `POST /api/flow/resume/{run_id}` — re-enqueue an existing run.
- `GET  /api/flow/status/{run_id}` — poll run status.

### Taxonomy CRUD

- `GET    /api/taxonomy`
- `POST   /api/taxonomy`
- `GET    /api/taxonomy/{taxonomy_id}`
- `PUT    /api/taxonomy/{taxonomy_id}`
- `DELETE /api/taxonomy/{taxonomy_id}`

### Files

- `POST /api/files/upload` — multipart CSV upload.

### Health

- `GET /api/health` — pings Redis and the Celery worker pool.

## Checkpoint / resume composition

`src.flow_builder._Checkpoint` writes
`<output_dir>/.checkpoint/completed_entities.json` where `output_dir`
is the parent of `flow.output.summary_csv`. The dispatcher rewrites
every output path in the flow YAML so it lands under
`server/data/runs/<run_id>/`, which pins the checkpoint directory to
`server/data/runs/<run_id>/.checkpoint/`.

`server.workers.flow_task.execute_flow` always calls
`build_flow(flow_yaml_path, resume=True)`:

- On a fresh run the checkpoint is empty, so `resume=True` is a no-op.
- On a retry (after `acks_late` requeue) or an explicit
  `POST /api/flow/resume/{run_id}` call, the checkpoint file lists the
  entities that already completed, and the flow skips them.

## Paths in flow YAMLs

Every file-path field in a flow YAML must be **project-root-relative
and POSIX-style** (forward slashes, no leading `/`, no Windows drive
letter). The rule covers:

- `flow.data.input_csv`
- `flow.output.summary_csv`, `results_csv`, `states_csv`, `spans_csv`
- `flow.logging.file`
- `flow.taxonomy`, `flow.prompts`

Enforced at validation time by
`src.flow_loader._validate_project_relative_posix_path`. The run
dispatcher emits output paths in the same form
(`server/data/runs/<run_id>/summary.csv`), and `POST /api/files/upload`
returns `stored_path` in the same form so clients can paste it
directly into a flow's `data.input_csv`.

Both the web container and the worker container use `WORKDIR /app`,
which maps to the project root via the bind mounts, so the same
relative string resolves to the same absolute path in both
processes.

## Configuration

All tunables read from environment variables prefixed with
`ACADEMIC_PIPELINE_`, loaded into `server.settings.ServerSettings`:

| Variable                               | Default                                                     |
|----------------------------------------|-------------------------------------------------------------|
| `ACADEMIC_PIPELINE_REDIS_URL`                | `redis://localhost:6379`                                    |
| `ACADEMIC_PIPELINE_REDIS_BROKER_DB`          | `0`                                                         |
| `ACADEMIC_PIPELINE_REDIS_RESULT_DB`          | `1`                                                         |
| `ACADEMIC_PIPELINE_REDIS_APP_DB`             | `2`                                                         |
| `ACADEMIC_PIPELINE_REDIS_KEY_PREFIX`         | `academic_pipeline`                                         |
| `ACADEMIC_PIPELINE_DATA_DIR`                 | `<project_root>/server/data`                                |
| `ACADEMIC_PIPELINE_MAX_UPLOAD_BYTES`         | `524288000` (500 MiB)                                       |
| `ACADEMIC_PIPELINE_CELERY_RESULT_EXPIRES`    | `86400` (1 day)                                             |
| `ACADEMIC_PIPELINE_WORKER_SHUTDOWN_TIMEOUT`  | `60`                                                        |
| `ACADEMIC_PIPELINE_LOG_LEVEL`                | `INFO`                                                      |
| `ACADEMIC_PIPELINE_CORS_ORIGINS`             | `["http://localhost:5173"]`                                 |

## Render deployment (not yet deployed)

The repository-root `render.yaml` describes the target Render
Blueprint. Four services are declared:

- `nocode-workflow-api` — Docker web service, runs
  `uvicorn server.app:create_app --factory`.
- `nocode-workflow-celery-worker` — Docker worker service, runs
  `celery -A server.celery_app worker --pool=solo --concurrency=1`.
- `nocode-workflow-redis` — managed Redis for broker, result backend,
  application state, and the SSE pubsub channel.
- `nocode-workflow-gui` — static site built from `gui/` (Vite).

`render.yaml` is **committed but not deployed**. Before running
`render deploy`:

1. Set `OPENROUTER_API_KEY`, `ACADEMIC_PIPELINE_CORS_ORIGINS`, and
   `VITE_API_BASE_URL` in Render's dashboard (they are marked
   `sync: false` in the blueprint so the deploy script never
   overwrites them).
2. Confirm the `nocode-workflow-redis` plan is appropriate for the
   workload; the blueprint defaults to the free tier.
3. The blueprint mounts a 1 GiB persistent disk at
   `/app/server/data`. Uploaded CSVs and run artefacts live there;
   increase `disk.sizeGB` in `render.yaml` if runs become larger.
4. Run `render blueprint deploy` (or deploy each service from the UI)
   only after running `scripts/smoke_test_backend.py` locally against
   the same container image tag.

The `Dockerfile` at `server/Dockerfile` is intentionally generic so
the web and worker services can share one image and differ only in
their `dockerCommand`.

## Running the full test suite

`scripts/test_all.ps1` (PowerShell) and `scripts/test_all.sh` (bash)
at the repository root run a seven-stage, fail-fast pipeline: the
script stops at the first non-zero exit code and does not execute any
later stage. Stage 2 is opt-in via `-Integration` (PowerShell) or
`--integration` (bash); without the flag that stage is skipped and
the remaining six stages still run.

Stages (each banner matches the form `Stage N / 7: <name>`):

- **Stage 1 / 7: Python backend unit + route tests** —
  `pytest server/tests/unit server/tests/routes src/tests`. Runs the
  in-process FastAPI and Celery unit tests plus the shared `src/`
  tests; needs neither Redis nor a running container.
- **Stage 2 / 7: Python backend integration tests** (opt-in) —
  `pytest server/tests/integration -m integration`. Exercises the
  web container, the Celery worker, and Redis end to end through
  HTTP and SSE.
- **Stage 3 / 7: getState() ban grep check** — asserts no
  `getState(` token appears under `gui/tests/rtl/` or
  `gui/tests/e2e/`. See the corresponding section in `gui/README.md`
  for the frontend-side rationale.
- **Stage 4 / 7: Vitest data-layer tier** — `npm run test:data`
  (covers `gui/tests/data/`).
- **Stage 5 / 7: Vitest RTL tier** — `npm run test:rtl`
  (covers `gui/tests/rtl/`).
- **Stage 6 / 7: Vitest contract tier** — `npm run test:contract`
  (covers `gui/tests/contract/`).
- **Stage 7 / 7: Playwright e2e** — `npm run e2e` (from `gui/`,
  expanding to `playwright test`), driven by
  `gui/playwright.config.ts` and the specs under `gui/tests/e2e/`.

### Integration-marker gotcha

The `integration` marker is declared in `pytest.ini` and attached via
`pytestmark` to every test file under `server/tests/integration/`.
The marker selects which tests run; it does **not** bring the docker
compose stack up. Stage 2 therefore expects
`docker compose up -d --wait` at the repository root to have already
succeeded. Without that, the integration tests cannot reach the web
container or Redis and fail at fixture setup.

Stage 7 (Playwright) does **not** share this gotcha: its
`globalSetup` hook at `gui/tests/e2e/global_setup.ts` runs
`docker compose up -d --wait` itself before the first spec. Stage 2
deliberately does not duplicate that behaviour — running the pytest
integration tier is meant to be a conscious choice on an already-up
stack.

### Prerequisites

- A project `.venv` at the repository root.
- `pip install -r server/requirements.txt -r requirements-test.txt`
  into that `.venv`, so both the runtime dependencies and the pytest
  toolchain are resolvable.
- `npm ci` in `gui/`, so stages 4–7 can resolve their JavaScript
  dependencies.
- `docker compose up -d --wait` at the repository root before
  invoking the runner with `-Integration`/`--integration`, and
  reachable (though not necessarily pre-started) when Stage 7 runs.

### Example invocations

Fast tier — stages 1 and 3–7, integration skipped:

```powershell
./scripts/test_all.ps1
```

```bash
./scripts/test_all.sh
```

Full tier — all seven stages including integration:

```powershell
./scripts/test_all.ps1 -Integration
```

```bash
./scripts/test_all.sh --integration
```

The full pipeline also runs the GUI tiers (stages 3–7); see the
corresponding section in `gui/README.md` for the frontend-side
description of those stages.
