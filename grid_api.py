"""Local AG-UI API for GRID desktop and Android clients.

The transport is HTTP + Server-Sent Events. Events follow the AG-UI 1.0
event contract; the client receives a normal run stream with text, tool calls,
activity and custom artifact events.

Security:
  * loopback-only by default;
  * every request needs ``Authorization: Bearer <token>``;
  * the token lives in ``run/api_token`` (gitignored);
  * dangerous tools ask through a per-run approval request.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from grid_permissions import PermissionPolicy

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "run"
REFS_REA = HERE / "refs" / "rea"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("GRID_API_PORT", "8771"))
DEFAULT_TOKEN_FILE = RUN_DIR / "api_token"
DEFAULT_THREAD_FILE = RUN_DIR / "api_threads.json"
PROTOCOL_VERSION = "1.0"
MAX_BODY_BYTES = 2_000_000
MAX_REPORT_BYTES = 2_000_000
APPROVAL_TIMEOUT_SECONDS = 300
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _runtime():
    """Resolve the module that owns the live Tools instance.

    ``grid_agent.py`` runs as ``__main__``, while imports of ``grid_agent``
    create a second module with its own context variables. The API must use the
    running module or tool events and policy overrides go nowhere.
    """
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "Tools") and hasattr(main, "set_event_sink"):
        return main
    import grid_agent
    return grid_agent


def _path(value: Optional[str], default: Path) -> Path:
    if not value:
        return default
    candidate = Path(str(value)).expanduser()
    if not candidate.is_absolute():
        candidate = HERE / candidate
    return candidate


def ensure_token(path: Optional[Path] = None) -> str:
    override = os.environ.get("GRID_API_TOKEN")
    if override:
        return override
    target = Path(path) if path else DEFAULT_TOKEN_FILE
    try:
        if target.exists():
            token = target.read_text(encoding="utf-8").strip()
            if token:
                return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return token


class ThreadStore:
    """Small JSON thread store for reconnects; message history is client-owned."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_THREAD_FILE
        self._lock = threading.Lock()
        self._threads: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("threads"), dict):
                self._threads = data["threads"]
        except (OSError, json.JSONDecodeError):
            self._threads = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps({"threads": self._threads}, indent=2),
                encoding="utf-8",
            )
            temp.replace(self.path)
        except OSError:
            pass

    def summaries(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = [
                {
                    "id": thread_id,
                    "title": item.get("title", ""),
                    "updated_at": item.get("updated_at", ""),
                    "message_count": len(item.get("messages") or []),
                }
                for thread_id, item in self._threads.items()
            ]
        rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        return rows

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._threads.get(thread_id)
            return json.loads(json.dumps(item)) if item else None

    def put(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        title = ""
        for message in messages:
            if message.get("role") == "user" and message.get("content"):
                title = str(message["content"]).strip().splitlines()[0][:120]
                break
        with self._lock:
            self._threads[thread_id] = {
                "id": thread_id,
                "created_at": self._threads.get(thread_id, {}).get("created_at") or _now(),
                "updated_at": _now(),
                "title": title,
                "messages": messages,
            }
            self._save()


class SSEStream:
    """Thread-safe SSE writer with a keep-alive comment."""

    def __init__(self, wfile):
        self.wfile = wfile
        self._lock = threading.Lock()
        self._closed = False
        self._stop = threading.Event()
        self._heartbeat = threading.Thread(
            target=self._keepalive, name="grid-api-sse-heartbeat", daemon=True
        )
        self._heartbeat.start()

    def _write(self, text: str) -> bool:
        if self._closed:
            return False
        try:
            with self._lock:
                self.wfile.write(text.encode("utf-8"))
                self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._closed = True
            return False

    def _keepalive(self) -> None:
        while not self._stop.wait(10):
            if not self._write(": ping\n\n"):
                return

    def send(self, event: Dict[str, Any]) -> bool:
        payload = dict(event)
        payload.setdefault("timestamp", int(time.time() * 1000))
        raw = json.dumps(payload, ensure_ascii=False)
        return self._write(f"data: {raw}\n\n")

    def close(self) -> None:
        self._stop.set()
        self._closed = True


class _QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that ignores clients disappearing mid-stream."""

    def handle_error(self, request, client_address):
        import sys

        error = sys.exc_info()[1]
        if isinstance(error, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class GridAPIServer:
    """AG-UI HTTP server bound to loopback by default."""

    def __init__(
        self,
        orchestrator,
        config: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        thread_store: Optional[ThreadStore] = None,
        refs_dir: Optional[Path] = None,
    ):
        self.orchestrator = orchestrator
        self.config = config or {}
        self.runtime = _runtime()
        self.token = token or ensure_token()
        self.host = host
        self.port = int(port)
        self.threads = thread_store or ThreadStore()
        self.refs_dir = Path(refs_dir) if refs_dir else REFS_REA
        self._httpd = None
        self._thread = None
        self._approvals_lock = threading.Lock()
        self._approvals: Dict[str, Dict[str, Any]] = {}

    # ── handlers ─────────────────────────────────────────────

    def _payload(self) -> Dict[str, Any]:
        backend = getattr(self.orchestrator, "backend", None)
        return {
            "ok": True,
            "name": "GRID API",
            "pid": os.getpid(),
            "protocol": PROTOCOL_VERSION,
            "model": getattr(backend, "model", ""),
            "backend": getattr(backend, "type", ""),
            "threads": len(self.threads.summaries()),
            "rea_reports": len(self._rea_reports()),
        }

    def _rea_reports(self) -> List[Dict[str, Any]]:
        rows = []
        if not self.refs_dir.exists():
            return rows
        for manifest_path in sorted(self.refs_dir.glob("*/manifest.json")):
            directory = manifest_path.parent
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append(
                {
                    "id": directory.name,
                    "target": manifest.get("target", ""),
                    "host": manifest.get("host", ""),
                    "generated_at": manifest.get("generated_at", ""),
                    "backend": manifest.get("backend", ""),
                    "authorization": manifest.get("authorization", ""),
                    "counts": manifest.get("counts") or {},
                    "report_path": str(directory / "report.md"),
                    "screenshot_path": (
                        str(directory / "screenshot.png")
                        if (directory / "screenshot.png").exists()
                        else ""
                    ),
                }
            )
        rows.sort(key=lambda row: row.get("generated_at", ""), reverse=True)
        return rows

    def _rea_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        if not ID_RE.match(report_id or ""):
            return None
        directory = self.refs_dir / report_id
        if not directory.is_dir():
            return None
        try:
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        report_path = directory / "report.md"
        try:
            report = report_path.read_text(encoding="utf-8")[:MAX_REPORT_BYTES]
        except OSError:
            report = ""
        return {
            "id": report_id,
            "manifest": manifest,
            "report": report,
            "report_path": str(report_path),
            "screenshot_path": (
                str(directory / "screenshot.png")
                if (directory / "screenshot.png").exists()
                else ""
            ),
        }

    def _approval_callback(self, stream: SSEStream):
        def ask(tool_name: str, tool_input: str, risk: str) -> str:
            approval_id = f"apr_{uuid.uuid4().hex[:12]}"
            waiter = threading.Event()
            with self._approvals_lock:
                self._approvals[approval_id] = {
                    "event": waiter,
                    "decision": "",
                    "created": time.time(),
                }
            stream.send(
                {
                    "type": "CUSTOM",
                    "name": "grid.approval_required",
                    "value": {
                        "approvalId": approval_id,
                        "tool": tool_name,
                        "input": tool_input[:2000],
                        "risk": risk,
                    },
                }
            )
            approved = waiter.wait(timeout=APPROVAL_TIMEOUT_SECONDS)
            with self._approvals_lock:
                record = self._approvals.pop(approval_id, {})
            return "yes" if approved and record.get("decision") == "approve" else "no"

        return ask

    def _handle_run(self, body: Dict[str, Any], handler: "BaseHTTPRequestHandler") -> None:
        messages = body.get("messages")
        if not isinstance(messages, list):
            self._json(handler, 400, {"ok": False, "error": "messages must be a list"})
            return
        prompt = ""
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                prompt = content.strip()
            elif isinstance(content, list):
                prompt = "\n".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()
            if prompt:
                break
        if not prompt:
            self._json(handler, 400, {"ok": False, "error": "a user message is required"})
            return

        thread_id = str(body.get("threadId") or f"thr_{uuid.uuid4().hex[:16]}")
        run_id = str(body.get("runId") or f"run_{uuid.uuid4().hex[:16]}")
        if not ID_RE.match(thread_id) or not ID_RE.match(run_id):
            self._json(handler, 400, {"ok": False, "error": "invalid threadId or runId"})
            return

        handler.close_connection = True
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

        stream = SSEStream(handler.wfile)
        message_id = f"msg_{uuid.uuid4().hex[:16]}"
        step_name = "agent"
        policy = PermissionPolicy(
            (self.config.get("permissions") or {}),
            approval_callback=self._approval_callback(stream),
        )
        assistant_text = ""
        try:
            stream.send(
                {
                    "type": "RUN_STARTED",
                    "threadId": thread_id,
                    "runId": run_id,
                    "protocolVersion": PROTOCOL_VERSION,
                }
            )
            stream.send({"type": "STEP_STARTED", "stepName": step_name})
            self.runtime.set_event_sink(stream.send)
            self.runtime.set_policy_override(policy)
            assistant_text = self.orchestrator.process(prompt, stream=True) or ""
            if not isinstance(assistant_text, str):
                assistant_text = str(assistant_text)
            stream.send(
                {
                    "type": "TEXT_MESSAGE_START",
                    "messageId": message_id,
                    "role": "assistant",
                }
            )
            stream.send(
                {
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": message_id,
                    "delta": assistant_text,
                }
            )
            stream.send({"type": "TEXT_MESSAGE_END", "messageId": message_id})
            stream.send({"type": "STEP_FINISHED", "stepName": step_name})
            stream.send(
                {
                    "type": "RUN_FINISHED",
                    "threadId": thread_id,
                    "runId": run_id,
                    "outcome": {"type": "success"},
                }
            )
            stored = [
                {
                    "id": str(message.get("id") or f"msg_{uuid.uuid4().hex[:12]}"),
                    "role": str(message.get("role") or "user"),
                    "content": message.get("content") or "",
                }
                for message in messages
                if isinstance(message, dict) and message.get("role") in {"user", "assistant"}
            ]
            stored.append(
                {"id": message_id, "role": "assistant", "content": assistant_text}
            )
            self.threads.put(thread_id, stored)
        except Exception as exc:
            stream.send({"type": "STEP_FINISHED", "stepName": step_name})
            stream.send(
                {
                    "type": "RUN_ERROR",
                    "message": f"{type(exc).__name__}: {exc}",
                    "code": "grid_run_failed",
                }
            )
        finally:
            self.runtime.set_event_sink(None)
            self.runtime.set_policy_override(None)
            stream.close()

    def _handle_approval(self, approval_id: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"approve", "deny"}:
            return 400, {"ok": False, "error": "decision must be approve or deny"}
        with self._approvals_lock:
            record = self._approvals.get(approval_id)
            if record is None:
                return 404, {"ok": False, "error": "approval not found"}
            record["decision"] = decision
            record["event"].set()
        return 200, {"ok": True, "approvalId": approval_id, "decision": decision}

    # ── HTTP plumbing ────────────────────────────────────────

    @staticmethod
    def _json(handler: "BaseHTTPRequestHandler", code: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except OSError:
            pass

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GRIDAPI/1.0"
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                if not header.startswith("Bearer "):
                    return False
                return hmac.compare_digest(header[7:].strip(), server.token)

            def _read_json(self) -> Dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return {}
                if length <= 0 or length > MAX_BODY_BYTES:
                    return {}
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, json.JSONDecodeError):
                    return {}
                return payload if isinstance(payload, dict) else {}

            def do_GET(self):
                if not self._authorized():
                    server._json(self, 401, {"ok": False, "error": "unauthorized"})
                    return
                path = urlparse(self.path).path.rstrip("/")
                if path == "/api/v1/health":
                    server._json(self, 200, server._payload())
                elif path == "/api/v1/threads":
                    server._json(self, 200, {"ok": True, "threads": server.threads.summaries()})
                elif path.startswith("/api/v1/threads/"):
                    thread_id = unquote(path[len("/api/v1/threads/"):])
                    thread = server.threads.get(thread_id)
                    if thread is None:
                        server._json(self, 404, {"ok": False, "error": "thread not found"})
                    else:
                        server._json(self, 200, {"ok": True, "thread": thread})
                elif path == "/api/v1/rea/reports":
                    server._json(self, 200, {"ok": True, "reports": server._rea_reports()})
                elif path.startswith("/api/v1/rea/reports/"):
                    rest = unquote(path[len("/api/v1/rea/reports/"):])
                    if rest.endswith("/screenshot"):
                        report_id = rest[: -len("/screenshot")]
                        report = server._rea_report(report_id)
                        screenshot = (
                            server.refs_dir / report_id / "screenshot.png"
                            if report
                            else None
                        )
                        if not screenshot or not screenshot.exists():
                            server._json(self, 404, {"ok": False, "error": "screenshot not found"})
                            return
                        raw = screenshot.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(len(raw)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        try:
                            self.wfile.write(raw)
                        except OSError:
                            pass
                        return
                    report = server._rea_report(rest)
                    if report is None:
                        server._json(self, 404, {"ok": False, "error": "report not found"})
                    else:
                        server._json(self, 200, {"ok": True, "report": report})
                else:
                    server._json(self, 404, {"ok": False, "error": "not found"})

            def do_POST(self):
                if not self._authorized():
                    server._json(self, 401, {"ok": False, "error": "unauthorized"})
                    return
                path = urlparse(self.path).path.rstrip("/")
                if path == "/api/v1/agent":
                    body = self._read_json()
                    if not body:
                        server._json(self, 400, {"ok": False, "error": "invalid JSON body"})
                        return
                    server._handle_run(body, self)
                    return
                if path.startswith("/api/v1/approvals/"):
                    approval_id = unquote(path[len("/api/v1/approvals/"):])
                    code, payload = server._handle_approval(approval_id, self._read_json())
                    server._json(self, code, payload)
                    return
                if path == "/api/v1/agent/resume":
                    server._json(
                        self,
                        501,
                        {
                            "ok": False,
                            "error": "resume is handled by the approval endpoint in this build",
                        },
                    )
                    return
                server._json(self, 404, {"ok": False, "error": "not found"})

        return Handler

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        try:
            self._httpd = _QuietHTTPServer((self.host, self.port), self._handler())
        except OSError:
            self._httpd = None
            return False
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="grid-api-http", daemon=True
        )
        self._thread.start()
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


def run_api(orchestrator, console, config: Optional[Dict[str, Any]] = None, tools=None) -> int:
    cfg = (config or {}).get("api") or {}
    host = str(cfg.get("host") or DEFAULT_HOST)
    try:
        port = int(cfg.get("port") or DEFAULT_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    token_file = _path(cfg.get("token_file"), DEFAULT_TOKEN_FILE)
    thread_file = _path(cfg.get("threads_file"), DEFAULT_THREAD_FILE)
    token = ensure_token(token_file)
    server = GridAPIServer(
        orchestrator,
        config=config or {},
        token=token,
        host=host,
        port=port,
        thread_store=ThreadStore(thread_file),
    )
    if not server.start():
        console.print(f"  [red]Could not bind GRID API to {host}:{port}.[/]")
        return 1
    console.print(
        f"  GRID API listening on [bold]http://{host}:{server.port}/api/v1[/]\n"
        f"  AG-UI protocol {PROTOCOL_VERSION}; token file: [dim]{token_file}[/]"
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0
