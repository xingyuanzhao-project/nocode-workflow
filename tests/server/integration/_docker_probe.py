"""Shared probe used by every file under :mod:`server.tests.integration`.

Exposes :func:`require_running_stack` which skips the calling test
module when ``docker compose ps`` does not show the three services
up. Keeps the integration suite opt-in and prevents confusing
``ConnectionRefused`` failures when a developer forgets to start the
stack.
"""

from __future__ import annotations

import os
import subprocess
from typing import Set

import pytest


_REQUIRED_SERVICES: Set[str] = {"web", "celery_worker", "redis"}


def require_running_stack() -> None:
    """Skip the calling module when the docker compose stack is not up.

    Also skips when ``AGENT_PAPER_SKIP_INTEGRATION=1`` is set in the
    environment so CI can opt out uniformly without needing the marker
    syntax.

    Returns:
        None. Raises :class:`pytest.skip.Exception` via ``pytest.skip``.
    """
    if os.environ.get("AGENT_PAPER_SKIP_INTEGRATION", "").strip() == "1":
        pytest.skip("AGENT_PAPER_SKIP_INTEGRATION=1 set; skipping.")
    try:
        completed = subprocess.run(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("docker command not available on PATH.")
    if completed.returncode != 0:
        pytest.skip(f"docker compose ps returned {completed.returncode}: {completed.stderr}")
    running_services = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    missing = _REQUIRED_SERVICES - running_services
    if missing:
        pytest.skip(
            f"docker compose services not running: {sorted(missing)}. "
            "Run `docker compose up --build -d` first."
        )
