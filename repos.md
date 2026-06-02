---
note: |
  When referring to repository names or URLs that are not explicitly known or described, consult this file (`repos.md`)
  as the single source of truth for all repository references in this project.

# Repository registry for nocode-workflow: all repository roles, locations, and relationships are documented below.
---

# End Generation Here
```


# Repository Map

## Three surfaces, one product

```
nocode-workflow (private)          ← source of truth, this workspace
    │
    ├─── deployed to Render.com
    │        nocode-workflow-api.onrender.com   (FastAPI + Celery, Docker)
    │        nocode-workflow-gui.onrender.com   (Vite/React SPA, static)
    │
    └─── deployed to HuggingFace Spaces
             huggingface.co/spaces/xingyuanzhao/nocode-workflow  (Docker)

nocode-workflow-public (public)    ← README-only mirror, no source code
    └─── user-facing docs, citation block, quick-start guide
```

---

## nocode-workflow (private)

**URL:** https://github.com/xingyuanzhao-project/nocode-workflow  
**Visibility:** Private  
**Role:** Full source code. All development happens here.

Contains `server/`, `gui/`, `src/`, `tests/`, `scripts/`, `codebooks/`, `workflows/`, `render.yaml`, `docker-compose.yml`, etc. Deployed automatically to Render.com via `render.yaml` (three services: API + Redis + GUI). Also the source image pushed to the HuggingFace Space.

---

## nocode-workflow-public (public)

**URL:** https://github.com/xingyuanzhao-project/nocode-workflow-public  
**Visibility:** Public  
**Role:** Public documentation face. No application source code.

Contains only `README.md`. Serves as the citable, indexable GitHub URL for the project — used in the `@software` citation block, linked from the HuggingFace Space, and referenced in any public-facing material. Source code is intentionally absent.

---

## HuggingFace Space — nocode-workflow

**URL:** https://huggingface.co/spaces/xingyuanzhao/nocode-workflow  
**Visibility:** Public  
**Role:** Live deployment of the app (Docker runtime, currently Running).

A second production deployment alongside Render. Hosts the full No-Code Workflow app built from the private repo's Docker image. Provides a persistent public demo URL under the `huggingface.co` domain.

---

## Summary table

| Surface | Visibility | Contains | Purpose |
|---|---|---|---|
| `xingyuanzhao-project/nocode-workflow` | Private | Full source | Development, CI, deployment source |
| `xingyuanzhao-project/nocode-workflow-public` | Public | README only | Citation, public documentation |
| `xingyuanzhao/nocode-workflow` (HF Space) | Public | Running app | Live demo deployment |
