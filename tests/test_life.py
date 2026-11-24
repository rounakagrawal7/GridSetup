"""Acceptance tests for the GRID Life loop.

These use a temporary DuckDB and a fixed clock, so they do not need a model,
network, terminal, or the full 70-tool registry.
"""

import os
import tempfile
import unittest
from datetime import datetime

from grid_db import GridDB
from grid_life import LifeEngine


def life_config(**overrides):
    config = {
        "enabled": True,
        "heartbeat_minutes": 30,
        "quiet_hours": ["23:00", "07:00"],
        "brief_time": "09:00",
        "brief_window_minutes": 30,
        "max_actions_per_day": 12,
        "max_messages_per_day": 6,
        "goal_stale_hours": 6,
        "reflection_hours": 24,
        "commitment_repeat_hours": 6,
    }
    config.update(overrides)
    return config


class LifeEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = GridDB(os.path.join(self.tmp.name, "life.duckdb"))
        self.now = datetime(2026, 11, 24, 10, 0)
        self.life = LifeEngine(
            self.db,
            life_config(),
            now_fn=lambda: self.now,
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_identity_is_seeded(self):
        identity = self.life.identity()
        self.assertEqual(identity["name"], "GRID")
        self.assertIn("local-first", identity["values"])
        self.assertIn("GRID Life identity", self.life.identity_text())

    def test_pause_and_resume(self):
        self.life.set_paused(True)
        result = self.life.tick(self.now)
        self.assertEqual(result["action"], "rest")
        self.assertEqual(result["reason"], "paused")

        self.life.set_paused(False)
        self.assertFalse(self.life.is_paused())

    def test_quiet_hours_rest(self):
        self.life.cfg["quiet_hours"] = ["23:00", "07:00"]
        result = self.life.tick(datetime(2026, 11, 24, 23, 30))
        self.assertEqual(result["action"], "rest")
        self.assertEqual(result["reason"], "quiet hours")

    def test_persona_is_adopted_on_startup(self):
        life = LifeEngine(
            self.db,
            life_config(),
            now_fn=lambda: self.now,
            persona="TinaGrid",
        )
        self.assertEqual(life.identity()["name"], "TinaGrid")
        self.assertIn("Moltbook as TinaGrid", life.identity_text())
        self.assertFalse(life.needs_persona())

    def test_persona_onboarding_is_asked_once(self):
        self.assertTrue(self.life.needs_persona())
        self.life.mark_persona_prompted()
        self.assertFalse(self.life.needs_persona())

    def test_adopt_and_clear_persona(self):
        self.life.adopt_persona("TinaGrid")
        self.assertEqual(self.life.identity()["name"], "TinaGrid")
        self.life.clear_persona()
        self.assertEqual(self.life.identity()["name"], "GRID")
        self.assertTrue(self.life.needs_persona())

    def test_manual_wake_overrides_quiet_hours(self):
        result = self.life.tick(datetime(2026, 11, 24, 23, 30), manual=True)
        self.assertNotEqual(result.get("reason"), "quiet hours")
        self.assertEqual(result["action"], "reflect")

    def test_manual_wake_overrides_action_budget(self):
        self.life.cfg["max_actions_per_day"] = 0
        result = self.life.tick(self.now, manual=True)
        self.assertNotEqual(result.get("reason"), "daily action budget reached")

    def test_same_day_quiet_hours(self):
        self.life.cfg["quiet_hours"] = ["12:00", "14:00"]
        result = self.life.tick(datetime(2026, 11, 24, 13, 0))
        self.assertEqual(result["reason"], "quiet hours")

    def test_daily_brief_is_sent_once(self):
        self.life.cfg["brief_time"] = "09:00"
        result = self.life.tick(datetime(2026, 11, 24, 9, 5))
        self.assertEqual(result["action"], "message")
        self.assertEqual(result["summary"], "Daily brief")
        self.assertEqual(len(self.life.pending_messages()), 1)

        self.life.tick(datetime(2026, 11, 24, 9, 6))
        self.assertEqual(len(self.life.pending_messages()), 1)

    def test_due_commitment_messages_and_repeats(self):
        self.life.cfg["brief_time"] = "23:00"
        self.life.add_commitment(
            "Send the OSINT report",
            due_at=datetime(2026, 11, 24, 9, 0),
            now=self.now,
        )
        result = self.life.tick(self.now)
        self.assertEqual(result["action"], "message")
        self.assertEqual(result["summary"], "Commitment due")
        self.assertEqual(len(self.life.pending_messages()), 1)

        self.life.tick(datetime(2026, 11, 24, 10, 1))
        self.assertEqual(len(self.life.pending_messages()), 1)

        later = datetime(2026, 11, 24, 17, 0)
        result = self.life.tick(later)
        self.assertEqual(result["summary"], "Commitment due")

    def test_action_budget_is_optional(self):
        self.life.cfg["max_actions_per_day"] = 1
        first = self.life.tick(self.now)
        self.assertEqual(first["action"], "reflect")
        second = self.life.tick(datetime(2026, 11, 24, 10, 1))
        self.assertEqual(second["action"], "rest")
        self.assertEqual(second["reason"], "daily action budget reached")

    def test_zero_action_budget_means_unlimited(self):
        self.life.cfg["max_actions_per_day"] = 0
        result = None
        for minute in range(5):
            result = self.life.tick(datetime(2026, 11, 24, 10, minute))
        self.assertNotEqual(result.get("reason"), "daily action budget reached")

    def test_quiet_hours_helpers(self):
        self.life.cfg["quiet_hours"] = ["22:00", "08:00"]
        late = datetime(2026, 11, 24, 23, 0)
        self.assertTrue(self.life.in_quiet_hours(late))
        self.assertEqual(self.life.seconds_until_quiet_end(late), 9 * 3600)
        self.assertFalse(
            self.life.in_quiet_hours(datetime(2026, 11, 24, 12, 0))
        )

    def test_self_goal_counter(self):
        self.life.add_goal("Review my notes", created_by="self", now=self.now)
        self.life.add_goal("User goal", now=self.now)
        self.assertEqual(self.life.self_goals_today(self.now), 1)

    def test_goal_add_complete_and_persist(self):
        message = self.life.add_goal("Map the home network", now=self.now)
        self.assertIn("Map the home network", message)
        self.assertEqual(len(self.life.list_goals("active")), 1)
        self.assertEqual(self.life.list_goals("active")[0]["goal_type"], "once")

        goal_id = self.life.list_goals("active")[0]["id"]
        self.life.complete_goal(goal_id)
        self.assertEqual(len(self.life.list_goals("active")), 0)
        self.assertEqual(len(self.life.list_goals("done")), 1)

        second = LifeEngine(self.db, life_config(), now_fn=lambda: self.now)
        self.assertEqual(len(second.list_goals("done")), 1)

    def test_ongoing_goal_type(self):
        self.life.add_goal("Watch the feed", goal_type="ongoing", now=self.now)
        goals = self.life.list_goals("active")
        self.assertEqual(goals[0]["goal_type"], "ongoing")

    def test_pause_persists(self):
        self.life.set_paused(True)
        second = LifeEngine(self.db, life_config(), now_fn=lambda: self.now)
        self.assertTrue(second.is_paused())

    def test_stale_goal_gets_worked(self):
        self.life.tick(self.now)  # first reflection
        self.life.add_goal("Write the satellite pass report", now=self.now)
        later = datetime(2026, 11, 24, 17, 0)
        result = self.life.tick(later)
        self.assertEqual(result["action"], "work")
        self.assertIn("satellite", result["summary"].lower())

    def test_reflection_only_once_per_window(self):
        first = self.life.tick(self.now)
        self.assertEqual(first["action"], "reflect")
        second = self.life.tick(datetime(2026, 11, 24, 10, 1))
        self.assertNotEqual(second["action"], "reflect")

    def test_pending_message_delivery(self):
        self.life.cfg["brief_time"] = "23:00"
        self.life.add_commitment(
            "Check the backup",
            due_at=datetime(2026, 11, 24, 9, 0),
            now=self.now,
        )
        self.life.tick(self.now)
        pending = self.life.pending_messages()
        self.assertEqual(len(pending), 1)
        self.life.mark_delivered(pending[0]["id"])
        self.assertEqual(len(self.life.pending_messages()), 0)

    def test_ilog_and_status(self):
        self.life.add_goal("Test the iLog", now=self.now)
        self.assertIn("Goal added: Test the iLog", self.life.log_text())
        status = self.life.status_text(self.now)
        self.assertIn("GRID Life - status", status)
        self.assertIn("awake", status)
        self.assertIn("1 active", status)


if __name__ == "__main__":
    unittest.main()
