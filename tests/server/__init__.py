"""Tests for the :mod:`server` package.

Layout:

- :mod:`tests.server.unit` — fast, no-Docker tests against services
  wired with :class:`fastapi.testclient.TestClient` + fakeredis + respx.
- :mod:`tests.server.routes` — route-level tests covering every
  declared endpoint, also using :class:`TestClient`.
- :mod:`tests.server.integration` — real-stack tests that require
  ``docker compose up`` plus an OpenRouter key. Marked with the
  ``integration`` pytest marker and skipped by default.
"""
