import unittest
from pathlib import Path

import grid_agent
from grid_agent import CAPABILITY_GROUPS


ROOT = Path(__file__).resolve().parent.parent


class ConsistencyTests(unittest.TestCase):
    def test_capability_groups_are_sixteen_and_complete(self):
        self.assertEqual(len(CAPABILITY_GROUPS), 16)
        self.assertEqual(len(set(CAPABILITY_GROUPS)), 16)
        self.assertIn("Satellite", CAPABILITY_GROUPS)
        self.assertIn("Microcontroller", CAPABILITY_GROUPS)

    def test_prompt_and_banner_use_the_shared_list(self):
        source = (ROOT / "grid_agent.py").read_text(encoding="utf-8")
        self.assertIn("group_line = \" | \".join", source)
        self.assertIn("len(CAPABILITY_GROUPS)", source)
        self.assertNotIn("14 categories", source)

    def test_readme_counts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("82-tool reconnaissance stack", readme)
        self.assertIn("82-tool registry", readme)
        self.assertIn("16 capability groups", readme)
        self.assertNotIn("80+ built-in tools", readme)
        self.assertNotIn("70+ built-in tools", readme)

    def test_changelog_status(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## v3.0 - GRID Life", changelog)
        self.assertNotIn("GRID Life (in progress)", changelog)

    def test_adr_status(self):
        adr = (ROOT / "docs" / "ADR-0001-grid-v3.md").read_text(encoding="utf-8")
        self.assertIn("shipped in v3.0", adr)

    def test_manual_has_v3_addendum(self):
        try:
            import docx
        except ImportError:
            self.skipTest("python-docx not installed")
        doc = docx.Document(ROOT / "GRID_Tools_Test_Guide.docx")
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("GRID v3 Addendum", text)
        self.assertIn("All 82 tools documented", text)
        self.assertNotIn("All 81 tools documented", text)
        for token in ("/life", "MCP", "skill_search", "document_read", "OpenCode"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
