import unittest

from grid_awake import (
    AutopilotRunner,
    AwakeRunner,
    CancelToken,
    DoubleEscapeWatcher,
    build_local_context,
)


class FakeLife:
    def __init__(self, goal=True, persona="TinaGrid", goal_type="once"):
        self.goal = (
            {
                "id": "g-test",
                "title": "Test goal",
                "description": "Do the thing",
                "goal_type": goal_type,
            }
            if goal else None
        )
        self.persona = persona
        self.cfg = {"autopilot_interval_seconds": 5, "autopilot_checkin_cycles": 3}
        self.events = []
        self.work = []
        self.completed = []

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

    def list_goals(self, status="active"):
        return [self.goal] if self.goal else []

    def add_goal(self, title, priority=3, goal_type="once", **kwargs):
        self.goal = {
            "id": "g-test",
            "title": title,
            "description": "",
            "goal_type": goal_type,
        }
        return f"Goal added: {title}"

    def complete_goal(self, goal_id):
        self.completed.append(goal_id)
        self.goal = None
        return f"Goal completed: {goal_id}"

    def can_act(self):
        return True

    def pending_messages(self):
        return []

    def mark_delivered(self, event_id):
        return None

    def record_event(self, *args):
        self.events.append(args)
        return {"id": "e-test"}

    def record_work(self, *args):
        self.work.append(args)


class FakeOrchestrator:
    def __init__(self, response="done", cancel=False, memory=None, backend=None):
        self.response = response
        self.cancel = cancel
        self.memory = memory
        self.backend = backend
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

    def test_awake_prompt_mentions_persona_and_skills(self):
        from grid_awake import build_awake_prompt

        prompt = build_awake_prompt(FakeLife(), "Test goal")
        self.assertIn("TinaGrid", prompt)
        self.assertIn("Moltbook as TinaGrid", prompt)
        self.assertIn("skill_search", prompt)
        self.assertIn("skill_load", prompt)

    def test_local_context_reads_chat_and_redacts_secrets(self):
        class FakeMemory:
            history = [
                {"role": "user", "content": "my api_key=SUPERSECRET please remember"},
                {"role": "assistant", "content": "Noted."},
            ]

        class FakeBackend:
            type = "ollama"

        orchestrator = FakeOrchestrator(memory=FakeMemory(), backend=FakeBackend())
        context = build_local_context(orchestrator, FakeLife())
        self.assertIn("Recent conversation", context)
        self.assertIn("[redacted]", context)
        self.assertNotIn("SUPERSECRET", context)

    def test_local_context_is_omitted_for_cloud_by_default(self):
        class FakeMemory:
            history = [{"role": "user", "content": "private"}]

        class FakeBackend:
            type = "openrouter"

        orchestrator = FakeOrchestrator(memory=FakeMemory(), backend=FakeBackend())
        context = build_local_context(orchestrator, FakeLife())
        self.assertIn("omitted", context)

    def test_autopilot_completes_one_shot_goal(self):
        life = FakeLife()
        orchestrator = FakeOrchestrator(response="done")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        result = runner.run()
        self.assertIn("Autopilot complete", result)
        self.assertEqual(life.completed, ["g-test"])
        self.assertEqual(len(life.work), 1)

    def test_autopilot_stops_on_cancel(self):
        life = FakeLife()
        orchestrator = FakeOrchestrator(response="[Cancelled by user]", cancel=True)
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        result = runner.run()
        self.assertIn("Autopilot stopped", result)
        self.assertIn("cancelled", [event[0] for event in life.events])


if __name__ == "__main__":
    unittest.main()
