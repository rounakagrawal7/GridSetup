import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

import grid_agent
from grid_api import DiscoveryResponder, GridAPIServer, PairingManager, ThreadStore
from grid_agent import Tools


class FakeBackend:
    type = "ollama"
    model = "fake-model"
    base_url = "http://fake-ollama"

    @staticmethod
    def fetch_models(backend_type, base_url):
        return ["fake-model", "other-model"]


class FakeOrchestrator:
    def __init__(self):
        self.backend = FakeBackend()
        self.prompts = []

    def process(self, prompt, stream=True):
        self.prompts.append(prompt)
        return f"echo: {prompt}"


class APITestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.refs = self.root / "rea"
        self.orch = FakeOrchestrator()
        self.server = GridAPIServer(
            self.orch,
            config={"permissions": {"mode": "read_only"}},
            token="test-token",
            host="127.0.0.1",
            port=0,
            thread_store=ThreadStore(self.root / "threads.json"),
            refs_dir=self.refs,
        )
        self.assertTrue(self.server.start())
        self.base = f"http://127.0.0.1:{self.server.port}/api/v1"
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def _events(self, payload):
        events = []
        with requests.post(
            f"{self.base}/agent",
            json=payload,
            headers=self.headers,
            stream=True,
            timeout=10,
        ) as response:
            self.assertEqual(response.status_code, 200)
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                events.append(event)
                if event.get("type") in ("RUN_FINISHED", "RUN_ERROR"):
                    break
        return events

    def test_requires_bearer_token(self):
        self.assertEqual(requests.get(f"{self.base}/health").status_code, 401)
        self.assertEqual(
            requests.get(
                f"{self.base}/health", headers={"Authorization": "Bearer wrong"}
            ).status_code,
            401,
        )
        self.assertEqual(
            requests.get(f"{self.base}/health", headers=self.headers).status_code, 200
        )
        self.assertEqual(
            requests.post(
                f"{self.base}/command", json={"command": "/plan"}, timeout=5
            ).status_code,
            401,
        )

    def test_health_reports_protocol(self):
        payload = requests.get(f"{self.base}/health", headers=self.headers).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["protocol"], "1.0")
        self.assertEqual(payload["model"], "fake-model")

    def test_tools_endpoint_lists_registry(self):
        payload = requests.get(f"{self.base}/tools", headers=self.headers).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], len(Tools.registry))
        names = {row["name"] for row in payload["tools"]}
        self.assertIn("rea", names)
        self.assertIn("web_search", names)
        social = next(row for row in payload["tools"] if row["name"] == "social")
        subcommands = {item["name"] for item in social["subcommands"]}
        self.assertIn("auto", subcommands)
        self.assertIn("persona", subcommands)
        self.assertIn("history", subcommands)

    def test_local_command_endpoint(self):
        help_payload = requests.post(
            f"{self.base}/command",
            json={"command": "/help"},
            headers=self.headers,
            timeout=5,
        ).json()
        self.assertTrue(help_payload["ok"])
        self.assertIn("/memory", help_payload["output"])

        memory_payload = requests.post(
            f"{self.base}/command",
            json={"command": "/memory status"},
            headers=self.headers,
            timeout=5,
        ).json()
        self.assertTrue(memory_payload["ok"])
        self.assertTrue(memory_payload["output"])

        life_payload = requests.post(
            f"{self.base}/command",
            json={"command": "/life status"},
            headers=self.headers,
            timeout=5,
        ).json()
        self.assertTrue(life_payload["ok"])
        self.assertTrue(life_payload["output"])

        plan_payload = requests.post(
            f"{self.base}/command",
            json={"command": "/plan"},
            headers=self.headers,
            timeout=5,
        ).json()
        self.assertTrue(plan_payload["ok"])
        self.assertTrue(self.orch.plan_mode)
        requests.post(
            f"{self.base}/command",
            json={"command": "/plan"},
            headers=self.headers,
            timeout=5,
        )
        self.assertFalse(self.orch.plan_mode)

    def test_local_command_rejects_unknown_and_plain_text(self):
        unknown = requests.post(
            f"{self.base}/command",
            json={"command": "/nope"},
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(unknown.status_code, 400)
        plain = requests.post(
            f"{self.base}/command",
            json={"command": "hello"},
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(plain.status_code, 400)

    def test_pb_status_command_reports_manager(self):
        response = requests.post(
            f"{self.base}/command",
            json={"command": "/pb status"},
            headers=self.headers,
            timeout=10,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("PocketBase", payload["output"])

    def test_shutdown_endpoint_saves_and_signals(self):
        runtime = self.server.runtime
        old = getattr(runtime, "EXPLICIT_SHUTDOWN", False)
        self.addCleanup(setattr, runtime, "EXPLICIT_SHUTDOWN", old)
        response = requests.post(
            f"{self.base}/shutdown", headers=self.headers, timeout=5
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("shutting down", payload["message"])
        self.assertTrue(self.server.shutdown_event.wait(2))
        self.assertTrue(getattr(runtime, "EXPLICIT_SHUTDOWN", False))

    def test_provider_info_and_switch(self):
        info = requests.get(f"{self.base}/provider", headers=self.headers).json()
        self.assertTrue(info["ok"])
        self.assertEqual(len(info["providers"]), 4)
        ids = {row["id"] for row in info["providers"]}
        self.assertEqual(ids, {"ollama", "lm_studio", "openrouter", "openai"})

        class FakeLLM:
            def __init__(self, backend_type, model, base_url):
                self.type = backend_type
                self.model = model
                self.base_url = base_url

        with mock.patch.object(grid_agent, "HAS_OLLAMA", True), \
                mock.patch.object(grid_agent, "LLMBackend", FakeLLM), \
                mock.patch.object(grid_agent, "save_config") as save:
            response = requests.post(
                f"{self.base}/provider",
                json={
                    "provider": "ollama",
                    "model": "new-model",
                    "base_url": "http://localhost:11434",
                },
                headers=self.headers,
                timeout=5,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.orch.backend.type, "ollama")
        self.assertEqual(self.orch.backend.model, "new-model")
        save.assert_called()

    def test_provider_models_endpoint(self):
        class FakeLLM:
            @staticmethod
            def fetch_models(provider, base_url):
                return ["model-a", "model-b"]

        with mock.patch.object(grid_agent, "HAS_OLLAMA", True), \
                mock.patch.object(grid_agent, "LLMBackend", FakeLLM):
            response = requests.post(
                f"{self.base}/provider/models",
                json={"provider": "ollama"},
                headers=self.headers,
                timeout=5,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["model-a", "model-b"])

    def test_model_info_and_switch(self):
        info = requests.get(f"{self.base}/model", headers=self.headers).json()
        self.assertEqual(info["model"], "fake-model")
        self.assertIn("other-model", info["models"])
        with mock.patch.object(grid_agent, "save_config") as save:
            response = requests.post(
                f"{self.base}/model",
                json={"model": "other-model"},
                headers=self.headers,
                timeout=5,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.orch.backend.model, "other-model")
        save.assert_called_once_with({"model": "other-model"})

    def test_run_stream_follows_agui_shape(self):
        events = self._events(
            {
                "threadId": "thr_test",
                "runId": "run_test",
                "messages": [{"id": "m1", "role": "user", "content": "hello"}],
            }
        )
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "RUN_STARTED")
        self.assertEqual(events[0]["threadId"], "thr_test")
        self.assertEqual(events[0]["runId"], "run_test")
        self.assertEqual(events[0]["protocolVersion"], "1.0")
        self.assertIn("STEP_STARTED", types)
        self.assertIn("TEXT_MESSAGE_START", types)
        self.assertIn("TEXT_MESSAGE_CONTENT", types)
        self.assertIn("TEXT_MESSAGE_END", types)
        self.assertIn("STEP_FINISHED", types)
        self.assertEqual(types[-1], "RUN_FINISHED")
        self.assertEqual(events[-1]["outcome"], {"type": "success"})
        content = next(
            event["delta"]
            for event in events
            if event["type"] == "TEXT_MESSAGE_CONTENT"
        )
        self.assertEqual(content, "echo: hello")
        for event in events:
            self.assertIn("timestamp", event)
        stats = next(event for event in events if event.get("name") == "grid.stats")
        self.assertGreater(stats["value"]["totalTokens"], 0)
        self.assertGreaterEqual(stats["value"]["durationMs"], 0)
        self.assertEqual(stats["value"]["model"], "fake-model")
        self.assertEqual(self.orch.prompts, ["hello"])

    def test_threads_are_persisted(self):
        self._events(
            {
                "threadId": "thr_persist",
                "messages": [{"id": "m1", "role": "user", "content": "remember this"}],
            }
        )
        listing = requests.get(f"{self.base}/threads", headers=self.headers).json()
        self.assertEqual(listing["threads"][0]["id"], "thr_persist")
        detail = requests.get(
            f"{self.base}/threads/thr_persist", headers=self.headers
        ).json()
        self.assertEqual(detail["thread"]["messages"][-1]["role"], "assistant")
        self.assertIn("remember this", detail["thread"]["messages"][-1]["content"])
        self._events(
            {
                "threadId": "thr_persist",
                "messages": [{"id": "m2", "role": "user", "content": "second turn"}],
            }
        )
        detail = requests.get(
            f"{self.base}/threads/thr_persist", headers=self.headers
        ).json()
        messages = detail["thread"]["messages"]
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]["content"], "remember this")
        self.assertEqual(messages[2]["content"], "second turn")

    def test_clear_threads_only_clears_threads(self):
        self._events(
            {
                "threadId": "thr_clear",
                "messages": [{"id": "m1", "role": "user", "content": "temporary"}],
            }
        )
        before = requests.get(f"{self.base}/threads", headers=self.headers).json()
        self.assertEqual(len(before["threads"]), 1)
        response = requests.post(
            f"{self.base}/threads/clear", headers=self.headers, timeout=5
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["cleared"], 1)
        after = requests.get(f"{self.base}/threads", headers=self.headers).json()
        self.assertEqual(after["threads"], [])

    def test_tool_result_is_not_duplicated_as_text(self):
        saved_registry = dict(Tools.registry)
        saved_enabled = set(Tools.enabled)
        Tools.registry["fake_echo"] = {
            "fn": lambda text: "tool-output",
            "desc": "test tool",
            "input_desc": "input",
        }
        Tools.enabled.add("fake_echo")
        original = self.orch.process

        def process(prompt, stream=True):
            result = Tools.execute("fake_echo", "x")
            return f"[Tool: fake_echo]\n{result}"

        self.orch.process = process
        try:
            events = self._events(
                {
                    "threadId": "thr_tool",
                    "messages": [{"id": "m1", "role": "user", "content": "run fake"}],
                }
            )
        finally:
            self.orch.process = original
            Tools.registry.clear()
            Tools.registry.update(saved_registry)
            Tools.enabled.clear()
            Tools.enabled.update(saved_enabled)
        types = [event["type"] for event in events]
        self.assertIn("TOOL_CALL_RESULT", types)
        self.assertNotIn("TEXT_MESSAGE_CONTENT", types)
        ui_events = [
            event
            for event in events
            if event.get("type") == "CUSTOM" and event.get("name") == "grid.ui"
        ]
        self.assertTrue(ui_events)
        self.assertEqual(ui_events[0]["value"]["root"]["type"], "card")
        detail = requests.get(
            f"{self.base}/threads/thr_tool", headers=self.headers
        ).json()
        messages = detail["thread"]["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "tool", "assistant"])
        self.assertEqual(messages[1]["name"], "fake_echo")
        self.assertEqual(messages[1]["args"], "x")
        self.assertEqual(messages[1]["content"], "tool-output")
        self.assertEqual(messages[1]["ui"]["type"], "card")

    def test_ui_catalog_and_action(self):
        catalog = requests.get(
            f"{self.base}/ui/catalog", headers=self.headers
        ).json()
        self.assertTrue(catalog["ok"])
        self.assertIn("card", catalog["catalog"])
        self.assertIn("table", catalog["catalog"])
        response = requests.post(
            f"{self.base}/ui/action",
            json={"surfaceId": "tool:test", "action": "noop", "payload": {}},
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_rejects_missing_user_message(self):
        response = requests.post(
            f"{self.base}/agent",
            json={"threadId": "thr_x", "messages": []},
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("user message", response.json()["error"])

    def test_rejects_bad_thread_id(self):
        response = requests.post(
            f"{self.base}/agent",
            json={
                "threadId": "../escape",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(response.status_code, 400)

    def test_rea_report_listing_and_detail(self):
        directory = self.refs / "example.com-20260101-000000"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "target": "https://example.com",
                    "host": "example.com",
                    "generated_at": "2026-01-01T00:00:00",
                    "backend": "rea",
                    "authorization": "explicit",
                    "counts": {"endpoints": 3},
                }
            ),
            encoding="utf-8",
        )
        (directory / "report.md").write_text("# Teardown\n\nbody", encoding="utf-8")
        (directory / "screenshot.png").write_bytes(b"\x89PNG\r\n")
        listing = requests.get(
            f"{self.base}/rea/reports", headers=self.headers
        ).json()
        self.assertEqual(listing["reports"][0]["id"], directory.name)
        detail = requests.get(
            f"{self.base}/rea/reports/{directory.name}", headers=self.headers
        ).json()
        self.assertIn("# Teardown", detail["report"]["report"])
        shot = requests.get(
            f"{self.base}/rea/reports/{directory.name}/screenshot",
            headers=self.headers,
        )
        self.assertEqual(shot.status_code, 200)
        self.assertEqual(shot.headers["Content-Type"], "image/png")

    def test_rea_report_rejects_traversal(self):
        response = requests.get(
            f"{self.base}/rea/reports/..%2Fsecret", headers=self.headers
        )
        self.assertEqual(response.status_code, 404)

    def test_approval_decision_wakes_waiter(self):
        event = threading.Event()
        self.server._approvals["apr_test"] = {"event": event, "decision": ""}
        code, payload = self.server._handle_approval(
            "apr_test", {"decision": "approve"}
        )
        self.assertEqual(code, 200)
        self.assertTrue(event.is_set())
        self.assertEqual(payload["decision"], "approve")


class ToolEventTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self._saved_registry = dict(Tools.registry)
        self._saved_enabled = set(Tools.enabled)

    def tearDown(self):
        Tools.registry.clear()
        Tools.registry.update(self._saved_registry)
        Tools.enabled.clear()
        Tools.enabled.update(self._saved_enabled)
        grid_agent.set_event_sink(None)
        grid_agent.set_policy_override(None)

    def _register(self, name, fn):
        Tools.registry[name] = {
            "fn": fn,
            "desc": "test tool",
            "input_desc": "input",
        }
        Tools.enabled.add(name)

    def test_execute_emits_tool_call_and_result(self):
        self._register("fake_echo", lambda text: f"echo: {text}")
        grid_agent.set_event_sink(self.events.append)
        result = Tools.execute("fake_echo", "hello")
        self.assertEqual(result, "echo: hello")
        types = [event["type"] for event in self.events]
        self.assertEqual(
            types[:4],
            [
                "TOOL_CALL_START",
                "TOOL_CALL_ARGS",
                "TOOL_CALL_END",
                "TOOL_CALL_RESULT",
            ],
        )
        call_id = self.events[0]["toolCallId"]
        tool_events = [
            event for event in self.events if event["type"].startswith("TOOL_CALL")
        ]
        self.assertTrue(
            all(event.get("toolCallId") == call_id for event in tool_events)
        )
        self.assertTrue(
            any(
                event.get("type") == "CUSTOM" and event.get("name") == "grid.ui"
                for event in self.events
            )
        )
        self.assertEqual(self.events[0]["toolCallName"], "fake_echo")
        self.assertEqual(self.events[3]["content"], "echo: hello")

    def test_rea_result_emits_artifact_event(self):
        self._register(
            "rea",
            lambda _text: "REA complete\nReport: refs/rea/example/report.md",
        )
        grid_agent.set_event_sink(self.events.append)
        Tools.execute("rea", "authorized https://example.com")
        artifacts = [
            event
            for event in self.events
            if event.get("type") == "CUSTOM" and event.get("name") == "grid.artifact"
        ]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["name"], "grid.artifact")
        self.assertEqual(
            artifacts[0]["value"]["path"], "refs/rea/example/report.md"
        )

    def test_policy_override_blocks_without_mutating_global_policy(self):
        self._register("fake_echo", lambda text: f"echo: {text}")

        class Deny:
            def allow(self, _name, _input):
                return False, "requires approval"

        grid_agent.set_policy_override(Deny())
        result = Tools.safe_execute("fake_echo", "hello")
        self.assertIn("[Blocked]", result)
        self.assertIsNone(Tools.policy)


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.orch = FakeOrchestrator()
        self.server = GridAPIServer(
            self.orch,
            config={"permissions": {"mode": "read_only"}},
            token="test-token",
            host="127.0.0.1",
            port=0,
            thread_store=ThreadStore(self.root / "threads.json"),
            refs_dir=self.root / "rea",
        )
        self.assertTrue(self.server.start())
        self.base = f"http://127.0.0.1:{self.server.port}/api/v1"
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def _wrong_code(self) -> str:
        code = self.server.pairing.status()["code"]
        return "000000" if code != "000000" else "111111"

    def test_pair_endpoint_is_public_but_rate_limited(self):
        response = requests.post(
            f"{self.base}/pair",
            json={"code": self._wrong_code()},
            timeout=5,
        )
        self.assertEqual(response.status_code, 401)

    def test_pair_with_code_returns_token_and_is_one_time(self):
        code = self.server.pairing.status()["code"]
        response = requests.post(f"{self.base}/pair", json={"code": code}, timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], "test-token")

        replay = requests.post(f"{self.base}/pair", json={"code": code}, timeout=5)
        self.assertEqual(replay.status_code, 401)

    def test_pair_code_accepts_spaces_and_hyphens(self):
        code = self.server.pairing.status()["code"]
        spaced = f"{code[:3]}-{code[3:]}"
        response = requests.post(f"{self.base}/pair", json={"code": spaced}, timeout=5)
        self.assertEqual(response.status_code, 200)

    def test_pair_code_endpoint_requires_auth(self):
        self.assertEqual(
            requests.get(f"{self.base}/pair/code", timeout=5).status_code,
            401,
        )
        response = requests.get(f"{self.base}/pair/code", headers=self.headers, timeout=5)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["code"]), 6)
        self.assertIn(str(self.server.port), payload["url"])

    def test_rotate_endpoint_requires_auth(self):
        self.assertEqual(
            requests.post(f"{self.base}/pair/rotate", timeout=5).status_code,
            401,
        )
        response = requests.post(
            f"{self.base}/pair/rotate",
            headers=self.headers,
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["code"]), 6)

    def test_pairing_manager_expiry_and_attempt_limit(self):
        manager = PairingManager(ttl=60, max_attempts=2)
        code = manager.status()["code"]
        wrong = "000000" if code != "000000" else "111111"
        first = manager.validate(wrong, "10.0.0.2")
        self.assertEqual(first[2], 401)
        second = manager.validate(wrong, "10.0.0.2")
        self.assertEqual(second[2], 401)
        limited = manager.validate(wrong, "10.0.0.2")
        self.assertEqual(limited[2], 429)
        other_ip = manager.validate(wrong, "10.0.0.3")
        self.assertEqual(other_ip[2], 401)

        manager._expires_at = 0
        expired = manager.validate(code, "10.0.0.4")
        self.assertFalse(expired[0])
        self.assertEqual(expired[2], 410)


class DiscoveryTests(unittest.TestCase):
    def test_discovery_responds_with_host_port(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()

        responder = DiscoveryResponder(
            api_port=8771,
            port=port,
            device_name="test-grid",
        )
        responder.start()
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(3)
        try:
            time.sleep(0.1)
            client.sendto(b"GRID_DISCOVER", ("127.0.0.1", port))
            data, _ = client.recvfrom(1024)
            payload = json.loads(data.decode("utf-8"))
            self.assertEqual(payload["port"], 8771)
            self.assertEqual(payload["name"], "test-grid")
            self.assertEqual(payload["grid"], 1)
        finally:
            client.close()
            responder.stop()


if __name__ == "__main__":
    unittest.main()
