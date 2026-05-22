"""Domain services for the server package.

Every module under :mod:`server.services` holds domain logic and nothing
else. Services never touch FastAPI request/response types and never
apply Celery decorators. They own one specific responsibility each:

- :mod:`server.services.node_catalog` — wraps :mod:`src.node_registry`.
- :mod:`server.services.flow_validation` — wraps
  :class:`src.flow_loader.FlowSchema`.
- :mod:`server.services.flow_repository` — CRUD over flow YAMLs on
  disk.
- :mod:`server.services.taxonomy_repository` — CRUD over taxonomy
  JSONs on disk.
- :mod:`server.services.csv_uploader` — accepts user-uploaded CSVs and
  inspects their columns.
- :mod:`server.services.results_preview` — reads run output artifacts
  for the GUI preview and download endpoints.
- :mod:`server.services.template_repository` — read-only repository of
  preset flow templates bundled with the application.
- :mod:`server.services.prompts_repository` — read-only view of
  ``config/prompts.json`` served to the GUI.
- :mod:`server.services.model_list_proxy` — OpenRouter / OpenAI
  model-list proxy with Redis-backed cache.
- :mod:`server.services.log_stream` — subscribes to the worker's
  Redis pubsub log channel and yields SSE events for the GUI's
  live log viewer.
- :mod:`server.services.run_registry` — Redis-backed run status store.
- :mod:`server.services.run_dispatcher` — writes per-run flow YAMLs
  and enqueues the Celery task.

The hard abstraction rule: only :mod:`server.services.node_catalog`,
:mod:`server.services.flow_validation`, and
:mod:`server.workers.flow_task` are allowed to import from ``src.*``.
"""
