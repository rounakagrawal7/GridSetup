import time
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


class FakeBackend:
    def __init__(self, reply="I'm here."):
        self.reply = reply
        self.calls = []

    def chat(self, messages, temperature=0.7):
        self.calls.append(messages)
        return self.reply


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

    def test_autopilot_completes_one_shot_goal_and_stays_awake(self):
        life = FakeLife()
        orchestrator = FakeOrchestrator(response="done")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        # The idle prompt would block on stdin; cancel after the completion.
        runner._idle = lambda: (runner.token.cancel(), "")[1]
        result = runner.run()
        self.assertIn("Autopilot stopped", result)
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

    def test_idle_chat_does_not_call_tools(self):
        life = FakeLife(goal=False)
        orchestrator = FakeOrchestrator()
        orchestrator.backend = FakeBackend("I'm well, and thinking about the iLog.")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        reply = runner._chat_reply("how are you")
        self.assertIn("well", reply)
        self.assertEqual(runner._extract_goal(reply), "")
        self.assertEqual(len(orchestrator.prompts), 0)

    def test_idle_chat_can_propose_a_goal(self):
        life = FakeLife(goal=False)
        orchestrator = FakeOrchestrator()
        orchestrator.backend = FakeBackend("On it.\nGOAL: Review the iLog")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        reply = runner._chat_reply("please review the iLog")
        self.assertEqual(runner._extract_goal(reply), "Review the iLog")

    def test_self_direction_adds_one_goal(self):
        life = FakeLife(goal=False)
        orchestrator = FakeOrchestrator()
        orchestrator.backend = FakeBackend("GOAL: Tidy my notes")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        self.assertTrue(runner._propose_goal())
        self.assertEqual(life.goal["title"], "Tidy my notes")

    def test_self_direction_phrases(self):
        runner = AutopilotRunner(
            FakeLife(), FakeOrchestrator(), FakeConsole(), {"mode": "read_only"}
        )
        self.assertTrue(runner._wants_self_direction("pick your next goal"))
        self.assertTrue(runner._wants_self_direction("pick your goal yourself"))
        self.assertTrue(runner._wants_self_direction("you choose"))
        self.assertFalse(runner._wants_self_direction("have you selected any goals?"))
        self.assertFalse(runner._wants_self_direction("which goal did you pick?"))

    def test_self_direction_falls_back_when_model_misses_format(self):
        life = FakeLife(goal=False)
        orchestrator = FakeOrchestrator()
        orchestrator.backend = FakeBackend("I might organize my notes.")
        runner = AutopilotRunner(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        self.assertTrue(runner._propose_goal(fallback=True))
        self.assertIn("Review recent memory", life.goal["title"])

    def test_budget_rest_is_not_an_exit(self):
        life = FakeLife()
        life.can_act = lambda: False
        runner = AutopilotRunner(
            life, FakeOrchestrator(), FakeConsole(), {"mode": "read_only"}
        )
        runner.token = CancelToken()
        waited = []
        runner._wait = lambda seconds: waited.append(seconds)
        self.assertTrue(runner._rest_if_needed())
        self.assertFalse(runner.token.is_set())
        self.assertEqual(waited, [300])

    def test_resident_never_blocks_on_input(self):
        from grid_awake import ResidentAutopilot

        runner = ResidentAutopilot(
            FakeLife(), FakeOrchestrator(), FakeConsole(), {"mode": "read_only"}
        )
        runner.token = CancelToken()
        self.assertEqual(runner._ask_user("anything?"), "")
        self.assertFalse(runner.token.is_set())
        self.assertEqual(runner._approve("run_command", "dir", "dangerous"), "n")

    def test_resident_leaves_messages_for_the_human(self):
        from grid_awake import ResidentAutopilot

        life = FakeLife()
        marked = []
        life.pending_messages = lambda: [
            {"id": "m-1", "summary": "Commitment due", "detail": "Do the thing"}
        ]
        life.mark_delivered = lambda event_id: marked.append(event_id)
        runner = ResidentAutopilot(
            life, FakeOrchestrator(), FakeConsole(), {"mode": "read_only"}
        )
        runner._deliver_pending()
        self.assertEqual(marked, [])
        self.assertIn("m-1", runner._seen_messages)

    def test_resident_startup_grace_delays_self_direction(self):
        from grid_awake import ResidentAutopilot

        life = FakeLife(goal=False)
        orchestrator = FakeOrchestrator()
        runner = ResidentAutopilot(
            life, orchestrator, FakeConsole(), {"mode": "read_only"}
        )
        runner.startup_grace_until = time.time() + 60
        waited = []
        runner._wait = lambda seconds: waited.append(seconds)
        runner._idle()
        self.assertTrue(waited)
        self.assertEqual(orchestrator.prompts, [])
        self.assertEqual(runner.startup_grace_until, 0.0)

    def test_runner_uses_the_live_tools_class(self):
        class LiveTools:
            cancel_token = None
            policy = None

        runner = AutopilotRunner(
            FakeLife(),
            FakeOrchestrator(),
            FakeConsole(),
            {"mode": "read_only"},
            tools=LiveTools,
        )
        self.assertIs(runner._tools(), LiveTools)
        runner._start()
        self.assertIs(LiveTools.cancel_token, runner.token)
        self.assertIs(LiveTools.policy, runner.policy)
        runner._stop()
        self.assertIsNone(LiveTools.cancel_token)
        self.assertIsNone(LiveTools.policy)


if __name__ == "__main__":
    unittest.main()
