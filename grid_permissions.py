"""Permission policy for autonomous GRID actions.

The model proposes a tool; this module decides whether it may run. Chat remains
unchanged unless a policy is installed by the awake runner.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Set, Tuple


READ_ONLY: Set[str] = {
    "db_analytics", "db_query", "dns_lookup", "document_read", "dork", "file_search",
    "get_cwd", "list_directory", "list_skills", "read_file",
    "skill_load", "skill_read", "skill_search", "memory_recall",
    # memory_add writes only the user profile and is explicitly user-requested.
    "memory_add",
    "mcp_servers", "mcp_tools", "memory_status", "netstat", "osint",
    "pb_status", "ping", "ref_read", "satellite", "screen_res",
    "system_info", "table", "telegram_status",
    "weather", "web_fetch", "web_search", "youtube_transcript",
}

SENSITIVE_READ: Set[str] = {
    "analyze_image", "camera_check", "compare_faces", "detect_faces",
    "screenshot", "screenshot_ocr", "video_analyze", "webcam",
}

LOCAL_WRITE: Set[str] = {
    "create_directory", "ctf", "game", "save_skill", "write_file",
}

EXTERNAL: Set[str] = {
    "email_send", "gcal", "ghostcam", "gsheet", "http_request", "mcp_call",
    "sherlock_scan",
    "nc_banner_grab", "nc_connect", "nc_scan", "nc_transfer", "nmap_scan",
    "pb_sync", "pb_upload", "social", "telegram_send",
}

HARDWARE: Set[str] = {
    "micro", "radio",
}

DANGEROUS: Set[str] = {
    "delete_file", "delete_skill", "mouse_click", "mouse_move",
    "mouse_scroll", "nc_chat", "nc_listen", "nc_proxy", "press_keys",
    "process_manager", "run_code", "run_command", "type_text",
    "nuclei_scan", "pio_build", "rea",
}

RISK_LABELS = {
    "read": "read-only",
    "sensitive": "private data (screen/camera)",
    "local_write": "writes local files",
    "external": "sends data or acts on the network",
    "hardware": "controls attached hardware",
    "dangerous": "can run code or change the machine",
    "confirm": "unclassified; confirm first",
}


def classify_tool(tool_name: str) -> str:
    """Return the risk class for a tool. Unknown tools are conservative."""
    name = (tool_name or "").strip().lower()
    if name in DANGEROUS:
        return "dangerous"
    if name in HARDWARE:
        return "hardware"
    if name in EXTERNAL:
        return "external"
    if name in LOCAL_WRITE:
        return "local_write"
    if name in SENSITIVE_READ:
        return "sensitive"
    if name in READ_ONLY:
        return "read"
    return "confirm"


SOCIAL_READ_COMMANDS = {
    "help", "history", "summary", "digest", "status_report", "whats_up",
    "analyze", "analysis", "report", "stats", "trend", "progress",
    "timeline", "timeseries", "feed", "posts", "post", "comments",
    "search", "profile", "submolts", "agents", "persona", "status",
}


def social_is_read_only(tool_input: str) -> bool:
    """Social reads (history/feed/search/post lookup) should not need approval."""
    text = re.sub(
        r"^(?:social|moltbook)\s+", "", str(tool_input or "").strip(), flags=re.I
    )
    command, _, args = text.partition(" ")
    command = command.lower()
    if command == "persona":
        sub = args.strip().lower()
        return not (sub == "clear" or sub.startswith("set "))
    if command == "post":
        return "|" not in args
    return command in SOCIAL_READ_COMMANDS


class PermissionPolicy:
    """Ask/auto/read-only policy with per-session approvals.

    config:
        mode: "ask" | "auto" | "read_only"
        auto_approve: [tool names]
        deny: [tool names]
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        approval_callback: Optional[Callable[[str, str, str], Any]] = None,
    ):
        config = config or {}
        self.mode = str(config.get("mode", "ask")).strip().lower()
        if self.mode not in ("ask", "auto", "read_only"):
            self.mode = "ask"
        self.auto_approve = {
            str(name).strip().lower()
            for name in (config.get("auto_approve") or [])
            if str(name).strip()
        }
        self.deny = {
            str(name).strip().lower()
            for name in (config.get("deny") or [])
            if str(name).strip()
        }
        self.approval_callback = approval_callback
        self.session_approvals: Set[str] = set()

    def describe(self, tool_name: str) -> str:
        return RISK_LABELS.get(classify_tool(tool_name), RISK_LABELS["confirm"])

    def allow(self, tool_name: str, tool_input: str = "") -> Tuple[bool, str]:
        name = (tool_name or "").strip().lower()
        if not name:
            return False, "empty tool name"
        if name in self.deny:
            return False, "denied by permissions.deny"
        if name in self.auto_approve or name in self.session_approvals:
            return True, "auto-approved"

        risk = classify_tool(name)
        if name == "social" and social_is_read_only(tool_input):
            risk = "read"
        if risk == "read":
            return True, "read-only"
        if self.mode == "read_only":
            return False, f"{risk} blocked in read-only mode"
        if self.mode == "auto" and risk in ("local_write", "external", "hardware"):
            return True, f"auto mode allows {risk}"
        if self.approval_callback is None:
            return False, f"{risk} requires approval and no approver is attached"

        answer = self.approval_callback(name, tool_input, risk)
        if answer in (True, "y", "yes", "allow", "allowed"):
            return True, "approved once"
        if answer in ("a", "always"):
            self.session_approvals.add(name)
            return True, "approved for this session"
        return False, "user denied"
