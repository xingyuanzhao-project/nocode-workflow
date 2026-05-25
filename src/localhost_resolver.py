"""Derive a reachable IP-address URL from a user-entered localhost URL.

The user types a localhost-form URL (e.g. ``http://localhost:9000/v1``)
in the Settings page.  At runtime the backend may be in a different
network namespace than the model server.  This module detects the
topology and derives the reachable URL by replacing only the host
component, preserving scheme, port, and path.

Topology detection is deterministic and ordered (first match wins):

1. **Inside Docker container** — ``/.dockerenv`` exists.
   Derived host: ``host.docker.internal``

2. **Inside WSL2** — ``/proc/version`` contains ``microsoft`` (case-
   insensitive).
   Derived host: the ``nameserver`` entry in ``/etc/resolv.conf``,
   which is the Windows host IP visible from WSL2.

3. **On Windows, model in WSL2** — ``platform.system() == "Windows"``
   and ``wsl hostname -I`` returns an IP, and ``localhost:<port>`` is
   not reachable via TCP.
   Derived host: the first IP from ``wsl hostname -I``.

4. **Same network namespace** — none of the above matched.
   No derivation; localhost is already correct.

Every consumer (settings test, model-list proxy, flow-builder runtime)
calls :func:`resolve_localhost_url` so the derivation is uniform.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def resolve_localhost_url(url: str) -> str:
    """Replace the host in *url* with a reachable address if needed.

    If the host is not ``localhost`` or ``127.0.0.1``, the URL is
    returned unchanged (the user already provided a routable address).

    Args:
        url: User-entered OpenAI-compatible base URL, e.g.
            ``http://localhost:9000/v1``.

    Returns:
        The same URL with scheme/port/path preserved and host replaced
        by the topology-derived reachable address.  When no rewrite is
        needed, the original URL is returned unchanged.
    """
    parsed = urlparse(url)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        return url

    reachable_host = _derive_reachable_host(parsed.port)
    if reachable_host is None:
        return url

    if parsed.port:
        new_netloc = f"{reachable_host}:{parsed.port}"
    else:
        new_netloc = reachable_host

    return urlunparse(parsed._replace(netloc=new_netloc))


# ────────────────────────────────────────────────────────────────────
# Topology detection — ordered, first match wins
# ────────────────────────────────────────────────────────────────────

def _derive_reachable_host(port: int | None) -> str | None:
    """Return the reachable host for the current topology, or None."""

    if _is_inside_docker():
        return "host.docker.internal"

    if _is_inside_wsl2():
        return _wsl2_windows_host_ip()

    if platform.system() == "Windows" and port is not None:
        if not _tcp_reachable("localhost", port):
            wsl_ip = _windows_wsl2_guest_ip()
            if wsl_ip is not None:
                return wsl_ip

    return None


# ────────────────────────────────────────────────────────────────────
# Individual topology probes
# ────────────────────────────────────────────────────────────────────

def _is_inside_docker() -> bool:
    """True when the current process runs inside a Docker container."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace")
        if "docker" in cgroup or "containerd" in cgroup:
            return True
    except OSError:
        pass
    return False


def _is_inside_wsl2() -> bool:
    """True when the current process runs inside a WSL2 guest."""
    try:
        version_info = Path("/proc/version").read_text(
            encoding="utf-8", errors="replace"
        )
        return "microsoft" in version_info.lower()
    except OSError:
        return False


def _wsl2_windows_host_ip() -> str | None:
    """Return the Windows host IP as seen from inside WSL2.

    WSL2 populates ``/etc/resolv.conf`` with a ``nameserver`` line
    pointing at the Windows host bridge IP.
    """
    try:
        for line in Path("/etc/resolv.conf").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            stripped = line.strip()
            if stripped.startswith("nameserver"):
                parts = stripped.split()
                if len(parts) >= 2:
                    return parts[1]
    except OSError:
        pass
    return None


def _windows_wsl2_guest_ip() -> str | None:
    """Return the WSL2 guest IPv4 address from the Windows host.

    Runs ``wsl hostname -I`` and returns the first token (the guest's
    primary IPv4 address).  Returns None if WSL2 is not installed or
    the command fails.
    """
    try:
        result = subprocess.run(
            ["wsl", "hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            ip = result.stdout.strip().split()[0]
            if ip:
                return ip
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    return None


def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """True if a TCP connection to *host:port* succeeds within *timeout*."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
