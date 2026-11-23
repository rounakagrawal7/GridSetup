"""Optional external tool wrappers for GRID v3.

These do not bundle anything. If the binary is missing, the tool explains how
to install it. Every call still goes through the permission policy.
"""

from __future__ import annotations

import shutil
import subprocess


def _which(*names: str) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def _run(command, timeout: int) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s."
    except Exception as exc:
        return f"Error: {exc}"
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        return f"Exit code {result.returncode}:\n{error or output}"
    return output or "(no output)"


def sherlock_scan(username: str) -> str:
    username = (username or "").strip().lstrip("@")
    if not username:
        return "Usage: sherlock_scan <username>"
    binary = _which("sherlock")
    if not binary:
        return (
            "Sherlock is not installed. Run: pip install sherlock-project\n"
            "Then retry: sherlock_scan <username>"
        )
    return _run(
        [binary, "--json", "--print-found", "--timeout", "15", username],
        timeout=180,
    )


def nuclei_scan(spec: str) -> str:
    raw = (spec or "").strip()
    if not raw.lower().startswith("authorized "):
        return (
            "Usage: nuclei_scan authorized <url-or-host>\n"
            "Only run this against systems you own or have written permission to test."
        )
    target = raw[len("authorized "):].strip()
    if not target:
        return "Usage: nuclei_scan authorized <url-or-host>"
    binary = _which("nuclei")
    if not binary:
        return (
            "Nuclei is not installed. Download it from "
            "https://github.com/projectdiscovery/nuclei/releases and put it on PATH."
        )
    return _run(
        [
            binary,
            "-u", target,
            "-severity", "low,medium,high,critical",
            "-silent",
            "-no-color",
            "-timeout", "10",
            "-retries", "1",
        ],
        timeout=300,
    )


def pio_build(project_path: str) -> str:
    project_path = (project_path or "").strip()
    if not project_path:
        return "Usage: pio_build <project-directory>"
    binary = _which("pio", "platformio")
    if not binary:
        return "PlatformIO is not installed. Run: pip install platformio"
    return _run([binary, "run", "-d", project_path], timeout=600)
