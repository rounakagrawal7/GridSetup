"""Always-on GRID Life resident.

One process owns ``grid_data.duckdb`` at a time. When the interactive app
starts, it asks the resident to hand the database over; when the app exits it
can relaunch the resident. The control surface is loopback-only HTTP.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
DEFAULT_PORT = int(os.environ.get("GRID_RESIDENT_PORT", "8770"))
M = "#00FF00"
_LOG_HANDLE = None


def info_path() -> Path:
    override = os.environ.get("GRID_RESIDENT_INFO")
    if override:
        return Path(override)
    return HERE / "run" / "resident.json"


def log_path() -> Path:
    directory = HERE / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"resident-{datetime.now():%Y%m%d}.log"


def redirect_output():
    """Point stdout/stderr at the resident log (pythonw has no console)."""
    global _LOG_HANDLE
    path = log_path()
    _LOG_HANDLE = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _LOG_HANDLE
    sys.stderr = _LOG_HANDLE
    return path


def make_logger(path: Optional[Path] = None) -> Callable[[str], None]:
    target = Path(path) if path else log_path()

    def _log(text: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp}  {text}"
        try:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line.rstrip() + "\n")
        except OSError:
            pass

    return _log


def read_info() -> Dict[str, Any]:
    path = info_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_info(payload: Dict[str, Any]) -> None:
    path = info_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload), encoding="utf-8")
    temp.replace(path)


def _remove_info(port: Optional[int] = None) -> None:
    data = read_info()
    if port is not None and data.get("port") not in (None, port):
        return
    try:
        info_path().unlink()
    except OSError:
        pass


def _base_url(port: Optional[int] = None) -> Optional[str]:
    data = read_info()
    chosen = port or data.get("port")
    if not chosen:
        return None
    return f"http://127.0.0.1:{int(chosen)}"


def _request(url: str, method: str = "GET", timeout: float = 1.0) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw else {}
        return payload if isinstance(payload, dict) else {}
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def is_resident_alive(timeout: float = 0.6) -> bool:
    base = _base_url()
    if not base:
        return False
    health = _request(f"{base}/health", timeout=timeout)
    return bool(health and health.get("ok"))


def request_handoff(
    timeout: float = 45.0,
    on_wait: Optional[Callable[[float], None]] = None,
) -> bool:
    """Ask the resident to close its database and exit.

    Returns True when the resident is gone (or was never running).
    """
    base = _base_url()
    if not base:
        return True
    if not is_resident_alive():
        _remove_info()
        return True

    _request(f"{base}/handoff", method="POST", timeout=3.0)
    started = time.time()
    while time.time() - started < timeout:
        if not is_resident_alive(timeout=0.4):
            _remove_info()
            return True
        if on_wait:
            try:
                on_wait(time.time() - started)
            except Exception:
                pass
        time.sleep(0.5)
    return False


def request_pause(paused: bool, timeout: float = 2.0) -> bool:
    base = _base_url()
    if not base or not is_resident_alive():
        return False
    path = "/pause" if paused else "/resume"
    return _request(f"{base}{path}", method="POST", timeout=timeout) is not None


def _pythonw() -> str:
    candidate = HERE / ".venv" / "Scripts" / "pythonw.exe"
    if candidate.exists():
        return str(candidate)
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        sibling = executable.with_name("pythonw.exe")
        if sibling.exists():
            return str(sibling)
    return str(executable)


def launch_detached() -> bool:
    """Start the resident without a console, unless one is already alive."""
    if is_resident_alive():
        return False
    command = [
        _pythonw(),
        str(HERE / "grid_agent.py"),
        "--no-input",
        "--no-banner",
        "--resident",
    ]
    kwargs: Dict[str, Any] = {
        "cwd": str(HERE),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
    try:
        subprocess.Popen(command, **kwargs)
        return True
    except Exception:
        return False


class ResidentServer:
    """Loopback control surface for the resident process."""

    def __init__(
        self,
        life,
        orchestrator=None,
        stop_event: Optional[threading.Event] = None,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
    ):
        self.life = life
        self.orchestrator = orchestrator
        self.stop_event = stop_event or threading.Event()
        self.host = host
        self.port = port
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self._httpd = None
        self._thread = None

    def _payload(self) -> Dict[str, Any]:
        backend = getattr(self.orchestrator, "backend", None)
        ident = {}
        try:
            ident = self.life.identity()
        except Exception:
            pass
        return {
            "ok": True,
            "pid": os.getpid(),
            "name": ident.get("name") or "GRID",
            "model": getattr(backend, "model", ""),
            "backend": getattr(backend, "type", ""),
            "started_at": self.started_at,
            "port": self.port,
        }

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GRIDResident/1.0"

            def log_message(self, *_args):
                return

            def _json(self, code: int, payload: Dict[str, Any]) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass

            def do_GET(self):
                if self.path == "/health":
                    self._json(200, server._payload())
                elif self.path == "/status":
                    try:
                        text = server.life.status_text()
                    except Exception as exc:
                        text = f"status unavailable: {exc}"
                    self._json(200, {"ok": True, "text": text})
                else:
                    self._json(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                if self.path == "/handoff":
                    server.stop_event.set()
                    self._json(200, {"ok": True, "handoff": True})
                elif self.path == "/pause":
                    server.life.set_paused(True)
                    self._json(200, {"ok": True, "paused": True})
                elif self.path == "/resume":
                    server.life.set_paused(False)
                    self._json(200, {"ok": True, "paused": False})
                else:
                    self._json(404, {"ok": False, "error": "not found"})

        return Handler

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        try:
            self._httpd = ThreadingHTTPServer(
                (self.host, self.port), self._handler()
            )
        except OSError:
            self._httpd = None
            return False
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="grid-resident-http",
            daemon=True,
        )
        self._thread.start()
        payload = self._payload()
        _write_info(payload)
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        _remove_info(self.port)


def _resolve_tools():
    main = sys.modules.get("__main__")
    candidate = getattr(main, "Tools", None)
    if candidate is not None:
        return candidate
    from grid_agent import Tools
    return Tools


def ensure_db_available(console, timeout: float = 120.0) -> bool:
    """Hand the database back from the resident before the app opens it."""
    if not is_resident_alive():
        return True

    from rich.panel import Panel

    console.print(Panel(
        "GRID Life is resident and owns the local database right now.\n"
        "Asking it to finish its current thought and hand over...",
        title=f"[bold {M}]GRID Life[/]",
        border_style=M,
        padding=(0, 1),
    ))
    announced = {"at": 0.0}

    def _progress(elapsed: float) -> None:
        if elapsed - announced["at"] >= 5:
            announced["at"] = elapsed
            console.print(f"  Waiting for the resident ({elapsed:.0f}s)...")

    if request_handoff(timeout=timeout, on_wait=_progress):
        console.print("  Resident handed over. Opening the interactive session.")
        return True

    console.print(
        "  The resident is still finishing a blocking tool call.\n"
        "  Wait a moment and start GRID again, or stop it from Task Manager."
    )
    return False


def run_resident(
    orchestrator,
    console,
    config: Optional[Dict[str, Any]] = None,
    tools=None,
) -> int:
    """Run the headless life loop until a handoff or shutdown."""
    from grid_awake import ResidentAutopilot

    Tools = tools or _resolve_tools()
    if Tools.life is None:
        console.print("GRID Life needs DuckDB. Run: pip install duckdb")
        return 1

    life_cfg = getattr(Tools.life, "cfg", {}) or {}
    if not life_cfg.get("enabled", True):
        console.print("GRID Life is disabled (life.enabled=false).")
        return 0

    stop_event = threading.Event()
    server = ResidentServer(
        Tools.life,
        orchestrator,
        stop_event=stop_event,
        port=DEFAULT_PORT,
    )
    logger = make_logger()

    if not server.start():
        if is_resident_alive():
            logger("another resident is already alive; exiting")
            return 0
        logger(f"could not bind 127.0.0.1:{DEFAULT_PORT}; exiting")
        return 1

    logger(
        f"resident started on 127.0.0.1:{server.port} "
        f"as {(Tools.life.identity() or {}).get('name', 'GRID')}"
    )
    try:
        Tools.life.record_event("resident", "Resident awake")
    except Exception:
        pass

    permissions = (config or {}).get("permissions") or {}
    runner = ResidentAutopilot(
        Tools.life,
        orchestrator,
        console,
        permissions=permissions,
        stop_event=stop_event,
        log=logger,
        tools=Tools,
    )

    reason = "stopped"
    try:
        runner.run()
        reason = "handoff" if stop_event.is_set() else "stopped"
    except KeyboardInterrupt:
        stop_event.set()
        reason = "keyboard interrupt"
    except Exception as exc:
        reason = f"error: {exc}"
        logger(f"resident error: {exc}")
    finally:
        try:
            Tools.life.record_event("resident", f"Resident asleep ({reason})")
        except Exception:
            pass
        # Release the database before the health endpoint disappears, so the
        # interactive app cannot race the resident for the file lock.
        db = getattr(Tools, "db", None)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
            Tools.db = None
        server.stop()
        logger(f"resident stopped ({reason})")
    return 0
