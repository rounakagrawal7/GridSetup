import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import grid_resident as resident


class FakeLife:
    def __init__(self):
        self.paused = False

    def identity(self):
        return {"name": "ResidentGrid"}

    def status_text(self):
        return "GRID Life - status\n  State: awake"

    def set_paused(self, paused):
        self.paused = bool(paused)
        return "paused" if paused else "resumed"


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_info = os.environ.get("GRID_RESIDENT_INFO")
        os.environ["GRID_RESIDENT_INFO"] = str(
            Path(self.tmp.name) / "resident.json"
        )
        self.stop_event = threading.Event()
        self.server = resident.ResidentServer(
            FakeLife(),
            orchestrator=None,
            stop_event=self.stop_event,
            port=0,
        )
        self.assertTrue(self.server.start())

    def tearDown(self):
        self.server.stop()
        if self.old_info is None:
            os.environ.pop("GRID_RESIDENT_INFO", None)
        else:
            os.environ["GRID_RESIDENT_INFO"] = self.old_info
        self.tmp.cleanup()

    def test_health_and_status(self):
        self.assertTrue(resident.is_resident_alive())
        info = resident.read_info()
        self.assertEqual(info["name"], "ResidentGrid")
        base = resident._base_url()
        self.assertIsNotNone(base)
        status = resident._request(f"{base}/status")
        self.assertTrue(status["text"].startswith("GRID Life"))

    def test_handoff_returns_when_server_stops(self):
        result = {}
        thread = threading.Thread(
            target=lambda: result.setdefault(
                "ok", resident.request_handoff(timeout=5)
            )
        )
        thread.start()
        self.assertTrue(self.stop_event.wait(3))
        self.server.stop()
        thread.join(3)
        self.assertTrue(result.get("ok"))
        self.assertFalse(resident.is_resident_alive())

    def test_pause_and_resume(self):
        self.assertTrue(resident.request_pause(True))
        self.assertTrue(self.server.life.paused)
        self.assertTrue(resident.request_pause(False))
        self.assertFalse(self.server.life.paused)

    def test_launch_detached_is_a_noop_when_alive(self):
        self.assertFalse(resident.launch_detached())

    @mock.patch("grid_resident.subprocess.Popen")
    @mock.patch("grid_resident.is_resident_alive", return_value=False)
    def test_launch_detached_command(self, _alive, popen):
        self.assertTrue(resident.launch_detached())
        command = popen.call_args[0][0]
        self.assertIn("grid_agent.py", command[1])
        self.assertIn("--resident", command)


if __name__ == "__main__":
    unittest.main()
