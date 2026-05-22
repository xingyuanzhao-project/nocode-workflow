"""HTTP routers for the server package.

Each module under :mod:`server.routes` owns one URL prefix and one
topic. Route handlers are thin: they parse request bodies into
:mod:`server.schemas` DTOs, delegate to the matching
:mod:`server.services` service, and return the service's response DTO.

Module layout
-------------

- :mod:`server.routes.schema` — ``/api/schema/*`` (node catalog, flow
  validation).
- :mod:`server.routes.flow` — ``/api/flow/*`` (CRUD and runs).
- :mod:`server.routes.results` — ``/api/flow/runs/{id}/preview`` and
  ``/api/flow/runs/{id}/artifacts/{name}`` (output artifacts).
- :mod:`server.routes.templates` — ``/api/flow/templates`` (preset
  flow templates).
- :mod:`server.routes.prompts` — ``/api/prompts`` (read-only prompts
  registry).
- :mod:`server.routes.models` — ``/api/models/{provider}`` (provider
  model-list proxy with Redis-backed cache).
- :mod:`server.routes.logs` — ``/api/flow/runs/{id}/logs/stream``
  (Server-Sent Events relay of a run's live log stream).
- :mod:`server.routes.taxonomy` — ``/api/taxonomy/*``.
- :mod:`server.routes.files` — ``/api/files/*``.
- :mod:`server.routes.health` — ``/api/health``.
"""
