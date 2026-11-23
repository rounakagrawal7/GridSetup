import tempfile
import unittest
from pathlib import Path

from grid_docs import document_read


class DocumentReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_text_document(self):
        path = self._write("notes.txt", "GRID document text")
        result = document_read(str(path))
        self.assertIn("Document: notes.txt", result)
        self.assertIn("GRID document text", result)

    def test_html_document(self):
        path = self._write(
            "page.html",
            "<html><body><h1>Hello</h1><script>bad()</script><p>World</p></body></html>",
        )
        result = document_read(str(path))
        self.assertIn("Hello", result)
        self.assertIn("World", result)
        self.assertNotIn("bad()", result)

    def test_html_fallback_without_bs4_or_markitdown(self):
        path = self._write(
            "fallback.html",
            "<html><body><h1>Hello</h1><script>bad()</script><p>World</p></body></html>",
        )
        import sys

        old_bs4 = sys.modules.get("bs4")
        old_md = sys.modules.get("markitdown")
        sys.modules["bs4"] = None
        sys.modules["markitdown"] = None
        try:
            result = document_read(str(path))
            self.assertIn("Hello", result)
            self.assertIn("World", result)
            self.assertNotIn("bad()", result)
        finally:
            if old_bs4 is None:
                sys.modules.pop("bs4", None)
            else:
                sys.modules["bs4"] = old_bs4
            if old_md is None:
                sys.modules.pop("markitdown", None)
            else:
                sys.modules["markitdown"] = old_md

    def test_json_document(self):
        path = self._write("data.json", '{"name": "grid", "ok": true}')
        result = document_read(str(path))
        self.assertIn('"name": "grid"', result)

    def test_csv_document(self):
        path = self._write("rows.csv", "name,score\na,1\nb,2\n")
        result = document_read(str(path))
        self.assertIn("name", result)
        self.assertIn("score", result)
        self.assertIn("a", result)

    def test_missing_file(self):
        result = document_read(str(self.root / "missing.txt"))
        self.assertIn("File not found", result)

    def test_directory_is_rejected(self):
        result = document_read(str(self.root))
        self.assertIn("Not a file", result)

    def test_empty_document(self):
        path = self._write("empty.txt", "")
        result = document_read(str(path))
        self.assertIn("no extractable text", result)

    def test_tool_is_registered(self):
        import grid_agent

        self.assertIn("document_read", grid_agent.Tools.registry)
        self.assertEqual(len(grid_agent.Tools.registry), 80)


if __name__ == "__main__":
    unittest.main()
