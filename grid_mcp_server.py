"""GRID as an MCP server.

Run: python grid_mcp_server.py

Exposes a read-only subset of GRID's tools over the MCP stdio transport, so
Claude Code, Codex, Cursor or another MCP client can use GRID's local recon,
document and skill tools. No PocketBase, memory writes or LLM are started.
"""

from __future__ import annotations

import json
import sys

from grid_agent import Tools
from grid_permissions import READ_ONLY
from grid_skilldocs import SkillDocManager


PROTOCOL_VERSION = "2024-11-05"

ALLOWED = [
    "system_info",
    "get_cwd",
    "list_directory",
    "read_file",
    "file_search",
    "document_read",
    "dns_lookup",
    "ping",
    "netstat",
    "web_fetch",
    "web_search",
    "weather",
    "osint",
    "skill_search",
    "skill_load",
]
ALLOWED = [name for name in ALLOWED if name in Tools.registry and name in READ_ONLY]


def _tool_descriptions():
    tools = []
    for name in ALLOWED:
        info = Tools.registry.get(name, {})
        tools.append({
            "name": name,
            "description": info.get("desc", name),
            "inputSchema": {
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"],
            },
        })
    tools.append({
        "name": "grid_tool",
        "description": "Run a read-only GRID tool. Use grid_tool with tool and input.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "enum": ALLOWED},
                "input": {"type": "string"},
            },
            "required": ["tool"],
        },
    })
    return tools


def _send(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _text_result(text: str, is_error: bool = False):
    return {
        "content": [{"type": "text", "text": str(text)}],
        "isError": bool(is_error),
    }


def _call_tool(name: str, arguments):
    arguments = arguments or {}
    if name == "grid_tool":
        tool = str(arguments.get("tool", "")).strip()
        if tool not in ALLOWED:
            return _text_result(f"Tool '{tool}' is not exposed by this server.", True)
        tool_input = str(arguments.get("input", ""))
    elif name in ALLOWED:
        tool = name
        tool_input = str(arguments.get("input", ""))
    else:
        return _text_result(f"Unknown tool '{name}'.", True)
    try:
        return _text_result(Tools.execute(tool, tool_input))
    except Exception as exc:
        return _text_result(f"GRID error: {exc}", True)


def main():
    Tools.skilldocs = SkillDocManager()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if request_id is None:
            continue
        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "grid", "version": "3.0"},
                },
            })
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": _tool_descriptions()},
            })
        elif method == "tools/call":
            name = str(params.get("name", ""))
            result = _call_tool(name, params.get("arguments"))
            _send({"jsonrpc": "2.0", "id": request_id, "result": result})
        else:
            _send({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            })


if __name__ == "__main__":
    main()
