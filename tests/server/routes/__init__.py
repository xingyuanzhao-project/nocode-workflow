"""Route-level tests using :class:`fastapi.testclient.TestClient`.

One file per router. Asserts on response bodies, status codes, and
response headers. The tests use the ``test_client`` fixture from
:mod:`tests.conftest` which wires fakeredis + eager Celery
under the hood.
"""
