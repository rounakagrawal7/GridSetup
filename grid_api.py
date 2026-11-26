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

PROVIDERS = (
    {
        "id": "ollama",
        "name": "Ollama",
        "description": "Local models on this machine",
        "default_url": "http://localhost:11434",
        "needs_key": False,
        "package": "ollama",
    },
    {
        "id": "lm_studio",
        "name": "LM Studio",
        "description": "Local OpenAI-compatible server",
        "default_url": "http://localhost:1234/v1",
        "needs_key": False,
        "package": "openai",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "description": "Cloud models via openrouter.ai",
        "default_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "package": "openai",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI or OpenAI-compatible API",
        "default_url": "https://api.openai.com/v1",
        "needs_key": True,
        "package": "openai",
    },
)


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
                    "message_count": len(
                        [
                            message
                            for message in (item.get("messages") or [])
                            if message.get("role") in {"user", "assistant"}
                        ]
                    ),
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

    def clear(self) -> int:
        """Delete saved threads only; memory and persona live elsewhere."""
        with self._lock:
            count = len(self._threads)
            self._threads = {}
            self._save()
            return count


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
        self.shutdown_event = threading.Event()

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
            "runtime": getattr(self.runtime, "__name__", ""),
        }

    def _model_info(self) -> Dict[str, Any]:
        backend = getattr(self.orchestrator, "backend", None)
        model = getattr(backend, "model", "")
        backend_type = getattr(backend, "type", "")
        models: List[str] = []
        try:
            fetcher = getattr(backend, "fetch_models", None)
            if callable(fetcher):
                models = list(
                    fetcher(backend_type, getattr(backend, "base_url", "")) or []
                )
        except Exception:
            models = []
        return {
            "ok": True,
            "model": model,
            "backend": backend_type,
            "models": models,
        }

    def _provider_info(self) -> Dict[str, Any]:
        backend = getattr(self.orchestrator, "backend", None)
        loader = getattr(self.runtime, "load_config", None)
        cfg: Dict[str, Any] = {}
        if callable(loader):
            try:
                cfg = loader()
            except Exception:
                cfg = {}
        rows = []
        for provider in PROVIDERS:
            row = {key: value for key, value in provider.items() if key != "package"}
            package = provider["package"]
            flag = "HAS_OLLAMA" if package == "ollama" else "HAS_OPENAI"
            row["available"] = bool(getattr(self.runtime, flag, False))
            if provider["id"] == "openrouter":
                row["key_set"] = bool(cfg.get("openrouter_api_key"))
            elif provider["id"] == "openai":
                row["key_set"] = bool(cfg.get("openai_api_key"))
            else:
                row["key_set"] = True
            rows.append(row)
        return {
            "ok": True,
            "provider": getattr(backend, "type", ""),
            "model": getattr(backend, "model", ""),
            "base_url": getattr(backend, "base_url", ""),
            "providers": rows,
        }

    def _provider_models(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        provider = str(body.get("provider") or "").strip().lower()
        info = next((row for row in PROVIDERS if row["id"] == provider), None)
        if info is None:
            return 400, {"ok": False, "error": f"unknown provider: {provider}"}
        flag = "HAS_OLLAMA" if info["package"] == "ollama" else "HAS_OPENAI"
        if not bool(getattr(self.runtime, flag, False)):
            return 400, {
                "ok": False,
                "error": f"{info['name']} needs the '{info['package']}' package",
            }
        base_url = str(body.get("base_url") or info["default_url"]).rstrip("/")
        api_key = str(body.get("api_key") or "").strip()
        loader = getattr(self.runtime, "load_config", None)
        cfg = loader() if callable(loader) else {}
        key_name = {
            "openrouter": "openrouter_api_key",
            "openai": "openai_api_key",
        }.get(provider, "")
        if key_name and not api_key and not cfg.get(key_name):
            return 400, {
                "ok": False,
                "error": f"{info['name']} API key is required",
            }
        if key_name and api_key:
            save = getattr(self.runtime, "save_config", None)
            if callable(save):
                try:
                    save({key_name: api_key})
                except Exception:
                    pass
        backend_cls = getattr(self.runtime, "LLMBackend", None)
        if backend_cls is None:
            return 500, {"ok": False, "error": "LLM backend is unavailable"}
        key = api_key or (cfg.get(key_name, "") if key_name else "lm-studio")
        try:
            if provider == "ollama":
                models = list(backend_cls.fetch_models(provider, base_url) or [])
            else:
                openai_cls = getattr(self.runtime, "OpenAI", None)
                if openai_cls is None:
                    return 400, {
                        "ok": False,
                        "error": "the 'openai' package is not installed",
                    }
                client = openai_cls(base_url=base_url, api_key=key)
                models = [model.id for model in client.models.list()]
        except Exception as exc:
            detail = str(exc)
            if key and len(key) > 8:
                detail = detail.replace(key, "***")
            return 502, {
                "ok": False,
                "error": f"{info['name']} model list failed: {detail}",
            }
        return 200, {
            "ok": True,
            "provider": provider,
            "base_url": base_url,
            "models": models,
        }

    def _set_provider(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        provider = str(body.get("provider") or "").strip().lower()
        info = next((row for row in PROVIDERS if row["id"] == provider), None)
        if info is None:
            return 400, {"ok": False, "error": f"unknown provider: {provider}"}
        flag = "HAS_OLLAMA" if info["package"] == "ollama" else "HAS_OPENAI"
        if not bool(getattr(self.runtime, flag, False)):
            return 400, {
                "ok": False,
                "error": f"{info['name']} needs the '{info['package']}' package",
            }
        model = str(body.get("model") or "").strip()
        if not model:
            return 400, {"ok": False, "error": "model is required"}
        base_url = str(body.get("base_url") or info["default_url"]).rstrip("/")
        api_key = str(body.get("api_key") or "").strip()
        loader = getattr(self.runtime, "load_config", None)
        cfg = loader() if callable(loader) else {}
        key_name = {
            "openrouter": "openrouter_api_key",
            "openai": "openai_api_key",
        }.get(provider, "")
        key_update: Dict[str, Any] = {}
        if key_name:
            if api_key:
                key_update[key_name] = api_key
            elif not cfg.get(key_name):
                return 400, {
                    "ok": False,
                    "error": f"{info['name']} API key is required",
                }
        save = getattr(self.runtime, "save_config", None)
        if key_update and callable(save):
            try:
                save(key_update)
            except Exception:
                pass
        backend_cls = getattr(self.runtime, "LLMBackend", None)
        if backend_cls is None:
            return 500, {"ok": False, "error": "LLM backend is unavailable"}
        try:
            backend = backend_cls(provider, model, base_url)
        except SystemExit:
            return 400, {"ok": False, "error": f"could not initialize {info['name']}"}
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not initialize provider: {exc}"}
        self.orchestrator.backend = backend
        recaller = getattr(self.orchestrator, "recaller", None)
        if recaller is not None:
            try:
                recaller.backend = backend
            except Exception:
                pass
        updates: Dict[str, Any] = {
            "backend_type": provider,
            "base_url": base_url,
            "model": model,
        }
        updates.update(key_update)
        if callable(save):
            try:
                save(updates)
            except Exception:
                pass
        return 200, {
            "ok": True,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "message": f"Switched to {info['name']} · {model}",
        }

    def _set_model(self, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        model = str(body.get("model") or "").strip()
        if not model:
            return 400, {"ok": False, "error": "model is required"}
        backend = getattr(self.orchestrator, "backend", None)
        if backend is None:
            return 503, {"ok": False, "error": "no backend is active"}
        try:
            backend.model = model
        except Exception as exc:
            return 500, {"ok": False, "error": f"could not switch model: {exc}"}
        save = getattr(self.runtime, "save_config", None)
        if callable(save):
            try:
                save({"model": model})
            except Exception:
                pass
        return 200, {"ok": True, "model": model, "backend": getattr(backend, "type", "")}

    def _tools_info(self) -> Dict[str, Any]:
        tools = getattr(self.runtime, "Tools", None)
        registry = getattr(tools, "registry", {}) if tools is not None else {}
        enabled = getattr(tools, "enabled", set()) if tools is not None else set()
        rows = [
            {
                "name": name,
                "description": str(info.get("desc") or ""),
                "enabled": name in enabled,
            }
            for name, info in registry.items()
        ]
        rows.sort(key=lambda row: row["name"])
        return {"ok": True, "count": len(rows), "tools": rows}

    # -- terminal-style local commands ---------------------------------
    #
    # The desktop composer exposes the same shortcuts as the terminal. These
    # handlers return plain text so the client can render them as a note
    # without parsing Rich markup.

    def _cmd_memory(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        recaller = getattr(tools, "recaller", None) if tools is not None else None
        if recaller is None:
            return "Memory layer not active (needs duckdb). Run: pip install duckdb"
        sub = args.strip()
        low = sub.lower()
        if low in ("", "status", "show"):
            return (
                f"{tools._memory_status()}\n\n"
                "Tip: /memory <query> recalls; /memory add <fact> teaches it; "
                "/memory profile shows the user profile."
            )
        if low in ("profile", "user", "about"):
            return recaller.profile_text()
        if low.startswith("add "):
            return recaller.remember(sub[4:].strip())
        if low.startswith("forget "):
            return recaller.forget(sub[7:].strip())
        if low in ("build-profile", "build profile", "backfill", "learn"):
            added = recaller.backfill_profile()
            return f"Profile updated: {added} new fact(s).\n\n{recaller.profile_text()}"
        if low in ("clear-profile", "reset-profile"):
            return recaller.clear_profile()
        if low in ("clear", "reset"):
            recaller.db.clear_memory()
            return "Layered memory cleared (profile untouched)."
        return f"{tools._memory_status()}\n\n{tools._memory_recall(sub)}"

    def _cmd_life(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        life = getattr(tools, "life", None) if tools is not None else None
        if life is None:
            return "GRID Life needs DuckDB. Run: pip install duckdb"
        body = args.strip()
        if not body:
            return (
                f"{life.status_text()}\n\n"
                "Desktop: /life status|help|log|goals|goal|commitments|commitment|"
                "pause|resume|identity|tick. Live autopilot loops stay in the terminal."
            )
        parts = body.split(maxsplit=2)
        sub = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if sub in ("status", "show"):
            return life.status_text()
        if sub == "help":
            return (
                "GRID autopilot\n"
                "  /life              status\n"
                "  /life status       current state\n"
                "  /life log [n]      recent activity\n"
                "  /life goals        active goals\n"
                "  /life goal add <title> | /life goal done <id>\n"
                "  /life commitments  open commitments\n"
                "  /life commitment add <text> | /life commitment done <id>\n"
                "  /life pause|resume stop or resume autonomous work\n"
                "  /life identity     persona and identity\n"
                "  /life tick         run one autonomous cycle\n"
                "Live autopilot loops are interactive and stay in the terminal."
            )
        if sub == "log":
            limit = int(arg) if arg.isdigit() else 20
            return life.log_text(limit)
        if sub == "goals":
            return life.goals_text()
        if sub == "goal":
            action, _, rest = arg.partition(" ")
            if action == "add" and rest.strip():
                title = rest.strip()
                goal_type = "once"
                if title.lower().startswith("ongoing "):
                    goal_type = "ongoing"
                    title = title[8:].strip()
                return life.add_goal(title, goal_type=goal_type)
            if action == "done" and rest.strip():
                return life.complete_goal(rest.strip())
            return "Usage: /life goal add <title> | /life goal done <id>"
        if sub == "commitments":
            return life.commitments_text()
        if sub == "commitment":
            action, _, rest = arg.partition(" ")
            if action == "add" and rest.strip():
                return life.add_commitment(rest.strip())
            if action == "done" and rest.strip():
                return life.complete_commitment(rest.strip())
            return "Usage: /life commitment add <description> | /life commitment done <id>"
        if sub == "pause":
            return life.set_paused(True)
        if sub == "resume":
            return life.set_paused(False)
        if sub == "identity":
            return life.identity_text()
        if sub in ("tick", "wake"):
            result = life.tick(manual=True)
            text = result.get("summary", "Tick complete.")
            if result.get("detail"):
                text += "\n" + result["detail"]
            for message in life.pending_messages():
                text += "\n\n" + (message.get("detail") or message.get("summary") or "")
                life.mark_delivered(message["id"])
            return text
        if sub == "awake":
            return (
                "Awake runs are interactive. Use /life tick for one autonomous "
                "cycle, or run /life awake <task> in the terminal client."
            )
        return (
            "Usage: /life [status|help|log|goals|goal|commitments|commitment|"
            "pause|resume|identity|tick]"
        )

    def _cmd_plan(self, _args: str) -> str:
        current = bool(getattr(self.orchestrator, "plan_mode", False))
        self.orchestrator.plan_mode = not current
        return f"Planner mode {'enabled' if self.orchestrator.plan_mode else 'disabled'}."

    def _cmd_ref(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        recaller = getattr(tools, "recaller", None) if tools is not None else None
        if recaller is None:
            return "Memory layer not active."
        ref_id = args.strip()
        if not ref_id:
            return "Usage: /ref <id> — read an offloaded tool output."
        return recaller.read_ref(ref_id)

    def _cmd_jobs(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        manager = getattr(tools, "skills", None) if tools is not None else None
        if manager is None:
            return "Skill system not initialized."
        sub = args.strip()
        if not sub or sub == "list":
            skills = manager.list_skills()
            if not skills:
                return "No skills defined yet."
            lines = [f"Skills ({len(skills)}):"]
            for skill in skills:
                status = "enabled" if skill.get("enabled") else "disabled"
                lines.append(
                    f"  {str(skill.get('name', '')).ljust(20)} "
                    f"{status.ljust(8)} {skill.get('description', '')}"
                )
            return "\n".join(lines)
        if sub.startswith("show "):
            name = sub.split(maxsplit=1)[1].strip().lower().replace(" ", "_")
            info = manager.skills.get(name)
            if not info:
                return f"Skill '{name}' not found."
            code = manager.get_code(name) or ""
            lines = [
                f"Skill: {name}",
                f"Description: {info.get('description', '')}",
                f"Input:       {info.get('input_desc', '')}",
                f"Status:      {'enabled' if info.get('enabled', True) else 'disabled'}",
            ]
            if info.get("schema"):
                lines.append(f"Schema:      {json.dumps(info['schema'], indent=2)}")
            if code:
                lines.append("Code:")
                lines.extend(f"  {line}" for line in code.splitlines())
            return "\n".join(lines)
        if sub.startswith("toggle "):
            name = sub.split(maxsplit=1)[1].strip().lower().replace(" ", "_")
            return manager.toggle(name)
        return (
            "Desktop supports /jobs list, /jobs show <name> and /jobs toggle <name>. "
            "Create, edit and delete skills in the terminal client."
        )

    def _cmd_pb(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        pb = getattr(tools, "pb", None) if tools is not None else None
        if pb is None:
            return "PocketBase not initialized. Check the pocketbase-client install."
        sub = args.strip().lower()
        if not sub or sub == "status":
            return pb.status_text()
        if sub == "start":
            return "PocketBase started." if pb.start() else "Failed to start PocketBase."
        if sub == "stop":
            pb.stop()
            return "PocketBase stopped."
        if sub in ("install", "download"):
            if pb.download():
                return "PocketBase downloaded. Run /pb start to launch it."
            return "PocketBase download failed. Try manually from https://pocketbase.io"
        if sub == "sync":
            if not getattr(pb, "token", None):
                return "PocketBase not connected. Start it first with /pb start."
            memory = getattr(tools, "memory_ref", None)
            if memory is None:
                return "Memory not available."
            pb.sync_memory(memory.history, "grid")
            return "Memory synced to PocketBase."
        return "Usage: /pb [status|start|stop|install|sync]"

    def _cmd_persona(self, args: str) -> str:
        from grid_agent_social import moltbook_social

        sub = args.strip()
        result = moltbook_social(f"persona {sub}".strip())
        tools = getattr(self.runtime, "Tools", None)
        life = getattr(tools, "life", None) if tools is not None else None
        if life is not None:
            low = sub.lower()
            if low.startswith("set ") and "error:" not in result.lower():
                life.adopt_persona(sub[4:].strip())
            elif low == "clear":
                life.clear_persona()
        return result

    def _cmd_social(self, args: str) -> str:
        from grid_agent_social import moltbook_social

        return moltbook_social(args.strip() or "help")

    def _cmd_comms(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        if tools is None or not hasattr(tools, "_comms"):
            return "Communication tools are unavailable."
        return str(tools._comms(args.strip()))

    def _cmd_ctf(self, args: str) -> str:
        from grid_ctf import ctf_main

        return ctf_main(args.strip() or "help")

    def _cmd_game(self, args: str) -> str:
        from grid_game import game_main

        return str(game_main(args.strip() or "help"))

    def _cmd_gcal(self, args: str) -> str:
        from grid_google import google_calendar

        return google_calendar(args.strip() or "help")

    def _cmd_gsheet(self, args: str) -> str:
        from grid_sheets import google_sheets

        return google_sheets(args.strip() or "help")

    def _cmd_save(self, _args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        memory = getattr(tools, "memory_ref", None) if tools is not None else None
        if memory is None:
            return "Conversation memory unavailable."
        memory.save()
        name = getattr(self.runtime, "MEMORY_FILE", "memory.json")
        message = f"Memory saved to '{name}'."
        pb = getattr(tools, "pb", None) if tools is not None else None
        if pb is not None and getattr(pb, "token", None):
            try:
                pb.sync_memory(memory.history, "grid")
                message += " Synced to PocketBase."
            except Exception as exc:
                message += f" PocketBase sync failed: {exc}"
        return message

    def _shutdown_host(self) -> Tuple[int, Dict[str, Any]]:
        try:
            message = self._cmd_save("")
        except Exception as exc:
            message = f"Memory save failed: {exc}"
        setattr(self.runtime, "EXPLICIT_SHUTDOWN", True)
        return 200, {
            "ok": True,
            "message": f"{message} GRID host is shutting down.",
            "saved": not message.startswith("Memory save failed"),
        }

    def _cmd_export(self, args: str) -> str:
        tools = getattr(self.runtime, "Tools", None)
        memory = getattr(tools, "memory_ref", None) if tools is not None else None
        if memory is None:
            return "Conversation memory unavailable."
        export = getattr(self.runtime, "export_history", None)
        if not callable(export):
            return "Export is unavailable in this runtime."
        fmt = (args.strip() or "txt").split()[0].lower()
        return str(export(memory, fmt))

    def _cmd_model(self, _args: str) -> str:
        info = self._model_info()
        return (
            f"Active model: {info.get('model') or '(unknown)'}\n"
            f"Available: {', '.join(info.get('models') or []) or '(none detected)'}\n"
            "Use Change model in the desktop sidebar to switch."
        )

    def _cmd_tools(self, _args: str) -> str:
        info = self._tools_info()
        lines = [f"GRID tools ({info['count']}):"]
        lines.extend(
            f"  {row['name'].ljust(22)} = {row['description']}"
            for row in info["tools"]
        )
        return "\n".join(lines)

    def _cmd_help(self, _args: str) -> str:
        return (
            "Local commands:\n"
            "  /help              = this list\n"
            "  /new, /clear       = client-side thread controls\n"
            "  /model             = active model and available models\n"
            "  /tokens            = session token and timing stats\n"
            "  /tools             = list every GRID tool\n"
            "  /tool <name> <in>  = run a tool through the agent\n"
            "  /rea authorized <url> = authorized passive teardown\n"
            "  /memory ...        = recall, add, profile, backfill\n"
            "  /life ...          = status, goals, commitments, tick\n"
            "  /plan              = toggle planner mode\n"
            "  /ref <id>          = read an offloaded tool output\n"
            "  /jobs ...          = list/show/toggle dynamic skills\n"
            "  /persona ...       = view or set GRID persona\n"
            "  /social ...        = Moltbook social platform\n"
            "  /pb ...            = PocketBase status/start/stop/sync\n"
            "  /export [fmt]      = export server chat history\n"
            "  /save              = save server conversation memory\n"
            "  /comms ...         = communication tools reference\n"
            "  /ctf ...           = local CTF sandbox\n"
            "  /game ...          = game worlds\n"
            "  /gcal ...          = Google Calendar\n"
            "  /gsheet ...        = Google Sheets + Excel\n"
            "Type / to autocomplete; ↑↓ select, Tab complete."
        )

    def _local_command(self, raw: str) -> Tuple[int, Dict[str, Any]]:
        command = str(raw or "").strip()
        if not command.startswith("/"):
            return 400, {"ok": False, "error": "command must start with /"}
        name, _, args = command.partition(" ")
        name = name.lower()
        handlers = {
            "/help": self._cmd_help,
            "/memory": self._cmd_memory,
            "/life": self._cmd_life,
            "/plan": self._cmd_plan,
            "/ref": self._cmd_ref,
            "/jobs": self._cmd_jobs,
            "/pb": self._cmd_pb,
            "/persona": self._cmd_persona,
            "/social": self._cmd_social,
            "/comms": self._cmd_comms,
            "/ctf": self._cmd_ctf,
            "/game": self._cmd_game,
            "/gcal": self._cmd_gcal,
            "/gsheet": self._cmd_gsheet,
            "/save": self._cmd_save,
            "/export": self._cmd_export,
            "/model": self._cmd_model,
            "/tools": self._cmd_tools,
        }
        handler = handlers.get(name)
        if handler is None:
            return 400, {"ok": False, "error": f"unknown local command: {name}"}
        try:
            output = handler(args)
        except Exception as exc:
            return 500, {"ok": False, "error": f"{name} failed: {exc}"}
        if not isinstance(output, str):
            output = str(output)
        return 200, {"ok": True, "command": name, "output": output}

    def _clear_threads(self) -> Dict[str, Any]:
        cleared = self.threads.clear()
        return {
            "ok": True,
            "cleared": cleared,
            "message": f"Cleared {cleared} saved thread(s). Memory, profile and persona were not changed.",
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
            self._audit(f"ask {approval_id} {tool_name} {risk}")
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
            decision = "yes" if approved and record.get("decision") == "approve" else "no"
            self._audit(f"result {approval_id} {decision} timeout={not approved}")
            return decision

        return ask

    @staticmethod
    def _audit(message: str) -> None:
        try:
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            with open(RUN_DIR / "api_approvals.log", "a", encoding="utf-8") as handle:
                handle.write(f"{_now()} {message}\n")
        except OSError:
            pass

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
        tool_results: List[str] = []
        tool_calls: Dict[str, Dict[str, Any]] = {}
        tool_order: List[str] = []
        started_at = time.time()
        backend = getattr(self.orchestrator, "backend", None)
        if hasattr(backend, "reset_usage"):
            try:
                backend.reset_usage()
            except Exception:
                pass

        def sink(event: Dict[str, Any]) -> None:
            kind = event.get("type")
            call_id = str(event.get("toolCallId") or "")
            if kind == "TOOL_CALL_START" and call_id:
                tool_calls[call_id] = {
                    "id": call_id,
                    "role": "tool",
                    "name": str(event.get("toolCallName") or ""),
                    "args": "",
                    "content": "",
                }
                tool_order.append(call_id)
            elif kind == "TOOL_CALL_ARGS" and call_id in tool_calls:
                delta = str(event.get("delta") or "")
                try:
                    parsed = json.loads(delta)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = None
                if isinstance(parsed, dict) and "input" in parsed:
                    tool_calls[call_id]["args"] = str(parsed.get("input") or "")
                else:
                    tool_calls[call_id]["args"] += delta
            elif kind == "TOOL_CALL_RESULT":
                content = str(event.get("content") or "")
                tool_results.append(content)
                if call_id in tool_calls:
                    tool_calls[call_id]["content"] = content
            elif kind == "CUSTOM" and event.get("name") == "grid.ui":
                value = event.get("value")
                if isinstance(value, dict):
                    surface_call = str(value.get("toolCallId") or "")
                    if surface_call in tool_calls:
                        tool_calls[surface_call]["ui"] = value.get("root")
                        tool_calls[surface_call]["surfaceId"] = value.get("surfaceId") or ""
            stream.send(event)

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
            self.runtime.set_event_sink(sink)
            self.runtime.set_policy_override(policy)
            assistant_text = self.orchestrator.process(prompt, stream=True) or ""
            if not isinstance(assistant_text, str):
                assistant_text = str(assistant_text)
            display_text = assistant_text
            if tool_results:
                cleaned = re.sub(
                    r"^\[Tool:\s*[^\]]+\]\s*\n?", "", assistant_text
                ).strip()
                normalized = [result.strip() for result in tool_results if result.strip()]
                if cleaned and any(cleaned == result for result in normalized):
                    display_text = ""
                elif assistant_text.strip() in normalized:
                    display_text = ""
            usage = getattr(backend, "last_usage", {}) or {}
            input_tokens = int(usage.get("input", 0) or 0)
            output_tokens = int(usage.get("output", 0) or 0)
            estimated = False
            if not input_tokens and not output_tokens:
                input_tokens = max(1, len(prompt) // 4)
                output_tokens = max(0, len(display_text) // 4)
                estimated = True
            stream.send(
                {
                    "type": "CUSTOM",
                    "name": "grid.stats",
                    "value": {
                        "durationMs": int((time.time() - started_at) * 1000),
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "totalTokens": input_tokens + output_tokens,
                        "model": getattr(backend, "model", ""),
                        "toolCalls": len(tool_results),
                        "estimated": estimated,
                    },
                }
            )
            if display_text:
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
                        "delta": display_text,
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
            incoming = [
                {
                    "id": str(message.get("id") or f"msg_{uuid.uuid4().hex[:12]}"),
                    "role": str(message.get("role") or "user"),
                    "content": message.get("content") or "",
                }
                for message in messages
                if isinstance(message, dict) and message.get("role") in {"user", "assistant"}
            ]
            turn_messages = list(incoming)
            turn_messages.extend(
                tool_calls[call_id]
                for call_id in tool_order
                if call_id in tool_calls
            )
            turn_messages.append(
                {"id": message_id, "role": "assistant", "content": display_text}
            )
            existing = self.threads.get(thread_id) or {}
            prior = existing.get("messages") if isinstance(existing, dict) else None
            if isinstance(prior, list) and len(incoming) <= 1:
                stored = list(prior) + turn_messages
            else:
                stored = turn_messages
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
        self._audit(f"decision {approval_id} {decision}")
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
                elif path == "/api/v1/model":
                    server._json(self, 200, server._model_info())
                elif path == "/api/v1/provider":
                    server._json(self, 200, server._provider_info())
                elif path == "/api/v1/ui/catalog":
                    from grid_ui import catalog

                    server._json(
                        self,
                        200,
                        {"ok": True, "catalog": catalog()},
                    )
                elif path == "/api/v1/tools":
                    server._json(self, 200, server._tools_info())
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
                if path == "/api/v1/model":
                    code, payload = server._set_model(self._read_json())
                    server._json(self, code, payload)
                    return
                if path == "/api/v1/provider":
                    code, payload = server._set_provider(self._read_json())
                    server._json(self, code, payload)
                    return
                if path == "/api/v1/provider/models":
                    code, payload = server._provider_models(self._read_json())
                    server._json(self, code, payload)
                    return
                if path == "/api/v1/threads/clear":
                    server._json(self, 200, server._clear_threads())
                    return
                if path == "/api/v1/ui/action":
                    body = self._read_json()
                    from grid_ui import handle_action

                    result = handle_action(
                        str(body.get("action") or ""),
                        body.get("payload") if isinstance(body.get("payload"), dict) else {},
                    )
                    server._json(self, 200 if result.get("ok") else 400, result)
                    return
                if path == "/api/v1/command":
                    body = self._read_json()
                    code, payload = server._local_command(body.get("command", ""))
                    server._json(self, code, payload)
                    return
                if path == "/api/v1/shutdown":
                    code, payload = server._shutdown_host()
                    server._json(self, code, payload)
                    if code == 200:
                        try:
                            self.wfile.flush()
                        except OSError:
                            pass
                        server.shutdown_event.set()
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
        while not server.shutdown_event.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0
