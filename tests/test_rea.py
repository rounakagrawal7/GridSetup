import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

import grid_rea


PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GRID REA Fixture</title>
  <meta name="generator" content="fixturegen">
  <link rel="stylesheet" href="/site.css">
  <script src="/app.js"></script>
</head>
<body>
  <h1>Fixture</h1>
  <form action="/login" method="post">
    <input name="username" />
  </form>
  <a href="/about">About</a>
</body>
</html>
"""

APP_JS = """
fetch('/api/users');
axios.post('/api/session', {});
const key = 'AKIAABCDEFGHIJKLMNOP';
const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXRlc3Q';
"""


class FixtureHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/app.js":
            body = APP_JS.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


class ReaTargetTests(unittest.TestCase):
    def test_public_domain_defaults_to_https(self):
        target = grid_rea.parse_target("example.com/path")
        self.assertEqual(target.url, "https://example.com/path")
        self.assertEqual(target.host, "example.com")
        self.assertFalse(target.explicit)

    def test_local_host_defaults_to_http(self):
        target = grid_rea.parse_target("localhost:8080")
        self.assertEqual(target.url, "http://localhost:8080")
        self.assertTrue(grid_rea._is_private_host(target.host))

    def test_authorized_prefix_is_stripped_and_marked(self):
        target = grid_rea.parse_target("authorized https://example.com/a")
        self.assertTrue(target.explicit)
        self.assertEqual(target.url, "https://example.com/a")

    def test_rejects_non_http_schemes(self):
        with self.assertRaises(ValueError):
            grid_rea.parse_target("ftp://example.com")
        with self.assertRaises(ValueError):
            grid_rea.parse_target("   ")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            grid_rea.parse_target("https://user:pass@example.com")

    def test_private_hosts(self):
        for host in ("127.0.0.1", "10.1.2.3", "192.168.1.4", "::1", "box.local", "app.test"):
            self.assertTrue(grid_rea._is_private_host(host), host)
        for host in ("example.com", "8.8.8.8"):
            self.assertFalse(grid_rea._is_private_host(host), host)

    def test_authorize_allowlist_and_wildcard(self):
        security = {"authorized_targets": ["example.com", "*.lab.test"]}
        ok, reason = grid_rea.authorize(grid_rea.parse_target("https://example.com"), security)
        self.assertTrue(ok)
        self.assertIn("allowlist", reason)
        ok, _ = grid_rea.authorize(grid_rea.parse_target("https://api.example.com"), security)
        self.assertTrue(ok)
        ok, _ = grid_rea.authorize(grid_rea.parse_target("https://app.lab.test"), security)
        self.assertTrue(ok)
        ok, _ = grid_rea.authorize(grid_rea.parse_target("https://evil.example"), security)
        self.assertFalse(ok)

    def test_authorize_refuses_unknown_public_host(self):
        ok, reason = grid_rea.authorize(
            grid_rea.parse_target("https://not-mine.example.org"), {}
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "not authorized")

    def test_explicit_authorization_wins(self):
        ok, reason = grid_rea.authorize(
            grid_rea.parse_target("authorized https://not-mine.example.org"), {}
        )
        self.assertTrue(ok)
        self.assertIn("authorized", reason)


class ReaHelpersTests(unittest.TestCase):
    def test_extracts_endpoints_from_html_and_scripts(self):
        endpoints = grid_rea._extract_endpoints(
            '<script>fetch("/api/one")</script>',
            ["axios.get('/api/two'); fetch('https://cdn.example.net/x')"],
            "https://example.com/",
        )
        self.assertIn("https://example.com/api/one", endpoints)
        self.assertIn("https://example.com/api/two", endpoints)
        self.assertNotIn("https://cdn.example.net/x", endpoints)

    def test_missing_headers(self):
        missing = grid_rea._missing_headers(
            {"Content-Security-Policy": "default-src 'self'", "Server": "x"}
        )
        self.assertNotIn("content-security-policy", missing)
        self.assertIn("strict-transport-security", missing)

    def test_secret_redaction(self):
        findings = grid_rea._find_secrets(["key=AKIAABCDEFGHIJKLMNOP"])
        self.assertEqual(len(findings), 1)
        self.assertIn("aws_access_key", findings[0])
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", findings[0])

    def test_slug_is_filesystem_safe(self):
        self.assertEqual(grid_rea._slug("exa mple..com"), "exa-mple..com")
        self.assertEqual(grid_rea._slug("***"), "target")

    def test_npx_is_opt_in(self):
        old_which = grid_rea.shutil.which
        grid_rea.shutil.which = lambda name: "C:/fake/npx.cmd" if name == "npx" else None
        try:
            self.assertIsNone(grid_rea._rea_command({}))
            command = grid_rea._rea_command({"allow_npx": True})
            self.assertEqual(command[:2], ["C:/fake/npx.cmd", "-y"])
            self.assertIn("rea-agents@", command[2])
        finally:
            grid_rea.shutil.which = old_which


class ReaAllowlistEditingTests(unittest.TestCase):
    def test_authorize_and_revoke_host(self):
        security, message = grid_rea.authorize_host({}, "https://Example.com/path")
        self.assertEqual(security["authorized_targets"], ["example.com"])
        self.assertIn("Authorized", message)

        security, message = grid_rea.authorize_host(security, "example.com")
        self.assertEqual(security["authorized_targets"], ["example.com"])
        self.assertIn("Already", message)

        security, message = grid_rea.revoke_host(security, "example.com")
        self.assertEqual(security["authorized_targets"], [])
        self.assertIn("Revoked", message)

        security, message = grid_rea.revoke_host(security, "example.com")
        self.assertIn("Not in allowlist", message)

    def test_list_allowlist(self):
        self.assertIn("No authorized targets", grid_rea.list_allowlist({}))
        listing = grid_rea.list_allowlist({"authorized_targets": ["example.com"]})
        self.assertIn("- example.com", listing)


class ReaTeardownTests(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.old_refs = grid_rea.REFS_DIR
        grid_rea.REFS_DIR = Path(self.tmp.name) / "rea"

    def tearDown(self):
        grid_rea.REFS_DIR = self.old_refs
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_native_teardown_writes_expected_report(self):
        result = grid_rea.run_teardown(
            f"authorized {self.base}/", {"rea": {"enabled": False}}
        )
        self.assertIn("REA complete", result)
        self.assertIn("Backend: native", result)

        report_dir = next((Path(self.tmp.name) / "rea").iterdir())
        report = (report_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("GRID REA Fixture", report)
        self.assertIn("fixturegen", report)
        self.assertIn("/api/users", report)
        self.assertIn("aws_access_key", report)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", report)
        self.assertIn("content-security-policy", report)

        manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["backend"], "native")
        self.assertEqual(manifest["host"], f"127.0.0.1")
        self.assertGreaterEqual(manifest["counts"]["endpoints"], 2)

        network = json.loads((report_dir / "network.json").read_text(encoding="utf-8"))
        self.assertEqual(network, [])

    def test_refuses_unauthorized_public_target_without_request(self):
        result = grid_rea.run_teardown("https://not-mine.example.org", {})
        self.assertIn("not authorized", result)
        self.assertFalse((Path(self.tmp.name) / "rea").exists())

    def test_backend_falls_back_when_rea_is_missing(self):
        old_find = grid_rea._find_browser
        grid_rea._find_browser = lambda cfg: None
        try:
            result = grid_rea.run_teardown(
                f"authorized {self.base}/",
                {"rea": {"enabled": True, "browser": "C:/missing/chrome.exe"}},
            )
        finally:
            grid_rea._find_browser = old_find
        self.assertIn("Backend: native", result)
        report_dir = next((Path(self.tmp.name) / "rea").iterdir())
        manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any("REA backend unavailable" in note for note in manifest["notes"]))


class ReaRoutingTests(unittest.TestCase):
    def setUp(self):
        from grid_agent import GridOrchestrator, Tools

        class FakeBackend:
            type = "ollama"
            model = "test-model"

            def chat(self, messages, temperature=0.3):
                return "summary"

        self.Tools = Tools
        self.orch = GridOrchestrator(FakeBackend(), None)

    def test_rea_is_registered_and_dangerous(self):
        from grid_permissions import classify_tool

        self.assertIn("rea", self.Tools.registry)
        self.assertEqual(classify_tool("rea"), "dangerous")

    def test_auto_detect_routes_rea(self):
        tool, tool_input = self.orch._auto_detect_tool(
            "rea authorized https://example.com", ""
        )
        self.assertEqual(tool, "rea")
        self.assertEqual(tool_input, "authorized https://example.com")

    def test_auto_detect_routes_reverse_engineer_phrasing(self):
        tool, tool_input = self.orch._auto_detect_tool(
            "reverse engineer https://example.com", ""
        )
        self.assertEqual(tool, "rea")
        self.assertEqual(tool_input, "https://example.com")

    def test_short_name_does_not_match_ordinary_words(self):
        for text in ("read the file notes.txt", "real estate prices in Nepal"):
            result = self.orch._auto_detect_tool(text, "")
            self.assertTrue(result is None or result[0] != "rea", text)


if __name__ == "__main__":
    unittest.main()
