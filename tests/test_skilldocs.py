import tempfile
import unittest
from pathlib import Path

from grid_skilldocs import SkillDocManager


VALID = """---
name: test-skill
description: A test skill for GRID. Use when testing skills.
license: MIT
metadata:
  author: test
---
# Test Skill

Use the test procedure.
"""


class SkillDocTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        skill = self.root / "test-skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text(VALID, encoding="utf-8")
        (skill / "references" / "notes.md").write_text(
            "reference notes", encoding="utf-8"
        )
        (self.root / "secret.txt").write_text("outside", encoding="utf-8")
        self.manager = SkillDocManager(roots=[self.root])

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_skill_is_listed_and_loaded(self):
        self.assertIn("test-skill", self.manager.summary())
        loaded = self.manager.load_text("test-skill")
        self.assertIn("Skill: test-skill", loaded)
        self.assertIn("Use the test procedure.", loaded)
        self.assertIn("License: MIT", loaded)

    def test_search(self):
        self.assertIn("test-skill", self.manager.search_text("testing"))
        self.assertIn("No SKILL.md skills matched", self.manager.search_text("zzz"))

    def test_read_reference(self):
        text = self.manager.read_text("test-skill/references/notes.md")
        self.assertEqual(text, "reference notes")

    def test_path_traversal_is_blocked(self):
        text = self.manager.read_text("test-skill/../secret.txt")
        self.assertIn("must stay inside", text)

    def test_invalid_name_is_reported_and_hidden(self):
        bad = self.root / "Bad_Name"
        bad.mkdir()
        (bad / "SKILL.md").write_text(
            """---
name: Bad_Name
description: bad
---
body
""",
            encoding="utf-8",
        )
        manager = SkillDocManager(roots=[self.root])
        self.assertNotIn("Bad_Name", manager.summary())
        self.assertIn("FAIL", manager.validate_text())
        self.assertIn("invalid", manager.load_text("Bad_Name").lower())

    def test_name_must_match_folder(self):
        other = self.root / "other-folder"
        other.mkdir()
        (other / "SKILL.md").write_text(
            """---
name: test-skill
description: mismatch
---
body
""",
            encoding="utf-8",
        )
        manager = SkillDocManager(roots=[self.root])
        self.assertIn("FAIL other-folder", manager.validate_text())

    def test_missing_frontmatter(self):
        plain = self.root / "plain-skill"
        plain.mkdir()
        (plain / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
        manager = SkillDocManager(roots=[self.root])
        self.assertIn("FAIL plain-skill", manager.validate_text())

    def test_missing_skill(self):
        self.assertIn("not found", self.manager.load_text("missing").lower())


if __name__ == "__main__":
    unittest.main()
