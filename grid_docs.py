"""Local document reading for GRID v3.

MarkItDown is optional. Text, Markdown, HTML, CSV, JSON, Excel and DOCX have
lightweight fallbacks so the tool still works before the optional install.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_BYTES = 20 * 1024 * 1024
MAX_CHARS = 16_000
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".log", ".py", ".ini", ".cfg", ".yaml", ".yml"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_html(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_read_text(path), "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return _read_text(path)


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    parts = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            parts.append(node.text)
        elif node.tag.endswith("}p"):
            parts.append("\n")
    return " ".join(parts).replace(" \n ", "\n").strip()


def _read_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    lines = []
    try:
        for sheet in workbook.worksheets:
            lines.append(f"## {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if value is None else str(value) for value in row]
                if any(cells):
                    lines.append(" | ".join(cells))
    finally:
        workbook.close()
    return "\n".join(lines)


def _fallback(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return _read_text(path)
    if suffix in (".html", ".htm"):
        return _read_html(path)
    if suffix == ".csv":
        return _read_text(path)
    if suffix == ".json":
        data = json.loads(_read_text(path))
        return json.dumps(data, indent=2, ensure_ascii=False)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    raise ValueError(
        f"No local fallback for '{suffix or 'file'}'. "
        "Install MarkItDown: pip install 'markitdown[pdf,docx,xlsx,pptx]'"
    )


def document_read(input_str: str) -> str:
    raw = (input_str or "").strip().strip('"').strip("'")
    if not raw:
        return "Usage: document_read <path>"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return f"File not found: {path}"
    if not path.is_file():
        return f"Not a file: {path}"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"Could not stat file: {exc}"
    if size > MAX_BYTES:
        return f"Error: file is too large ({size / 1024 / 1024:.1f} MB; limit 20 MB)."

    markitdown_error = ""
    try:
        from markitdown import MarkItDown

        result = MarkItDown().convert(str(path))
        text = result.text_content or ""
    except ImportError:
        try:
            text = _fallback(path)
        except Exception as exc:
            return str(exc)
    except Exception as exc:
        markitdown_error = str(exc)
        try:
            text = _fallback(path)
        except Exception:
            return f"Could not read {path.name}: {markitdown_error}"

    text = text.strip()
    if not text:
        return f"{path.name}: no extractable text."
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n\n... (truncated; {len(text)} characters total)"
    header = f"Document: {path.name} ({size} bytes)"
    if markitdown_error:
        header += f"\nMarkItDown fallback used: {markitdown_error[:200]}"
    return header + "\n\n" + text
