import tempfile
import unittest
from pathlib import Path
from unittest import mock

import grid_agent
from grid_agent import GridOrchestrator, Recaller, Tools


class FakeBackend:
    def __init__(self, reply="NONE"):
        self.reply = reply

    def chat(self, messages, temperature=0.2):
        return self.reply


class FakeMemory:
    def __init__(self, history=None):
        self.history = history or []


class MemoryProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.persona = Path(self.tmp.name) / "grid_persona.md"
        self.refs = Path(self.tmp.name) / "refs"
        self.patches = [
            mock.patch.object(grid_agent, "PERSONA_FILE", str(self.persona)),
            mock.patch.object(grid_agent, "REFS_DIR", str(self.refs)),
        ]
        for patch in self.patches:
            patch.start()
        self.recaller = Recaller(FakeBackend(), None, FakeMemory())

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def test_remember_and_dedupe(self):
        message = self.recaller.remember("Prefers table output")
        self.assertIn("Saved", message)
        self.assertIn("Prefers table output", self.recaller.profile_text())
        again = self.recaller.remember("prefers table output.")
        self.assertIn("Already", again)
        self.assertEqual(self.recaller.profile_text().count("- "), 1)

    def test_refuses_secrets(self):
        message = self.recaller.remember("my api_key=sk-secret123456")
        self.assertIn("won't store", message)
        self.assertEqual(self.recaller._profile_lines(), [])

    def test_build_context_puts_profile_first(self):
        self.recaller.remember("User works on GRID")
        context = self.recaller.build_context("what am I working on?")
        self.assertIn("USER PROFILE", context)
        self.assertIn("User works on GRID", context)
        self.assertLess(context.index("USER PROFILE"), context.index("User works on GRID"))

    def test_forget(self):
        self.recaller.remember("Likes tables")
        self.recaller.remember("Works on GRID")
        message = self.recaller.forget("tables")
        self.assertIn("Removed 1", message)
        self.assertNotIn("Likes tables", self.recaller.profile_text())
        self.assertIn("Works on GRID", self.recaller.profile_text())

    def test_distill_merges_persona(self):
        self.recaller._ingest(
            "PERSONA:\n- Prefers concise answers\nATOMS:\n- A fact\n"
            "SCENARIO: Test: did a thing"
        )
        self.assertIn("Prefers concise answers", self.recaller.profile_text())

    def test_backfill_skips_test_prompts_and_pii(self):
        memory = FakeMemory(
            [
                {"role": "user", "content": "I prefer tables and I work on GRID."},
                {"role": "user", "content": "ping 8.8.8.8"},
                {"role": "assistant", "content": "ok"},
            ]
        )
        recaller = Recaller(
            FakeBackend("- Prefers tables\n- Works on GRID\n- Email me at a@b.com"),
            None,
            memory,
        )
        added = recaller.backfill_profile(batch_size=10)
        self.assertEqual(added, 2)
        profile = recaller.profile_text()
        self.assertIn("Prefers tables", profile)
        self.assertIn("Works on GRID", profile)
        self.assertNotIn("a@b.com", profile)

    def test_backfill_rejects_assistant_identity(self):
        memory = FakeMemory(
            [{"role": "user", "content": "I am testing my GRID setup."}]
        )
        recaller = Recaller(
            FakeBackend(
                "- The user identifies themselves as TinaGrid\n"
                "- Prefers tables"
            ),
            None,
            memory,
        )
        added = recaller.backfill_profile(batch_size=10)
        self.assertEqual(added, 1)
        self.assertNotIn("TinaGrid", recaller.profile_text())
        self.assertIn("Prefers tables", recaller.profile_text())

    def test_clean_fact_strips_markdown(self):
        self.assertEqual(
            Recaller._clean_fact("- *Language:** English"),
            "Language: English",
        )

    def test_capture_remembers_strips_line(self):
        with mock.patch.object(Tools, "recaller", self.recaller):
            cleaned = GridOrchestrator._capture_remembers(
                "Answer.\nREMEMBER: User prefers concise answers."
            )
        self.assertEqual(cleaned, "Answer.")
        self.assertIn("concise", self.recaller.profile_text())

    def test_capture_remembers_strips_fake_tool_header(self):
        with mock.patch.object(Tools, "recaller", self.recaller):
            cleaned = GridOrchestrator._capture_remembers(
                "[Tool: memory_recall]\nInput: user profile\nAnswer."
            )
        self.assertEqual(cleaned, "Answer.")


if __name__ == "__main__":
    unittest.main()
