"""Subcommand metadata for slash autocomplete.

The registry is deliberately data-only. The desktop requests it through
``/api/v1/tools`` and renders a second-level palette after ``/tool ``.
Tools with free-form inputs do not need an entry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _cmd(
    name: str,
    description: str,
    template: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "template": template,
    }


SUBCOMMANDS: Dict[str, List[Dict[str, Any]]] = {
    "social": [
        _cmd("persona", "Set/view/clear persona: set <name> | clear", "persona "),
        _cmd("register", "Register a new agent", "register "),
        _cmd("profile", "View your or another agent's profile", "profile "),
        _cmd("post", "Create (submolt | title | content) or fetch a post id", "post "),
        _cmd("reply", "Comment on a post: <post_id> | <content>", "reply "),
        _cmd("reply_to", "Reply to a comment: <comment_id> | <content>", "reply_to "),
        _cmd("comments", "View comments on a post", "comments "),
        _cmd("feed", "Get feed: [home|popular|all] [sort] [limit]", "feed "),
        _cmd("posts", "List posts: [sort] [limit] [submolt]", "posts "),
        _cmd("search", "Search: <query> [type] [limit]", "search "),
        _cmd("upvote", "Upvote a post: <post_id>", "upvote "),
        _cmd("downvote", "Downvote a post: <post_id>", "downvote "),
        _cmd("upvote_comment", "Upvote a comment: <comment_id>", "upvote_comment "),
        _cmd("downvote_comment", "Downvote a comment: <comment_id>", "downvote_comment "),
        _cmd("submolts", "List communities", "submolts "),
        _cmd("subscribe", "Join a community: <submolt>", "subscribe "),
        _cmd("unsubscribe", "Leave a community: <submolt>", "unsubscribe "),
        _cmd("follow", "Follow an agent: <agent_name>", "follow "),
        _cmd("unfollow", "Unfollow an agent: <agent_name>", "unfollow "),
        _cmd("agents", "List locally registered agents"),
        _cmd("switch", "Switch active agent: <agent_name>", "switch "),
        _cmd("status", "Check agent claim status"),
        _cmd("verify", "Submit a verification answer: <code> <answer>", "verify "),
        _cmd("auto", "Run one autonomous exploration cycle now"),
        _cmd("engage", "Reply to new comments and upvote promising posts"),
        _cmd("writeup", "Auto-generate and post the memory write-up", "writeup "),
        _cmd("auto-daemon", "Background daemon: on|off", "auto-daemon "),
        _cmd("history", "Show past social activity", "history "),
        _cmd("summary", "Plain-language activity + hot-topic digest"),
        _cmd("analyze", "Pandas report on feed and engagement"),
        _cmd("trend", "Time-series report: day|week|month|year|all", "trend "),
        _cmd("help", "Show the social reference"),
    ],
    "satellite": [
        _cmd("iss", "ISS position and crew"),
        _cmd("position", "Current position: <norad>", "position "),
        _cmd("passes", "Pass predictions: <norad> <lat> <lon> [days]", "passes "),
        _cmd("tle", "TLE data: <norad>", "tle "),
        _cmd("search", "Search the catalog: <query>", "search "),
        _cmd("list", "List a group: [weather|gps|science|...]", "list "),
        _cmd("analyze", "Orbit analysis: <norad>", "analyze "),
        _cmd("help", "Show the satellite reference"),
    ],
    "radio": [
        _cmd("browser", "Radio-Browser: search|bycountry|bytag|top|play", "browser "),
        _cmd("kiwi", "KiwiSDR: list|bycountry|open|stream|status", "kiwi "),
        _cmd("rtlsdr", "RTL-SDR: scan|list|tune", "rtlsdr "),
        _cmd("help", "Show the radio reference"),
    ],
    "micro": [
        _cmd("scan", "Scan for serial ports"),
        _cmd("connect", "Connect: <port|host:port> [baud]", "connect "),
        _cmd("disconnect", "Close the connection"),
        _cmd("send", "Send data: <data>", "send "),
        _cmd("read", "Read lines: [N]", "read "),
        _cmd("monitor", "Continuous read: on|off", "monitor "),
        _cmd("info", "Show connection state"),
        _cmd("lora", "LoRa: send <data> | recv", "lora "),
        _cmd("help", "Show the microcontroller reference"),
    ],
    "ctf": [
        _cmd("start", "Start a challenge: [id]", "start "),
        _cmd("status", "Show the active challenge"),
        _cmd("hint", "Get a hint: [id]", "hint "),
        _cmd("submit", "Submit a flag: <flag>", "submit "),
        _cmd("score", "Show progress and write scoreboard"),
        _cmd("reset", "Reset a challenge or the range: [id]", "reset "),
        _cmd("list", "List challenges and solved status"),
        _cmd("help", "Show the CTF reference"),
    ],
    "game": [
        _cmd("world", "Open-world sandbox: help|start|status", "world "),
        _cmd("minigrid", "MiniGrid RL bridge: status", "minigrid "),
        _cmd("help", "Show the game reference"),
    ],
    "gcal": [
        _cmd("setup", "Authenticate: <client_id> <client_secret>", "setup "),
        _cmd("calendars", "List calendars"),
        _cmd("events", "Upcoming events: [cal_id] [count]", "events "),
        _cmd("event", "Event details: <event_id> [cal_id]", "event "),
        _cmd("create", "Create: <cal_id> | <summary> | <start> | <end>", "create "),
        _cmd("update", "Update: <event_id> [cal_id] | <field>=<value>", "update "),
        _cmd("delete", "Delete: <event_id> [cal_id]", "delete "),
        _cmd("search", "Search: <query> [cal_id] [count]", "search "),
        _cmd("help", "Show the calendar reference"),
    ],
    "gsheet": [
        _cmd("list", "List Google Sheets"),
        _cmd("read", "Read: <id> [range]", "read "),
        _cmd("create", "Create: <title>", "create "),
        _cmd("write", "Write: <id> | <range> | <values>", "write "),
        _cmd("append", "Append: <id> | <range> | <values>", "append "),
        _cmd("open", "Open local .xlsx: <path> [sheet]", "open "),
        _cmd("new", "New .xlsx: <path> [sheet] [headers]", "new "),
        _cmd("edit", "Edit cell: <path> | <cell> | <value>", "edit "),
        _cmd("addrow", "Add row: <path> | <values>", "addrow "),
        _cmd("stats", "Summary stats: <id_or_path> [sheet]", "stats "),
        _cmd("analyze", "Column analysis: <id_or_path> [columns]", "analyze "),
        _cmd("plot", "Plot: <id_or_path> | <x> | <y> [| title]", "plot "),
        _cmd("help", "Show the sheets reference"),
    ],
    "rea": [
        _cmd("authorized", "One-off authorized teardown: <url>", "authorized "),
        _cmd("authorize", "Add a host to the allowlist: <host>", "authorize "),
        _cmd("revoke", "Remove a host: <host>", "revoke "),
        _cmd("list", "Show the allowlist"),
        _cmd("status", "Show the allowlist and status"),
        _cmd("help", "Show the REA reference"),
    ],
    "osint": [
        _cmd("search", "Web intelligence: <query>", "search "),
        _cmd("camera", "Find public cameras: <country>", "camera "),
        _cmd("dork", "Google dorks: cameras|admin|logs|config|db|docs|cloud|dev", "dork "),
        _cmd("flight", "Track a flight: <callsign>", "flight "),
        _cmd("flight_tracker", "Regional flight map: [lat lon radius]", "flight_tracker "),
        _cmd("help", "Show the OSINT reference"),
    ],
    "comms": [
        _cmd("help", "Show the communication reference"),
    ],
    "jobs": [
        _cmd("list", "List dynamic skills"),
        _cmd("show", "Show a skill: <name>", "show "),
        _cmd("toggle", "Enable/disable a skill: <name>", "toggle "),
        _cmd("new", "Create a skill interactively"),
        _cmd("edit", "Edit a skill: <name>", "edit "),
        _cmd("delete", "Delete a skill: <name>", "delete "),
        _cmd("help", "Show the skills reference"),
    ],
    "life": [
        _cmd("status", "Current autopilot state"),
        _cmd("help", "Show the life reference"),
        _cmd("log", "Recent activity: [n]", "log "),
        _cmd("goals", "Active goals"),
        _cmd("goal", "add <title> | done <id>", "goal "),
        _cmd("commitments", "Open commitments"),
        _cmd("commitment", "add <text> | done <id>", "commitment "),
        _cmd("pause", "Pause autonomous work"),
        _cmd("resume", "Resume autonomous work"),
        _cmd("identity", "Show persona and identity"),
        _cmd("tick", "Run one autonomous cycle"),
        _cmd("awake", "Awake run: [task]", "awake "),
    ],
    "memory": [
        _cmd("status", "Show memory status"),
        _cmd("profile", "Show the user profile"),
        _cmd("add", "Teach a durable fact: <fact>", "add "),
        _cmd("forget", "Remove a fact: <text>", "forget "),
        _cmd("build-profile", "Rebuild the profile from previous chats"),
        _cmd("clear-profile", "Clear the profile"),
        _cmd("clear", "Clear layered memory (profile untouched)"),
        _cmd("help", "Show the memory reference"),
    ],
    "persona": [
        _cmd("set", "Set the GRID persona: <name>", "set "),
        _cmd("clear", "Clear the persona"),
        _cmd("status", "Show the current persona"),
    ],
    "pb": [
        _cmd("status", "PocketBase status"),
        _cmd("start", "Start PocketBase"),
        _cmd("stop", "Stop PocketBase"),
        _cmd("install", "Download the PocketBase binary"),
        _cmd("sync", "Sync memory to PocketBase"),
    ],
}


def subcommands_for(name: str) -> List[Dict[str, Any]]:
    return list(SUBCOMMANDS.get((name or "").lower()) or [])
