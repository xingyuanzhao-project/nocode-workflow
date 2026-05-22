# agent_paper GUI

React Flow graph editor, flow manager, and run viewer for the
`agent_paper` backend. The GUI speaks only HTTP / SSE to the backend
that lives under `server/`; there is no direct filesystem access from
the browser.

## Prerequisites

- Node.js 20+ (tested on 22.x).
- A running backend (`docker compose up --build` at the repository
  root is the recommended local setup).

## Local development

```bash
cd gui
npm ci
npm run dev
```

The dev server starts on `http://127.0.0.1:5173`. Vite proxies
`/api/**` and `/openapi.json` to `http://127.0.0.1:8000` (the FastAPI
web container), so browser-side URLs stay path-relative.

Override the proxy target with the `VITE_API_PROXY_TARGET` env var
when running against a remote backend:

```bash
VITE_API_PROXY_TARGET=http://some-host:8000 npm run dev
```

## Production build

```bash
npm run build
```

Produces a static bundle under `gui/dist/`. On Render this is served
as a static site (see the repository-root `render.yaml`).

At runtime the static bundle uses `VITE_API_BASE_URL` (baked at build
time) to reach the backend. For local previews, leave it empty so the
built site uses path-relative URLs and works behind any reverse
proxy; set it to a full URL when the GUI and the backend live on
different origins.

## Scripts

- `npm run dev` — Vite dev server with HMR + backend proxy.
- `npm run build` — TypeScript project build plus Vite static build.
- `npm run lint` — Type-check only (no emit).
- `npm test` — Vitest fast tier (`cross-env VITEST_SCOPE=fast vitest run`).
- `npm run test:data` — Vitest data-layer tier (`tests/data/`).
- `npm run test:rtl` — Vitest RTL tier (`tests/rtl/`).
- `npm run test:contract` — Vitest contract tier (`tests/contract/`).
- `npm run test:all` — All Vitest tiers in one run.
- `npm run e2e:install` — One-time Playwright browser download.
- `npm run e2e` — Playwright end-to-end tests.

## Folder layout

Each folder owns one responsibility:

```
gui/
├── src/
│   ├── api/               # Typed HTTP/SSE client (one file per backend tag)
│   ├── schemas/           # Zod mirrors of every server DTO
│   ├── stores/            # Zustand stores (graph, flow metadata, run)
│   ├── hooks/             # React hooks (TanStack Query + SSE)
│   ├── components/        # Generic UI widgets (NavBar, dialogs, toasts, ui/ primitives)
│   ├── flow_editor/       # Canvas + palette + property panel
│   │   ├── canvas/
│   │   ├── palette/
│   │   ├── nodes/
│   │   ├── edges/
│   │   └── property_panel/
│   ├── serialisation/     # Graph <-> FlowConfig codec + YAML IO
│   ├── pages/             # Route components (flows, runs, taxonomies, settings)
│   ├── lib/               # Cross-cutting helpers (cn, unit compatibility)
│   └── styles/            # globals.css and any other static stylesheets
├── tests/
│   ├── data/              # Vitest data-layer tier (codec, zod mirrors, unit compat)
│   ├── rtl/               # Vitest React-Testing-Library tier (DOM assertions only)
│   ├── contract/          # Vitest OpenAPI-compatibility tier
│   └── e2e/               # Playwright end-to-end specs (live stack)
└── dist/                  # Production build output (git-ignored)
```

## Running the full test suite

`scripts/test_all.ps1` (PowerShell) and `scripts/test_all.sh` (bash)
at the repository root run a seven-stage, fail-fast pipeline: the
script stops at the first non-zero exit code and does not execute any
later stage. Stage 2 is opt-in via `-Integration` (PowerShell) or
`--integration` (bash); without the flag that stage is skipped and
the remaining six stages still run.

Stages (each banner matches the form `Stage N / 7: <name>`):

- **Stage 1 / 7: Python backend unit + route tests** —
  `pytest server/tests/unit server/tests/routes src/tests`.
- **Stage 2 / 7: Python backend integration tests** (opt-in) —
  `pytest server/tests/integration -m integration`. Requires the
  docker compose stack at the repository root to already be up; see
  the corresponding section in `server/README.md`.
- **Stage 3 / 7: getState() ban grep check** — asserts no
  `getState(` token appears under `gui/tests/rtl/` or
  `gui/tests/e2e/`. A React Testing Library or Playwright test that
  reaches into a Zustand store through `useStore.getState()` reads
  state outside the render cycle, so it can pass even when the
  component under test is not actually subscribed to the store.
  Tests in those directories must assert on the DOM the component
  rendered, matching the RTL helpers' contract that "Zustand stores
  are reset before each render so tests observe only the DOM their
  component produced" (`gui/tests/rtl/_helpers.tsx`).
- **Stage 4 / 7: Vitest data-layer tier** — `npm run test:data`
  (expands to `cross-env VITEST_SCOPE=data vitest run`). Covers the
  pure data layer under `gui/tests/data/`: zod mirrors of server
  DTOs, the YAML codec, unit-compatibility rules, and codec
  round-trip.
- **Stage 5 / 7: Vitest RTL tier** — `npm run test:rtl`
  (expands to `cross-env VITEST_SCOPE=rtl vitest run`). Covers the
  React Testing Library specs under `gui/tests/rtl/`: node
  renderers, property-panel tabs, and shared components.
- **Stage 6 / 7: Vitest contract tier** — `npm run test:contract`
  (expands to `cross-env VITEST_SCOPE=contract vitest run`). Covers
  `gui/tests/contract/` — the OpenAPI-compatibility test that guards
  the TypeScript client against backend schema drift.
- **Stage 7 / 7: Playwright e2e** — `npm run e2e` (expands to
  `playwright test`), driven by `gui/playwright.config.ts`. The
  `globalSetup` hook in
  `gui/tests/e2e/global_setup.ts` runs `docker compose up -d --wait`
  at the repository root before the first spec, so this tier starts
  the backend stack on its own.

### Prerequisites

- `npm ci` in `gui/` so Vitest, React Testing Library, and Playwright
  are installed. Stages 3–7 all need `gui/node_modules/`.
- `npx playwright install --with-deps chromium` (one-time, exposed as
  `npm run e2e:install`) so the Playwright browser binary is present
  for Stage 7.
- A project `.venv` at the repository root with
  `pip install -r server/requirements.txt -r requirements-test.txt`,
  because the same runner also drives Stages 1 and 2.
- `docker compose up -d --wait` reachable at the repository root.
  Stage 7 brings the stack up itself; Stage 2 does not and requires
  the stack to already be up before the runner is invoked.

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

The full pipeline also runs the backend tiers (stages 1 and 2); see
the corresponding section in `server/README.md` for the backend-side
description, including the pytest `integration`-marker gotcha.
