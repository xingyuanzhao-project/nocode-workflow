"""Real-stack integration tests.

Every test in this package talks to the live FastAPI container at
``http://127.0.0.1:8000`` (default) and the live Celery + Redis
services. Marked with the ``integration`` pytest marker so they do
not run by default.

Invocation::

    docker compose up --build -d
    pytest -m integration

Each test that actually fires a run uses ``google/gemini-2.5-flash``
with ``processing_limit=1`` so cost stays under a cent per full
suite run.
"""
