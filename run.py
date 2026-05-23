"""Click *Run Python File* to start the full app (backend + frontend + browser).

Uses only stdlib so it works under any Python interpreter the IDE selects.
The backend is launched with the project .venv interpreter; the frontend
is launched with node directly (bypassing npm/vite .cmd wrappers).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
REDIS_PORT = 6379


def _venv_python() -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    name = "python.exe" if os.name == "nt" else "python"
    return REPO_ROOT / ".venv" / scripts / name


def _vite_js() -> Path:
    return REPO_ROOT / "gui" / "node_modules" / "vite" / "bin" / "vite.js"


def _redis_server_exe() -> Path:
    return REPO_ROOT / "tools" / "redis" / "redis-server.exe"


def _preflight() -> tuple[str, Path, str]:
    """Verify all prerequisites exist and return their paths."""
    errors: list[str] = []

    venv_py = _venv_python()
    if not venv_py.exists():
        errors.append(
            ".venv not found — create it with:\n"
            "  python -m venv .venv\n"
            "  .venv\\Scripts\\pip install -r requirements.txt"
            " -r server/requirements.txt"
        )

    vite_js = _vite_js()
    if not vite_js.exists():
        errors.append("vite not installed — run:\n  cd gui && npm install")

    node = shutil.which("node")
    if node is None:
        errors.append("node not found on PATH")

    redis_exe = _redis_server_exe()
    if not redis_exe.exists():
        errors.append(
            f"redis-server not found at {redis_exe}\n"
            "  Download from https://github.com/tporadowski/redis/releases\n"
            "  and extract to tools/redis/"
        )

    if errors:
        sys.exit("ERROR:\n" + "\n".join(errors))

    return str(venv_py), vite_js, node  # type: ignore[return-value]


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port (Windows only)."""
    import re as _re
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], text=True, creationflags=0x08000000,
        )
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                if pid > 0:
                    subprocess.call(
                        ["taskkill", "/F", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print(f"  Killed PID {pid} on port {port}", flush=True)
    except Exception:
        pass


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    """Block until *localhost:port* accepts a TCP connection."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def main() -> None:
    venv_py, vite_js, node = _preflight()

    print("Checking for existing processes on ports ...", flush=True)
    _kill_port(REDIS_PORT)
    _kill_port(BACKEND_PORT)
    _kill_port(FRONTEND_PORT)
    time.sleep(0.5)

    procs: list[subprocess.Popen] = []

    print("Starting Redis    (redis   :6379) ...", flush=True)
    redis_proc = subprocess.Popen(
        [
            str(_redis_server_exe()),
            "--port", str(REDIS_PORT),
            "--save", "",
            "--appendonly", "no",
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(redis_proc)

    if not _wait_for_port(REDIS_PORT, timeout=10.0):
        sys.exit("ERROR: Redis did not start within 10 s.")
    print("  Redis is ready.", flush=True)

    print("Starting Celery   (worker  :solo) ...", flush=True)
    celery_proc = subprocess.Popen(
        [
            venv_py, "-m", "celery",
            "-A", "server.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=INFO",
        ],
        cwd=str(REPO_ROOT),
    )
    procs.append(celery_proc)

    print("Starting backend  (uvicorn :8000) ...", flush=True)
    backend = subprocess.Popen(
        [
            venv_py, "-m", "uvicorn", "server.app:create_app",
            "--factory", "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
        ],
        cwd=str(REPO_ROOT),
    )
    procs.append(backend)

    print("Starting frontend (vite    :5173) ...", flush=True)
    frontend = subprocess.Popen(
        [node, str(vite_js)],
        cwd=str(REPO_ROOT / "gui"),
    )
    procs.append(frontend)

    print("Waiting for frontend to be ready ...", flush=True)
    if _wait_for_port(FRONTEND_PORT):
        url = f"http://127.0.0.1:{FRONTEND_PORT}/"
        print(f"Opening {url}", flush=True)
        webbrowser.open(url)
    else:
        print("Frontend did not respond in 20 s — check the output above.",
              flush=True)

    print(flush=True)
    print(f"  App running at  http://127.0.0.1:{FRONTEND_PORT}/", flush=True)
    print(f"  API running at  http://127.0.0.1:{BACKEND_PORT}/", flush=True)
    print(f"  Redis running at         :{REDIS_PORT}", flush=True)
    print("  Press Ctrl+C to stop.", flush=True)
    print(flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down ...", flush=True)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()


if __name__ == "__main__":
    main()
