"""
GRID v2 — Dynamic Skill Manager
File-based skills with def run(input) interface, auto-registration as Tools,
JSON schema support, skill chaining, and LLM-driven creation.
"""

import json
import os
import importlib.util
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any

SKILLS_DIR = Path(__file__).parent / "skills"
INDEX_FILE = SKILLS_DIR / "skills_index.json"

class SkillManager:
    def __init__(self):
        self.skills: Dict[str, dict] = {}
        SKILLS_DIR.mkdir(exist_ok=True)
        self._load_index()

    # ── index persistence ──────────────────────────────────────

    def _load_index(self):
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                self.skills = data.get("skills", {})
            except (json.JSONDecodeError, KeyError):
                self.skills = {}
        else:
            self.skills = {}

    def _save_index(self):
        INDEX_FILE.write_text(
            json.dumps({"skills": self.skills}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── registration with Tools ────────────────────────────────

    def register_all(self):
        from grid_agent import Tools
        for name, info in self.skills.items():
            if name in Tools.registry:
                continue
            fn = self._make_runner(name)
            desc = info.get("description", "")
            input_desc = info.get("input_desc", "varies")
            Tools._reg(name, fn, desc, input_desc)
        Tools.SCHEMA = Tools._build_schema()

    def unregister(self, name: str):
        from grid_agent import Tools
        Tools.registry.pop(name, None)
        Tools.enabled.discard(name)
        Tools.SCHEMA = Tools._build_schema()

    # ── skill runner factory ───────────────────────────────────

    def _make_runner(self, name: str):
        mod_path = SKILLS_DIR / f"{name}.py"

        def runner(input_str: str) -> str:
            if not mod_path.exists():
                return f"Skill '{name}' file not found at {mod_path}"
            try:
                spec = importlib.util.spec_from_file_location(f"skill_{name}", mod_path)
                if spec is None or spec.loader is None:
                    return f"Error: could not load skill module for '{name}'"
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f"skill_{name}"] = mod
                spec.loader.exec_module(mod)
                if not hasattr(mod, "run"):
                    return f"Error: skill '{name}' has no run(input) function"
                return mod.run(input_str)
            except Exception as e:
                return f"Error executing skill '{name}': {e}"

        return runner

    # ── CRUD ───────────────────────────────────────────────────

    def create(self, name: str, description: str, input_desc: str, code: str,
               schema: Optional[dict] = None) -> str:
        name = name.strip().lower().replace(" ", "_")
        if not name or not name.isidentifier():
            return "Error: skill name must be a valid Python identifier"

        if name in self.skills:
            return f"Error: skill '{name}' already exists"

        mod_path = SKILLS_DIR / f"{name}.py"
        if mod_path.exists():
            return f"Error: file {mod_path} already exists"

        try:
            compile(code, f"<skill {name}>", "exec")
        except SyntaxError as e:
            return f"Error: syntax error in skill code:\n{e}"

        code = code.strip()
        if "def run(" not in code:
            return "Error: skill code must define a `def run(input: str) -> str:` function"

        mod_path.write_text(code, encoding="utf-8")

        entry = {
            "description": description,
            "input_desc": input_desc,
            "enabled": True,
        }
        if schema:
            entry["schema"] = schema
        self.skills[name] = entry
        self._save_index()

        from grid_agent import Tools
        fn = self._make_runner(name)
        Tools._reg(name, fn, description, input_desc)
        Tools.SCHEMA = Tools._build_schema()

        return f"Skill '{name}' created and registered."

    def delete(self, name: str) -> str:
        if name not in self.skills:
            return f"Error: skill '{name}' not found"
        mod_path = SKILLS_DIR / f"{name}.py"
        if mod_path.exists():
            mod_path.unlink()
        self.skills.pop(name, None)
        self._save_index()
        self.unregister(name)
        return f"Skill '{name}' deleted."

    def toggle(self, name: str) -> str:
        from grid_agent import Tools
        if name not in self.skills:
            return f"Error: skill '{name}' not found"
        current = self.skills[name].get("enabled", True)
        self.skills[name]["enabled"] = not current
        self._save_index()
        if not current:
            Tools.enabled.add(name)
            return f"Skill '{name}' enabled."
        else:
            Tools.enabled.discard(name)
            return f"Skill '{name}' disabled."

    def get_code(self, name: str) -> Optional[str]:
        mod_path = SKILLS_DIR / f"{name}.py"
        if mod_path.exists():
            return mod_path.read_text(encoding="utf-8")
        return None

    def edit_code(self, name: str, new_code: str) -> str:
        if name not in self.skills:
            return f"Error: skill '{name}' not found"
        try:
            compile(new_code, f"<skill {name}>", "exec")
        except SyntaxError as e:
            return f"Error: syntax error:\n{e}"
        mod_path = SKILLS_DIR / f"{name}.py"
        mod_path.write_text(new_code, encoding="utf-8")
        return f"Skill '{name}' updated."

    def list_skills(self) -> List[Dict[str, Any]]:
        result = []
        for name, info in self.skills.items():
            result.append({
                "name": name,
                "description": info.get("description", ""),
                "input_desc": info.get("input_desc", ""),
                "enabled": info.get("enabled", True),
                "has_schema": "schema" in info,
            })
        return sorted(result, key=lambda x: x["name"])

    # ── skill chaining helper ──────────────────────────────────

    @staticmethod
    def call_skill(name: str, input_str: str) -> str:
        from grid_agent import Tools
        if name not in Tools.enabled:
            return f"Skill '{name}' is not enabled"
        return Tools.execute(name, input_str)


# ── standalone convenience ─────────────────────────────────────

_skills_mgr: Optional[SkillManager] = None

def get_manager() -> SkillManager:
    global _skills_mgr
    if _skills_mgr is None:
        _skills_mgr = SkillManager()
    return _skills_mgr
