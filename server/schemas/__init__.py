"""HTTP-facing Pydantic DTOs for the server package.

Every module in :mod:`server.schemas` contains only request and
response models used by the FastAPI routes. The DTOs are deliberately
kept separate from :mod:`src.flow_loader` and
:mod:`src.node_registry` so HTTP-only fields never leak into the
domain models.

Module layout
-------------

- :mod:`server.schemas.node_types` — node-type catalog response shapes.
- :mod:`server.schemas.flow` — flow validation, CRUD, and run request
  shapes.
- :mod:`server.schemas.taxonomy` — taxonomy CRUD shapes.
- :mod:`server.schemas.run` — run status enum and response shapes.
- :mod:`server.schemas.results` — run output artifact preview shapes.
- :mod:`server.schemas.templates` — preset flow-template shapes.
- :mod:`server.schemas.prompts` — prompts-registry response shape.
- :mod:`server.schemas.models` — provider model-list proxy shapes.
- :mod:`server.schemas.files` — CSV upload shapes.
- :mod:`server.schemas.health` — health-check response shape.
- :mod:`server.schemas.errors` — error-response envelope used by
  :mod:`server.errors`.
"""
