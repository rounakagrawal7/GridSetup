"""Constrained server-driven UI for GRID.

The model never ships HTML, JavaScript or arbitrary component names. The
server builds one of the components in ``CATALOG`` and the desktop renders it
with native Compose widgets. ``expand_macro`` keeps sensitive data binding on
the server side: callers pass a macro name plus references, never the private
payload itself.

This is the small GRID subset inspired by Google's A2UI 1.0
(https://a2ui.org/). It is deliberately independent of any A2UI SDK so the
transport can stay AG-UI and clients can fall back to plain text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MAX_TEXT = 8000
MAX_FALLBACK = 4000
MAX_SURFACE = 60000

CATALOG = (
    "markdown",
    "table",
    "keyValue",
    "card",
    "button",
    "form",
    "select",
    "approval",
    "artifact",
    "chart",
)

_MACROS: Dict[str, Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = {}


def ui_macro(name: str):
    """Register a server-side macro. Models only ever name the macro."""

    def decorator(fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]):
        _MACROS[name] = fn
        return fn

    return decorator


def expand_macro(name: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fn = _MACROS.get(name)
    if fn is None:
        return None
    try:
        surface = fn(payload or {})
    except Exception:
        return None
    if not isinstance(surface, dict):
        return None
    try:
        encoded = json.dumps(surface, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    if len(encoded.encode("utf-8")) > MAX_SURFACE:
        # Never send an unbounded surface. Keep the text fallback.
        return None
    return surface


def catalog() -> List[str]:
    return list(CATALOG)


def handle_action(action: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    action = (action or "").strip()
    if not action:
        return {"ok": False, "error": "action is required"}
    if action.startswith("artifact."):
        return {
            "ok": True,
            "message": "Artifact actions are handled by the desktop.",
        }
    if action == "noop":
        return {"ok": True, "message": "Action received."}
    return {
        "ok": True,
        "message": f"Action '{action}' received.",
        "payload": payload or {},
    }


def _clip(text: Any, limit: int = MAX_TEXT) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n…"


def _card(
    title: str,
    children: List[Dict[str, Any]],
    subtitle: str = "",
    tone: str = "default",
) -> Dict[str, Any]:
    return {
        "type": "card",
        "title": _clip(title, 200),
        "subtitle": _clip(subtitle, 400),
        "tone": tone,
        "children": children,
    }


def _markdown(text: Any) -> Dict[str, Any]:
    return {"type": "markdown", "text": _clip(text, MAX_TEXT)}


def _key_value(items: List[tuple]) -> Dict[str, Any]:
    return {
        "type": "keyValue",
        "items": [
            {"label": _clip(label, 80), "value": _clip(value, 1200)}
            for label, value in items
        ],
    }


def _table(columns: List[str], rows: List[List[Any]]) -> Dict[str, Any]:
    clipped_rows = []
    for row in rows:
        clipped_rows.append([_clip(cell, 600) for cell in row])
    return {
        "type": "table",
        "columns": [_clip(column, 80) for column in columns],
        "rows": clipped_rows,
    }


def _artifact(path: str, kind: str = "file", label: str = "Open") -> Dict[str, Any]:
    return {
        "type": "artifact",
        "path": _clip(path, 1000),
        "kind": kind,
        "label": label,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _system_info_surface(tool_name: str, result: str) -> Dict[str, Any]:
    items = []
    for line in result.splitlines():
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9 _/()-]{1,40}):\s*(.+?)\s*$", line)
        if match:
            items.append((match.group(1), match.group(2)))
    if not items:
        return _card(
            tool_name,
            [_markdown(result)],
            subtitle="Tool output",
        )
    return _card(
        tool_name,
        [_key_value(items)],
        subtitle="System information",
    )


def _rea_surface(
    tool_name: str,
    result: str,
    call_id: str = "",
) -> Optional[Dict[str, Any]]:
    report_match = re.search(r"^Report:\s*(.+)$", result, re.MULTILINE)
    if not report_match:
        return None
    report_path = report_match.group(1).strip()
    report_file = Path(report_path)
    if not report_file.is_file():
        return None
    manifest_path = report_file.parent / "manifest.json"
    manifest: Dict[str, Any] = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    report_text = ""
    try:
        report_text = report_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        report_text = ""

    counts = manifest.get("counts") or {}
    children: List[Dict[str, Any]] = []
    children.append(
        _key_value(
            [
                ("Target", manifest.get("target") or report_path),
                ("Host", manifest.get("host") or ""),
                ("Generated", manifest.get("generated_at") or ""),
                ("Authorization", manifest.get("authorization") or ""),
                ("Backend", manifest.get("backend") or ""),
            ]
        )
    )

    rows: List[List[Any]] = []
    for label, key in (
        ("Scripts", "scripts"),
        ("Endpoints", "endpoints"),
        ("Third-party origins", "third_party"),
        ("Secrets", "secrets"),
        ("Network events", "network"),
    ):
        rows.append([label, counts.get(key, 0)])
    missing_match = re.search(
        r"Missing security headers:\s*(.+)", report_text, re.IGNORECASE
    )
    if missing_match:
        for header in missing_match.group(1).split(","):
            header = header.strip()
            if header:
                rows.append([f"Header: {header}", "MISSING"])
    if rows:
        children.append(_table(["Finding", "Value"], rows))

    summary_lines = []
    for line in report_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Title:") or stripped.startswith("- HTTP status:"):
            summary_lines.append(stripped[2:].strip())
    if summary_lines:
        children.append(_markdown("\n".join(f"- {line}" for line in summary_lines)))

    children.append(_artifact(report_path, kind="rea_report", label="Open report"))
    return {
        "surfaceId": f"rea:{call_id or report_file.parent.name}",
        "toolCallId": call_id,
        "artifactPath": report_path,
        "artifactKind": "rea_report",
        "fallback": _clip(result, MAX_FALLBACK),
        "root": _card(
            "REA findings",
            children,
            subtitle=manifest.get("target") or report_path,
            tone="warning",
        ),
    }


@ui_macro("tool_result")
def _tool_result_macro(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    call_id = str(payload.get("call_id") or "")
    tool_name = str(payload.get("tool_name") or "tool")
    tool_input = str(payload.get("tool_input") or "")
    result = str(payload.get("result") or "")

    if tool_name == "rea":
        surface = _rea_surface(tool_name, result, call_id=call_id)
        if surface is not None:
            return surface

    if tool_name == "system_info":
        root = _system_info_surface(tool_name, result)
    elif tool_name in ("run_command", "run_code"):
        root = _card(
            tool_name,
            [_markdown(f"```\n{_clip(result, MAX_TEXT)}\n```")],
            subtitle=tool_input[:240],
            tone="default",
        )
    else:
        root = _card(
            tool_name,
            [_markdown(result)],
            subtitle=tool_input[:240] or "Tool output",
            tone="default",
        )

    return {
        "surfaceId": f"tool:{call_id or tool_name}",
        "toolCallId": call_id,
        "fallback": _clip(result, MAX_FALLBACK),
        "root": root,
    }
