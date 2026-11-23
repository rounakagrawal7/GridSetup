import unittest

from grid_awake import AwakeRunner, CancelToken, DoubleEscapeWatcher


class FakeLife:
    def __init__(self, goal=True, persona="TinaGrid"):
        self.goal = (
            {"id": "g-test", "title": "Test goal", "description": "Do the thing"}
            if goal else None
        )
        self.persona = persona
        self.events = []
        self.work = []

    def identity(self):
        return {
            "name": self.persona or "GRID",
            "voice": "direct",
            "values": "local-first",
            "boundaries": "ask first",
        }

    def identity_text(self):
        social = f"Moltbook as {self.persona}" if self.persona else "not configured"
        return (
            f"GRID Life identity\n  Name: {self.identity()['name']}\n"
            f"  Social: {social}"
        )

    def focus_goal(self):
        return self.goal

    def record_event(self, *args):
        self.events.append(args)

    def record_work(self, *args):
        self.work.append(args)


class FakeOrchestrator:
    def __init__(self, response="done", cancel=False):
        self.response = response
        self.cancel = cancel
        self.prompts = []

    def process(self, prompt, stream=True, step_logs=None):
        from grid_agent import Tools

        self.prompts.append(prompt)
        if step_logs is not None:
            step_logs.append("Step 1: system_info")
        if self.cancel and Tools.cancel_token is not None:
            Tools.cancel_token.cancel()
        return self.response


class FakeConsole:
    def print(self, *args, **kwargs):
        pass


class AwakeTests(unittest.TestCase):
    def test_cancel_token(self):
        token = CancelToken()
        self.assertFalse(token.is_set())
        token.cancel()
        self.assertTrue(token.is_set())
        token.reset()
        self.assertFalse(token.is_set())

    def test_double_escape_sets_token(self):
        token = CancelToken()
        watcher = DoubleEscapeWatcher(token)
        watcher._on_escape()
        self.assertFalse(token.is_set())
        watcher._on_escape()
        self.assertTrue(token.is_set())

    def test_runner_uses_goal_and_records_work(self):
        life = FakeLife()
        orchestrator = FakeOrchestrator()
        runner = AwakeRunner(life, orchestrator, FakeConsole(), {"mode": "read_only"})
        result = runner.run()
        self.assertEqual(result, "done")
        self.assertEqual(len(life.work), 1)
        self.assertIn("Test goal", life.work[0][0])
        self.assertIn("Test goal", orchestrator.prompts[0])

    def test_runner_stops_and_records_cancel(self):
        life = FakeLife()
        orchestrator = FakeOrchestrator(response="[Cancelled by user]", cancel=True)
        runner = AwakeRunner(life, orchestrator, FakeConsole(), {"mode": "read_only"})
        result = runner.run()
        self.assertIn("Cancelled", result)
        self.assertEqual(len(life.events), 1)
        self.assertEqual(life.events[0][0], "cancelled")

    def test_runner_without_goal(self):
        life = FakeLife(goal=False)
        runner = AwakeRunner(life, FakeOrchestrator(), FakeConsole(), {"mode": "read_only"})
        result = runner.run()
        self.assertIn("No active goals", result)


if __name__ == "__main__":
    unittest.main()
