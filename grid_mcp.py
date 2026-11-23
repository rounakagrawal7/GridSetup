"""Minimal Model Context Protocol (MCP) stdio client for GRID v3.

This speaks the line-delimited JSON-RPC transport used by MCP servers. It is
intentionally small: one process per configured server, lazily started, with a
timeout and a bounded stderr tail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    pass


@dataclass
class MCPTool:
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


class MCPClient:
    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout = float(timeout)
        self.proc: Optional[subprocess.Popen] = None
        self.server_info: Dict[str, Any] = {}
        self.protocol_version = MCP_PROTOCOL_VERSION
        self._next_id = 0
        self._responses: Dict[int, Dict[str, Any]] = {}
        self._condition = threading.Condition()
        self._stderr: List[str] = []
        self._started = False

    def _start_process(self) -> None:
        env = os.environ.copy()
        env.update(self.env)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=self.cwd,
            env=env,
            **kwargs,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            message_id = message.get("id")
            if message_id is None:
                continue
            with self._condition:
                self._responses[int(message_id)] = message
                self._condition.notify_all()

    def _read_stderr(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr.append(line.rstrip())
            if len(self._stderr) > 20:
                self._stderr.pop(0)

    def _send(self, payload: Dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise MCPError(f"MCP server '{self.name}' is not running")
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except OSError as exc:
            raise MCPError(f"Could not write to MCP server '{self.name}': {exc}") from exc

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        })
        with self._condition:
            found = self._condition.wait_for(
                lambda: request_id in self._responses,
                timeout=self.timeout,
            )
            message = self._responses.pop(request_id, None) if found else None
        if message is None:
            tail = "\n".join(self._stderr[-5:])
            raise MCPError(
                f"MCP server '{self.name}' did not answer {method}"
                + (f": {tail}" if tail else "")
            )
        if "error" in message:
            error = message["error"]
            raise MCPError(f"MCP {method} failed: {error}")
        return message.get("result") or {}

    def start(self) -> "MCPClient":
        if self._started:
            return self
        self._start_process()
        result = self._request("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "GRID", "version": "3.0"},
        })
        self.protocol_version = result.get("protocolVersion", MCP_PROTOCOL_VERSION)
        self.server_info = result.get("serverInfo") or {}
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._started = True
        return self

    def list_tools(self) -> List[MCPTool]:
        result = self._request("tools/list")
        return [
            MCPTool(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                input_schema=item.get("inputSchema") or {},
            )
            for item in (result.get("tools") or [])
            if item.get("name")
        ]

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        result = self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })
        content = result.get("content") or []
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
            elif isinstance(item, dict):
                chunks.append(json.dumps(item, ensure_ascii=False))
        text = "\n".join(chunk for chunk in chunks if chunk)
        if result.get("isError"):
            return f"[MCP error] {text or 'tool returned an error'}"
        return text or "(no text content)"

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        self.proc = None
        self._started = False


class MCPManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.clients: Dict[str, MCPClient] = {}

    def names(self) -> List[str]:
        return sorted(self.config)

    def _settings(self, name: str) -> Dict[str, Any]:
        settings = self.config.get(name)
        if not isinstance(settings, dict):
            raise MCPError(f"MCP server '{name}' is not configured")
        if settings.get("enabled", True) is False:
            raise MCPError(f"MCP server '{name}' is disabled")
        return settings

    def client(self, name: str) -> MCPClient:
        if name in self.clients:
            return self.clients[name]
        settings = self._settings(name)
        command = settings.get("command")
        if not command:
            raise MCPError(f"MCP server '{name}' has no command")
        client = MCPClient(
            name=name,
            command=str(command),
            args=settings.get("args") or [],
            env=settings.get("env") or {},
            cwd=settings.get("cwd") or None,
            timeout=float(settings.get("timeout", 30)),
        )
        client.start()
        self.clients[name] = client
        return client

    def list_servers_text(self) -> str:
        if not self.config:
            return (
                "No MCP servers configured. Add an 'mcp_servers' object to "
                "config.json; each entry needs command and optional args."
            )
        lines = ["MCP servers:"]
        for name in self.names():
            settings = self.config.get(name) or {}
            enabled = "enabled" if settings.get("enabled", True) else "disabled"
            command = settings.get("command", "?")
            allow = settings.get("allow")
            allow_text = f"; allow={','.join(allow)}" if allow else ""
            lines.append(f"  {name}: {enabled}; command={command}{allow_text}")
        return "\n".join(lines)

    def list_tools_text(self, name: str) -> str:
        try:
            client = self.client(name)
        except MCPError as exc:
            return f"Error: {exc}"
        tools = client.list_tools()
        if not tools:
            return f"MCP server '{name}' exposes no tools."
        lines = [f"MCP tools on '{name}':"]
        for tool in tools:
            lines.append(f"  {tool.name}: {tool.description}")
        return "\n".join(lines)

    def call_text(self, name: str, tool_name: str, arguments_text: str = "") -> str:
        try:
            settings = self._settings(name)
        except MCPError as exc:
            return f"Error: {exc}"
        allow = settings.get("allow")
        if allow and tool_name not in allow:
            return f"MCP tool '{tool_name}' is not in the allowlist for '{name}'."
        arguments: Dict[str, Any] = {}
        raw = (arguments_text or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return f"Error: MCP arguments must be JSON: {exc}"
            if not isinstance(parsed, dict):
                return "Error: MCP arguments must be a JSON object."
            arguments = parsed
        try:
            return self.client(name).call_tool(tool_name, arguments)
        except MCPError as exc:
            return f"Error: {exc}"

    def close_all(self) -> None:
        for client in list(self.clients.values()):
            client.close()
        self.clients = {}
