import json
import tempfile
import unittest
from pathlib import Path

from grid_dna_skills import (
    SkillValidationError,
    apply_package,
    validate_package,
    verify_applied,
)
from grid_skilldocs import SkillDocManager


def write_skill(root: Path, name: str, kind: str = "procedure", code: str = ""):
    package = root / name
    (package / "tests").mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: A test skill\n"
        "license: MIT\n"
        "---\n\n"
        "Use this skill for tests.\n",
        encoding="utf-8",
    )
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "0.1.0",
                "kind": kind,
                "description": "A test skill",
                "permissions": [],
                "dependencies": [],
            }
        ),
        encoding="utf-8",
    )
    if kind == "tool":
        (root / f"{name}.py").write_text(
            code or "def run(input: str) -> str:\n    return input\n",
            encoding="utf-8",
        )
        (package / "tests" / "test_skill.py").write_text(
            f"import unittest\n"
            f"from {name} import run\n\n"
            f"class SkillTests(unittest.TestCase):\n"
            f"    def test_run(self):\n"
            f"        self.assertEqual(run('ok'), 'ok')\n",
            encoding="utf-8",
        )
    return package


class FakeSkillManager:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.deleted = []

    def create(self, name, description, input_desc, code, schema=None):
        (self.skills_dir / f"{name}.py").write_text(code, encoding="utf-8")
        return f"Skill '{name}' created and registered."

    def delete(self, name):
        self.deleted.append(name)
        path = self.skills_dir / f"{name}.py"
        if path.exists():
            path.unlink()
        return "deleted"


class FakeTools:
    def __init__(self, skills_dir: Path):
        self.skilldocs = SkillDocManager([skills_dir])
        self.skills = FakeSkillManager(skills_dir)
        self.registry = {}


class DnaSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.staging = self.root / "staging"
        self.skills = self.root / "skills"
        self.staging.mkdir()
        self.skills.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_procedure_validate_apply_verify(self):
        write_skill(self.staging, "hello-procedure")
        report = validate_package(self.staging)
        self.assertTrue(report["ok"], report["errors"])
        tools = FakeTools(self.skills)
        applied = apply_package(report, tools, self.skills)
        self.assertTrue(applied["ok"])
        verification = verify_applied(report, tools, self.skills)
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertTrue((self.skills / "hello-procedure" / "SKILL.md").is_file())

    def test_tool_validate_runs_tests(self):
        write_skill(self.staging, "hello_tool", "tool")
        report = validate_package(self.staging)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["tests"]["ran"])
        self.assertTrue(report["tests"]["ok"])

    def test_tool_static_scan_rejects_os(self):
        write_skill(
            self.staging,
            "bad_tool",
            "tool",
            "import os\n\ndef run(input: str) -> str:\n    return os.getcwd()\n",
        )
        report = validate_package(self.staging)
        self.assertFalse(report["ok"])
        self.assertTrue(any("import not allowed" in e for e in report["errors"]))

    def test_tool_tests_must_exist(self):
        package = write_skill(self.staging, "no_tests", "tool")
        (package / "tests" / "test_skill.py").unlink()
        report = validate_package(self.staging)
        self.assertFalse(report["ok"])
        self.assertTrue(any("test file" in e for e in report["errors"]))

    def test_apply_refuses_existing_skill(self):
        write_skill(self.staging, "taken")
        (self.skills / "taken").mkdir()
        report = validate_package(self.staging)
        with self.assertRaises(SkillValidationError):
            apply_package(report, FakeTools(self.skills), self.skills)


if __name__ == "__main__":
    unittest.main()
