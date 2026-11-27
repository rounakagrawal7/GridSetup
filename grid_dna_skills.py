"""Validation, application and genome records for DNA Level 2 skill packages."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from grid_skilldocs import NAME_RE, SkillDocManager

BASE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = BASE_DIR / "skills"
DNA_DIR = BASE_DIR / "refs" / "dna"
GENERATIONS_DIR = DNA_DIR / "generations"
STAGING_DIR = DNA_DIR / "staging"

MAX_FILES = 60
MAX_BYTES = 512 * 1024
TEST_TIMEOUT_SECONDS = 20
SAFE_IMPORTS = {
    "base64",
    "binascii",
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "difflib",
    "fractions",
    "functools",
    "hashlib",
    "html",
    "itertools",
    "json",
    "math",
    "random",
    "re",
    "statistics",
    "string",
    "textwrap",
    "typing",
    "unicodedata",
}
BLOCKED_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
BLOCKED_ATTRS = {
    "__builtins__",
    "__code__",
    "__globals__",
    "__subclasses__",
}


class SkillValidationError(ValueError):
    pass


def proposal_dir(proposal_id: str) -> Path:
    if not re.fullmatch(r"prop-[a-f0-9]{12}", str(proposal_id or "")):
        raise SkillValidationError("invalid proposal id")
    return STAGING_DIR / proposal_id


def save_proposal(data: Dict[str, Any]) -> Path:
    path = proposal_dir(str(data["id"])) / "proposal.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_proposal(proposal_id: str) -> Dict[str, Any]:
    path = proposal_dir(proposal_id) / "proposal.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillValidationError(f"proposal not found: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillValidationError("invalid proposal file")
    return data


def remove_applied(
    name: str,
    tools: Any,
    skills_dir: Optional[Path] = None,
) -> None:
    skills_dir = Path(skills_dir or SKILLS_DIR)
    folder = skills_dir / name
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    tool_file = skills_dir / f"{name}.py"
    if tool_file.exists():
        tool_file.unlink()
    if tools is not None and getattr(tools, "skills", None):
        try:
            tools.skills.delete(name)
        except Exception:
            pass
    if tools is not None and getattr(tools, "skilldocs", None) is not None:
        try:
            tools.skilldocs.discover()
        except Exception:
            pass



def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.name.endswith(".pyc"):
            continue
        rows[str(path.relative_to(root)).replace("\\", "/")] = _sha256(path)
    return rows


def find_package(staging: Path) -> Path:
    staging = Path(staging)
    candidates = [
        path.parent
        for path in staging.glob("*/SKILL.md")
        if path.is_file()
    ]
    if len(candidates) != 1:
        raise SkillValidationError(
            f"expected exactly one <name>/SKILL.md, found {len(candidates)}"
        )
    return candidates[0]


def _check_tool_code(tool_file: Path) -> List[str]:
    errors: List[str] = []
    try:
        tree = ast.parse(tool_file.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"tool syntax error: {exc}"]
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "run" not in functions:
        errors.append("tool must define def run(input: str) -> str")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_IMPORTS:
                    errors.append(f"import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in SAFE_IMPORTS:
                errors.append(f"import not allowed: {node.module or '.'}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                errors.append(f"call not allowed: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_ATTRS:
                errors.append(f"attribute not allowed: {node.func.attr}")
        elif isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRS:
            errors.append(f"attribute not allowed: {node.attr}")
    return errors


def _run_tests(package_root: Path, staging: Path, name: str) -> Dict[str, Any]:
    tests_dir = package_root / "tests"
    if not tests_dir.is_dir():
        return {"ok": True, "ran": False, "output": "no tests directory"}
    with tempfile.TemporaryDirectory(prefix="grid-dna-tests-") as tmp:
        temp = Path(tmp)
        copied = temp / "package"
        shutil.copytree(staging, copied)
        tool_file = staging / f"{name}.py"
        if tool_file.is_file():
            shutil.copy2(tool_file, copied / f"{name}.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(copied), str(copied / package_root.name)]
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=str(copied / package_root.name),
                env=env,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "ran": True, "output": "tests timed out"}
        output = (completed.stdout + completed.stderr).strip()
        return {
            "ok": completed.returncode == 0,
            "ran": True,
            "output": output[-8000:],
        }


def validate_package(staging: Path) -> Dict[str, Any]:
    staging = Path(staging)
    errors: List[str] = []
    warnings: List[str] = []
    report: Dict[str, Any] = {
        "ok": False,
        "errors": errors,
        "warnings": warnings,
        "staging": str(staging),
        "files": {},
        "tests": {"ok": True, "ran": False, "output": ""},
    }
    try:
        package_root = find_package(staging)
    except SkillValidationError as exc:
        errors.append(str(exc))
        return report

    name = package_root.name
    report["package_root"] = str(package_root)
    report["name"] = name
    if not NAME_RE.fullmatch(name):
        errors.append(
            "skill folder must use lowercase letters, digits and single hyphens"
        )

    manifest_path = package_root / "manifest.json"
    manifest: Dict[str, Any] = {}
    if not manifest_path.is_file():
        errors.append("manifest.json is required")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"manifest.json is invalid: {exc}")
            manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
        errors.append("manifest.json must be an object")
    report["manifest"] = manifest
    report["kind"] = str(manifest.get("kind") or "procedure").strip().lower()
    report["description"] = str(manifest.get("description") or "").strip()
    if report["kind"] not in ("procedure", "tool"):
        errors.append("manifest kind must be 'procedure' or 'tool'")
    if report["kind"] == "tool" and not name.isidentifier():
        errors.append("tool skill name must be a Python identifier (use underscores)")
    if str(manifest.get("name") or "").strip() != name:
        errors.append("manifest name must match the skill folder")
    deps = manifest.get("dependencies")
    if deps not in (None, []):
        errors.append("dependencies must be empty for Level 2 v0")
    permissions = manifest.get("permissions", [])
    if permissions and not isinstance(permissions, list):
        errors.append("manifest permissions must be a list")

    docs = SkillDocManager([staging]).skills.get(name)
    if docs is None or docs.error:
        errors.append(
            f"SKILL.md invalid: {docs.error if docs else 'not found'}"
        )
    else:
        report["skill_md"] = {
            "description": docs.description,
            "license": docs.license,
            "compatibility": docs.compatibility,
        }

    tool_file = staging / f"{name}.py"
    report["tool_file"] = None
    if report["kind"] == "tool":
        if not tool_file.is_file():
            errors.append(f"tool package must include {name}.py at its root")
        else:
            report["tool_file"] = str(tool_file)
            errors.extend(_check_tool_code(tool_file))
            tests_dir = package_root / "tests"
            if not tests_dir.is_dir() or not any(tests_dir.glob("test_*.py")):
                errors.append("tool packages need at least one test file")
            report["tests"] = _run_tests(package_root, staging, name)
            if not report["tests"]["ok"]:
                errors.append("tool tests failed")
    elif tool_file.exists():
        errors.append("procedure packages must not include an executable .py")

    package_files = _files(package_root)
    files = {
        f"{name}/{relative}": digest
        for relative, digest in package_files.items()
    }
    if tool_file.is_file():
        files[f"../{name}.py"] = _sha256(tool_file)
    report["files"] = files
    if len(files) > MAX_FILES:
        errors.append(f"package has too many files ({len(files)} > {MAX_FILES})")
    total = sum(
        (package_root / relative).stat().st_size
        for relative in package_files
    )
    if total > MAX_BYTES:
        errors.append("package is too large")
    report["ok"] = not errors
    return report


def apply_package(
    report: Dict[str, Any],
    tools: Any,
    skills_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if not report.get("ok"):
        raise SkillValidationError("proposal is not valid")
    skills_dir = Path(skills_dir or SKILLS_DIR)
    skills_dir.mkdir(parents=True, exist_ok=True)
    name = report["name"]
    package_root = Path(report["package_root"])
    dest = skills_dir / name
    if dest.exists():
        raise SkillValidationError(f"skill folder already exists: {dest}")
    tool_file = report.get("tool_file")
    tool_dest = skills_dir / f"{name}.py"
    if tool_file and tool_dest.exists():
        raise SkillValidationError(f"skill tool already exists: {tool_dest}")

    created_tool = False
    try:
        if tool_file:
            if tools is None or not getattr(tools, "skills", None):
                raise SkillValidationError("skill manager is not initialized")
            code = Path(tool_file).read_text(encoding="utf-8")
            desc = report.get("description") or f"DNA skill: {name}"
            result = tools.skills.create(
                name,
                desc,
                "varies (see SKILL.md)",
                code,
            )
            if str(result).lower().startswith("error"):
                raise SkillValidationError(result)
            created_tool = True
        shutil.copytree(package_root, dest)
        if hasattr(tools, "skilldocs") and tools.skilldocs is not None:
            tools.skilldocs.discover()
    except Exception:
        if created_tool and tools is not None and getattr(tools, "skills", None):
            try:
                tools.skills.delete(name)
            except Exception:
                pass
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise

    return {
        "ok": True,
        "name": name,
        "kind": report.get("kind"),
        "folder": str(dest),
        "tool": str(tool_dest) if tool_file else "",
    }


def verify_applied(
    report: Dict[str, Any],
    tools: Any,
    skills_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    skills_dir = Path(skills_dir or SKILLS_DIR)
    name = report.get("name", "")
    dest = skills_dir / name
    errors: List[str] = []
    if not (dest / "SKILL.md").is_file():
        errors.append(f"missing {dest / 'SKILL.md'}")
    if not (dest / "manifest.json").is_file():
        errors.append(f"missing {dest / 'manifest.json'}")
    if report.get("kind") == "tool":
        tool_dest = skills_dir / f"{name}.py"
        if not tool_dest.is_file():
            errors.append(f"missing {tool_dest}")
        if tools is None or name not in getattr(tools, "registry", {}):
            errors.append("tool is not registered")
    else:
        docs = getattr(tools, "skilldocs", None) if tools is not None else None
        if docs is None or name not in getattr(docs, "skills", {}):
            errors.append("SKILL.md skill is not discovered")
    actual = _files(dest)
    expected = {
        key.split("/", 1)[1]: value
        for key, value in (report.get("files") or {}).items()
        if key.startswith(f"{name}/")
    }
    for rel, digest in expected.items():
        if actual.get(rel) != digest:
            errors.append(f"hash mismatch or missing: {rel}")
    if report.get("kind") == "tool":
        tool_dest = skills_dir / f"{name}.py"
        if tool_dest.is_file():
            staged_tool = Path(report.get("tool_file") or "")
            if staged_tool.is_file():
                staged_text = staged_tool.read_text(encoding="utf-8").strip()
                applied_text = tool_dest.read_text(encoding="utf-8").strip()
                if staged_text != applied_text:
                    errors.append("tool file content mismatch")
            else:
                expected_tool = (report.get("files") or {}).get(f"../{name}.py")
                if expected_tool and _sha256(tool_dest) != expected_tool:
                    errors.append("tool file hash mismatch")
    return {"ok": not errors, "errors": errors, "checks": actual}


def write_genome(
    report: Dict[str, Any],
    proposal_id: str,
    room_id: str,
    approver: str,
    applied: Dict[str, Any],
    verification: Dict[str, Any],
    generations_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    generations_dir = Path(generations_dir or GENERATIONS_DIR)
    generations_dir.mkdir(parents=True, exist_ok=True)
    existing = []
    for path in generations_dir.glob("*/genome.json"):
        try:
            value = int(path.parent.name)
            existing.append(value)
        except ValueError:
            continue
    generation = (max(existing) if existing else 0) + 1
    parent = ""
    if existing:
        parent_path = generations_dir / str(max(existing)) / "genome.json"
        try:
            parent = _sha256(parent_path)
        except OSError:
            parent = ""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        commit = ""
    skills = {}
    skills_root = Path(applied.get("folder") or "")
    if skills_root.is_dir():
        skills = _files(skills_root)
    tool_path = applied.get("tool") or ""
    if tool_path and Path(tool_path).is_file():
        skills["tool.py"] = _sha256(Path(tool_path))
    genome = {
        "generation": generation,
        "parent": parent,
        "created_at": _now(),
        "proposal_id": proposal_id,
        "room_id": room_id,
        "approver": approver,
        "git_commit": commit,
        "skill": {
            "name": report.get("name"),
            "kind": report.get("kind"),
            "files": skills,
        },
        "verification": {
            "ok": bool(verification.get("ok")),
            "errors": verification.get("errors", []),
        },
        "tests": report.get("tests", {}),
    }
    path = generations_dir / str(generation) / "genome.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(genome, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "generation": generation,
        "path": str(path),
        "hash": _sha256(path),
        "genome": genome,
    }
