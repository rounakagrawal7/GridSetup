import os
import sys
import unittest
from pathlib import Path

from grid_mcp import MCPClient, MCPManager


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "mcp_echo_server.py"
GRID_SERVER = ROOT / "grid_mcp_server.py"


class MCPTests(unittest.TestCase):
    def config(self, **overrides):
        entry = {
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "cwd": str(ROOT),
            "enabled": True,
        }
        entry.update(overrides)
        return {"echo": entry}

    def test_client_handshake_list_and_call(self):
        client = MCPClient(
            "echo",
            sys.executable,
            [str(FIXTURE)],
            cwd=str(ROOT),
        )
        try:
            client.start()
            tools = client.list_tools()
            self.assertEqual([tool.name for tool in tools], ["echo", "add"])
            self.assertEqual(client.call_tool("echo", {"text": "hello"}), "hello")
            self.assertEqual(client.call_tool("add", {"a": 2, "b": 3}), "5.0")
        finally:
            client.close()

    def test_manager_lists_and_calls(self):
        manager = MCPManager(self.config())
        try:
            self.assertIn("echo", manager.list_servers_text())
            self.assertIn("echo", manager.list_tools_text("echo"))
            self.assertEqual(
                manager.call_text("echo", "echo", '{"text": "manager"}'),
                "manager",
            )
            self.assertEqual(
                manager.call_text("echo", "add", '{"a": 4, "b": 5}'),
                "9.0",
            )
        finally:
            manager.close_all()

    def test_allowlist_and_bad_json(self):
        manager = MCPManager(self.config(allow=["echo"]))
        try:
            self.assertIn(
                "not in the allowlist",
                manager.call_text("echo", "add", '{"a": 1, "b": 2}'),
            )
            self.assertIn(
                "must be JSON",
                manager.call_text("echo", "echo", "not json"),
            )
        finally:
            manager.close_all()

    def test_disabled_server(self):
        manager = MCPManager(self.config(enabled=False))
        self.assertIn("disabled", manager.list_servers_text())
        self.assertIn("disabled", manager.call_text("echo", "echo", "{}"))

    def test_grid_server_exposes_read_only_tools(self):
        client = MCPClient(
            "grid",
            sys.executable,
            [str(GRID_SERVER)],
            cwd=str(ROOT),
        )
        try:
            client.start()
            names = [tool.name for tool in client.list_tools()]
            self.assertIn("system_info", names)
            self.assertIn("grid_tool", names)
            self.assertNotIn("run_command", names)
            output = client.call_tool("grid_tool", {"tool": "get_cwd", "input": ""})
            self.assertIn("GridSetup", output)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
