"""Agent Skills (SKILL.md) loader for GRID v3.

A skill is a folder with a SKILL.md file and optional scripts/, references/
and assets/ content. GRID loads only the name and description into the prompt;
the body is read on demand through skill_load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


NAME_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
MAX_SKILL_BYTES = 256 * 1024
MAX_READ_BYTES = 128 * 1024
MAX_LOAD_CHARS = 16_000

BASE_DIR = Path(__file__).parent
DEFAULT_ROOTS = [BASE_DIR / "skills", BASE_DIR / "skill_library"]


@dataclass
class SkillDoc:
    name: str
    description: str
    root: Path
    skill_file: Path
    source: str
    license: str = ""
    compatibility: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    allowed_tools: str = ""
    error: str = ""


class SkillDocManager:
    def __init__(self, roots: Optional[List[Path]] = None):
        self.roots = [Path(root) for root in (roots or DEFAULT_ROOTS)]
        self.skills: Dict[str, SkillDoc] = {}
        self.discover()

    def discover(self) -> Dict[str, SkillDoc]:
        self.skills = {}
        for index, root in enumerate(self.roots):
            source = "user" if index == 0 else "builtin"
            if not root.exists():
                continue
            for skill_file in sorted(root.glob("*/SKILL.md")):
                doc = self._parse(skill_file, source)
                key = skill_file.parent.name
                if key in self.skills:
                    continue
                self.skills[key] = doc
        return self.skills

    def _parse(self, skill_file: Path, source: str) -> SkillDoc:
        folder = skill_file.parent.name
        doc = SkillDoc(
            name=folder,
            description="",
            root=skill_file.parent,
            skill_file=skill_file,
            source=source,
        )
        try:
            raw_text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            doc.error = f"cannot read SKILL.md: {exc}"
            return doc
        if len(raw_text.encode("utf-8")) > MAX_SKILL_BYTES:
            doc.error = "SKILL.md is too large (over 256 KB)"
            return doc
        if not raw_text.startswith("---"):
            doc.error = "missing YAML frontmatter (SKILL.md must start with ---)"
            return doc

        parts = raw_text.split("---", 2)
        if len(parts) < 3:
            doc.error = "unterminated YAML frontmatter"
            return doc
        try:
            data = yaml.safe_load(parts[1]) or {}
        except Exception as exc:
            doc.error = f"invalid YAML: {exc}"
            return doc
        if not isinstance(data, dict):
            doc.error = "YAML frontmatter must be a mapping"
            return doc

        name = str(data.get("name") or "").strip()
        description = str(data.get("description") or "").strip()
        license_name = str(data.get("license") or "").strip()
        compatibility = str(data.get("compatibility") or "").strip()
        allowed_tools = str(data.get("allowed-tools") or "").strip()
        metadata = data.get("metadata") or {}

        errors = []
        if not name:
            errors.append("name is required")
        elif len(name) > 64:
            errors.append("name must be 64 characters or fewer")
        elif not NAME_RE.match(name):
            errors.append("name must use lowercase letters, digits and single hyphens")
        elif name != folder:
            errors.append(f"name '{name}' must match folder '{folder}'")
        if not description:
            errors.append("description is required")
        elif len(description) > 1024:
            errors.append("description must be 1024 characters or fewer")
        if compatibility and len(compatibility) > 500:
            errors.append("compatibility must be 500 characters or fewer")
        if metadata and not isinstance(metadata, dict):
            errors.append("metadata must be a mapping")
        elif isinstance(metadata, dict):
            for key, value in metadata.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    errors.append("metadata keys and values must be strings")
                    break

        doc.name = name or folder
        doc.description = description
        doc.license = license_name
        doc.compatibility = compatibility
        doc.metadata = {
            str(key): str(value)
            for key, value in (metadata.items() if isinstance(metadata, dict) else [])
        }
        doc.allowed_tools = allowed_tools
        doc.error = "; ".join(errors)
        return doc

    def valid(self) -> List[SkillDoc]:
        return [doc for doc in self.skills.values() if not doc.error]

    def summary(self, query: str = "", limit: int = 30) -> str:
        docs = self.valid()
        tokens = [token for token in re.split(r"[^\w-]+", query.lower()) if token]
        if tokens:
            docs = [
                doc
                for doc in docs
                if any(
                    token in doc.name.lower() or token in doc.description.lower()
                    for token in tokens
                )
            ]
        docs = docs[: max(1, int(limit))]
        if not docs:
            return ""
        lines = []
        for doc in docs:
            lines.append(f"- {doc.name}: {doc.description} [{doc.source}]")
        return "\n".join(lines)

    def search_text(self, query: str = "") -> str:
        summary = self.summary(query)
        if not summary:
            if query:
                return f"No SKILL.md skills matched '{query}'."
            return "No SKILL.md skills found. Add a skill folder under skill_library/ or skills/."
        return "Skills (load with skill_load <name>):\n" + summary

    def load_text(self, name: str) -> str:
        doc = self.skills.get((name or "").strip())
        if doc is None:
            return f"Skill '{name}' not found. Use skill_search <query> to find one."
        if doc.error:
            return f"Skill '{doc.name}' is invalid: {doc.error}"
        try:
            text = doc.skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            return f"Could not read skill '{doc.name}': {exc}"
        body = text.split("---", 2)[2].strip() if text.startswith("---") else text
        header = [
            f"Skill: {doc.name}",
            f"Source: {doc.source}",
            f"Description: {doc.description}",
        ]
        if doc.license:
            header.append(f"License: {doc.license}")
        if doc.compatibility:
            header.append(f"Compatibility: {doc.compatibility}")
        header.append("")
        content = "\n".join(header) + body
        if len(content) > MAX_LOAD_CHARS:
            content = content[:MAX_LOAD_CHARS] + "\n\n... (skill truncated; use skill_read for references)"
        return content

    def read_text(self, spec: str) -> str:
        raw = (spec or "").strip()
        if "/" not in raw:
            return "Usage: skill_read <skill-name>/<relative-path>"
        name, relative = raw.split("/", 1)
        doc = self.skills.get(name.strip())
        if doc is None:
            return f"Skill '{name.strip()}' not found."
        if doc.error:
            return f"Skill '{doc.name}' is invalid: {doc.error}"
        try:
            root = doc.root.resolve()
            target = (doc.root / relative).resolve()
        except OSError as exc:
            return f"Could not resolve path: {exc}"
        if target != root and root not in target.parents:
            return "Error: path must stay inside the skill folder."
        if not target.is_file():
            return f"File not found: {relative}"
        try:
            if target.stat().st_size > MAX_READ_BYTES:
                return "Error: referenced file is too large (over 128 KB)."
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "Error: referenced file is not UTF-8 text."
        except OSError as exc:
            return f"Could not read file: {exc}"

    def validate_text(self) -> str:
        if not self.skills:
            return "No SKILL.md files found."
        lines = ["SKILL.md validation"]
        for doc in sorted(self.skills.values(), key=lambda item: item.name):
            label = doc.skill_file.parent.name
            if doc.error:
                lines.append(f"  FAIL {label}: {doc.error}")
            else:
                lines.append(f"  PASS {label} [{doc.source}]")
        return "\n".join(lines)
