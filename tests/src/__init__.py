"""Unit tests for the :mod:`src` package.

These tests are pure Python: no FastAPI, no Redis, no Celery, no
Docker. They exercise the Pydantic validators declared in
:mod:`src.flow_loader`, the node-type registry in
:mod:`src.node_registry`, the I/O schema conversion in
:mod:`src.io_schema`, the prompt resolver in
:mod:`src.prompt_resolver`, and the dispatcher wiring in
:mod:`src.flow_builder`.
"""
