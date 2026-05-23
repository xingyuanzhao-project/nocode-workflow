"""Unified test suite for the academic_pipeline project.

Layout:

- :mod:`tests.server` — tests for the ``server`` package (routes, unit,
  integration).
- :mod:`tests.src` — pure-Python tests for the ``src`` package (flow
  loader, node registry, io schema, prompt resolver, flow builder).
- :mod:`tests.scripts` — standalone smoke-test scripts that exercise the
  real backend and real LLM endpoints.
- :mod:`tests.fixtures` — on-disk fixtures (YAML, CSV, JSON) shared
  across suites.
"""
