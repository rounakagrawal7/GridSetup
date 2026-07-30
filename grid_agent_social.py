"""
GRID v2 — AI Agent Social Platform Integration
Moltbook client: register, post, reply, vote, feed, search, follow, manage submolts
Security: only platform-issued agent API keys stored in agent file — never user credentials.
"""

import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Optional

CONFIG_FILE = "config.json"
MOLTBOOK_BASE = "https://api.moltbook.com"
MOLTBOOK_AGENT_FILE = "moltbook_agents.json"
SOCIAL_HISTORY_FILE = "social_history.json"

PERSONA_DESCRIPTION = """\
GRID needs a persona (a username) before it can post or interact on AI agent platforms.
This persona is YOUR chosen identity — the name that appears next to content GRID publishes
on your behalf. It is NOT a password, wallet key, or any real credential.

Choose a username that represents you (e.g. "MyAgent", "CyberPunk", "DataVizPro").
GRID will use this persona every time it posts, comments, votes, or follows on platforms
like Moltbook, Nebils, Moltweet, and others.

Set it once with:  /persona set <your_username>
View it anytime:   /persona
Remove it:         /persona clear"""


# ── helpers ──────────────────────────────────────────────────────

def _load_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            return json.loads(open(CONFIG_FILE, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _load_agents() -> dict:
    try:
        if os.path.exists(MOLTBOOK_AGENT_FILE):
            return json.loads(open(MOLTBOOK_AGENT_FILE, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_agents(agents: dict):
    with open(MOLTBOOK_AGENT_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, indent=2, ensure_ascii=False)


# ── Persona system ───────────────────────────────────────────────

PERSONA_FIRST_USE_KEY = "grid_persona_first_use"


def _get_persona() -> Optional[str]:
    cfg = _load_config()
    return cfg.get("grid_persona")


def _set_persona(username: str) -> str:
    username = username.strip()
    if not username:
        return "Error: persona username cannot be empty."
    if len(username) > 48:
        return "Error: persona username must be 48 characters or fewer."
    cfg = _load_config()
    cfg["grid_persona"] = username
    cfg[PERSONA_FIRST_USE_KEY] = False
    _save_config(cfg)
    return f"Persona set to '{username}'. GRID will use this identity when posting on AI agent platforms."


def _clear_persona() -> str:
    cfg = _load_config()
    old = cfg.pop("grid_persona", None)
    _save_config(cfg)
    if old:
        return f"Persona '{old}' cleared. GRID will not post or interact until a new persona is set."
    return "No persona was set."


def _is_first_persona_use() -> bool:
    cfg = _load_config()
    return cfg.get(PERSONA_FIRST_USE_KEY, True)


def _require_persona() -> Optional[str]:
    """Returns an error message if persona is not set, else None."""
    p = _get_persona()
    if p:
        return None
    if _is_first_persona_use():
        return f"GRID persona not set.\n\n{PERSONA_DESCRIPTION}"
    return "GRID persona not set. Use /persona set <username> to choose a persona before posting or interacting."


# ── MoltbookClient ──────────────────────────────────────────────

class MoltbookClient:
    def __init__(self, agent_name: Optional[str] = None):
        self.base = MOLTBOOK_BASE
        self.agent_name = agent_name
        self._agent_info = None
        if agent_name:
            agents = _load_agents()
            self._agent_info = agents.get(agent_name)

    @property
    def api_key(self) -> Optional[str]:
        if self._agent_info:
            return self._agent_info.get("api_key")
        return None

    @property
    def agent_id(self) -> Optional[str]:
        if self._agent_info:
            return self._agent_info.get("agent_id")
        return None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _request(self, method: str, path: str, data: Optional[dict] = None, params: Optional[dict] = None) -> str:
        import requests
        url = f"{self.base}{path}"
        try:
            r = requests.request(method, url, headers=self._headers(), json=data, params=params, timeout=30)
            if r.status_code in (200, 201):
                return r.text
            try:
                err = r.json()
                return f"Error ({r.status_code}): {json.dumps(err)}"
            except (json.JSONDecodeError, ValueError):
                return f"Error ({r.status_code}): {r.text[:500]}"
        except ImportError:
            return "Error: requests module not available. Run: pip install requests"
        except Exception as e:
            return f"Error: {e}"

    # ── Agent management ─────────────────────────────────────────

    def register(self, name: str, description: str = "", owner_email: str = "") -> str:
        import requests
        data = {"name": name}
        if description:
            data["description"] = description
        if owner_email:
            data["owner_email"] = owner_email
        try:
            r = requests.post(f"{self.base}/agents/register", json=data, headers={"Content-Type": "application/json"}, timeout=30)
            if r.status_code in (200, 201):
                result = r.json()
                agent_id = result.get("agent_id") or result.get("agent", {}).get("agent_id")
                api_key = result.get("api_key") or result.get("agent", {}).get("api_key")
                if agent_id and api_key:
                    agents = _load_agents()
                    agents[name] = {
                        "agent_id": agent_id,
                        "api_key": api_key,
                        "name": name,
                        "description": description,
                        "created_at": datetime.now().isoformat()
                    }
                    _save_agents(agents)
                    self._agent_info = agents[name]
                    self.agent_name = name
                    return f"Agent '{name}' registered!\n  ID: {agent_id}\n  API Key: {api_key}\nSaved to {MOLTBOOK_AGENT_FILE}."
                return json.dumps(result, indent=2)
            return f"Registration failed ({r.status_code}): {r.text[:500]}"
        except Exception as e:
            return f"Error: {e}"

    def profile(self, target: Optional[str] = None) -> str:
        if target:
            return self._request("GET", f"/agents/profile", params={"name": target})
        return self._request("GET", "/agents/me")

    def update_profile(self, **kwargs) -> str:
        return self._request("PATCH", "/agents/me", data=kwargs)

    # ── Posts ────────────────────────────────────────────────────

    def create_post(self, title: str, content: str, submolt: str = "general") -> str:
        return self._request("POST", "/posts", data={"type": "text", "title": title, "content": content, "submolt": submolt})

    def get_posts(self, sort: str = "hot", limit: int = 25, submolt: Optional[str] = None, offset: int = 0) -> str:
        params = {"sort": sort, "limit": str(limit), "offset": str(offset)}
        if submolt:
            params["submolt"] = submolt
        return self._request("GET", "/posts", params=params)

    def get_post(self, post_id: str) -> str:
        return self._request("GET", f"/posts/{post_id}")

    def delete_post(self, post_id: str) -> str:
        return self._request("DELETE", f"/posts/{post_id}")

    # ── Voting ───────────────────────────────────────────────────

    def upvote_post(self, post_id: str) -> str:
        return self._request("POST", f"/posts/{post_id}/upvote")

    def downvote_post(self, post_id: str) -> str:
        return self._request("POST", f"/posts/{post_id}/downvote")

    def upvote_comment(self, comment_id: str) -> str:
        return self._request("POST", f"/comments/{comment_id}/upvote")

    def downvote_comment(self, comment_id: str) -> str:
        return self._request("POST", f"/comments/{comment_id}/downvote")

    # ── Comments ─────────────────────────────────────────────────

    def create_comment(self, post_id: str, content: str, parent_id: Optional[str] = None) -> str:
        data = {"content": content}
        if parent_id:
            data["parent_id"] = parent_id
        return self._request("POST", f"/posts/{post_id}/comments", data=data)

    def reply_comment(self, comment_id: str, content: str) -> str:
        return self._request("POST", f"/comments/{comment_id}/reply", data={"content": content})

    def get_comments(self, post_id: str, sort: str = "best", limit: int = 100) -> str:
        return self._request("GET", f"/posts/{post_id}/comments", params={"sort": sort, "limit": str(limit)})

    def delete_comment(self, comment_id: str) -> str:
        return self._request("DELETE", f"/comments/{comment_id}")

    # ── Submolts ─────────────────────────────────────────────────

    def list_submolts(self, sort: str = "popular", limit: int = 25) -> str:
        return self._request("GET", "/submolts", params={"sort": sort, "limit": str(limit)})

    def get_submolt(self, name: str) -> str:
        return self._request("GET", f"/submolts/{name}")

    def create_submolt(self, name: str, display_name: str, description: str, category: str = "general") -> str:
        return self._request("POST", "/submolts", data={"name": name, "display_name": display_name, "description": description, "category": category})

    def subscribe(self, submolt_name: str) -> str:
        return self._request("POST", f"/submolts/{submolt_name}/subscribe")

    def unsubscribe(self, submolt_name: str) -> str:
        return self._request("DELETE", f"/submolts/{submolt_name}/subscribe")

    # ── Feed ─────────────────────────────────────────────────────

    def get_feed(self, feed_type: str = "home", sort: str = "hot", limit: int = 25) -> str:
        if feed_type == "home":
            return self._request("GET", "/feed", params={"sort": sort, "limit": str(limit)})
        return self._request("GET", f"/feed/{feed_type}", params={"sort": sort, "limit": str(limit)})

    # ── Search ───────────────────────────────────────────────────

    def search(self, query: str, search_type: str = "all", limit: int = 25, time_filter: str = "all") -> str:
        params = {"q": query, "limit": str(limit), "time": time_filter}
        return self._request("GET", f"/search/{search_type}" if search_type != "all" else "/search", params=params)

    # ── Following ────────────────────────────────────────────────

    def follow(self, agent_name_or_id: str) -> str:
        return self._request("POST", f"/agents/{agent_name_or_id}/follow")

    def unfollow(self, agent_name_or_id: str) -> str:
        return self._request("DELETE", f"/agents/{agent_name_or_id}/follow")

    # ── Agent management helpers ─────────────────────────────────

    def list_registered_agents(self) -> str:
        agents = _load_agents()
        if not agents:
            return "No Moltbook agents registered. Use 'register <name>'."
        lines = ["Registered Moltbook agents:"]
        for name, info in agents.items():
            lines.append(f"  {name} — ID: {info.get('agent_id', '?')}")
        return "\n".join(lines)

    def switch_agent(self, name: str) -> str:
        agents = _load_agents()
        if name not in agents:
            available = ", ".join(agents.keys()) if agents else "none"
            return f"Agent '{name}' not found. Available: {available}"
        self._agent_info = agents[name]
        self.agent_name = name
        return f"Switched to agent '{name}' (ID: {agents[name]['agent_id']})"


# ── Global client singleton ──────────────────────────────────────

_client: Optional[MoltbookClient] = None


def get_client() -> MoltbookClient:
    global _client
    if _client is None:
        agents = _load_agents()
        if agents:
            name = next(iter(agents))
            _client = MoltbookClient(name)
        else:
            _client = MoltbookClient()
    return _client


def _extract_id(response_text: str) -> str:
    """Try to extract a post/comment ID from an API response."""
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            for key in ("id", "post_id", "comment_id", "_id"):
                val = data.get(key)
                if val:
                    return str(val)
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r'"id"\s*:\s*"([^"]+)"', response_text)
    if m:
        return m.group(1)
    return ""


# ── Social History ───────────────────────────────────────────────

def _load_social_history() -> list:
    try:
        if os.path.exists(SOCIAL_HISTORY_FILE):
            with open(SOCIAL_HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_social_history(history: list):
    with open(SOCIAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _social_log(action: str, details: str, link: str = ""):
    history = _load_social_history()
    history.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "details": details,
        "link": link
    })
    if len(history) > 200:
        history = history[-200:]
    _save_social_history(history)


def _format_history(history: list, limit: int = 20) -> str:
    if not history:
        return "No social activity yet. GRID hasn't posted or interacted on any platform."
    lines = [f"GRID Social Activity — last {min(limit, len(history))} of {len(history)} entries:"]
    for entry in history[-limit:]:
        ts = entry.get("timestamp", "")[:19]
        action = entry.get("action", "?")
        details = entry.get("details", "")
        link = entry.get("link", "")
        lines.append(f"  [{ts}] {action}: {details}")
        if link:
            lines.append(f"         Link: {link}")
    return "\n".join(lines)


# ── Autonomous Social Exploration ───────────────────────────────

_SOCIAL_DAEMON_RUNNING = False
_SOCIAL_DAEMON_THREAD: Optional[threading.Thread] = None
_SOCIAL_DAEMON_INTERVAL = 1800  # 30 minutes between cycles


def _ensure_ready() -> tuple[bool, str]:
    """Ensure persona and agent are set. Returns (ok, message)."""
    c = get_client()
    persona = _get_persona()
    if not persona:
        return False, "GRID persona not set. Use /persona set <username>"
    agent_name = c.agent_name
    if not agent_name:
        agents = _load_agents()
        if not agents:
            return False, "No Moltbook agents registered. Use /social register <name>"
        first = next(iter(agents))
        c.switch_agent(first)
    return True, ""


def _run_auto_cycle() -> str:
    """Run one autonomous social exploration cycle. Returns summary."""
    ok, msg = _ensure_ready()
    if not ok:
        return msg

    c = get_client()
    persona = _get_persona()
    lines = []
    lines.append(f"GRID social auto-cycle — persona: {persona}, agent: {c.agent_name}")

    # Phase 1: check feed
    try:
        feed = c.get_feed("home", "hot", 10)
        lines.append(f"  [Feed] home/hot — {len(feed)} chars")
    except Exception as e:
        lines.append(f"  [Feed] error: {e}")

    # Phase 2: search topics
    interests = ["ai", "data", "python", "coding", "llm", "machine learning", "automation", "tech"]
    hits = 0
    for interest in interests:
        try:
            r = c.search(interest, "posts", 3)
            if r and "error" not in r.lower() and "page not found" not in r:
                hits += 1
        except Exception:
            pass
    lines.append(f"  [Search] scanned {hits} topics / {len(interests)}")

    # Phase 3: list submolts
    try:
        c.list_submolts(sort="popular", limit=5)
        lines.append(f"  [Submolts] checked trending communities")
    except Exception as e:
        lines.append(f"  [Submolts] error: {e}")

    _social_log("auto_cycle", f"Feed + search (topics: {hits}) + submolts", "")
    lines.append(f"  All logged. Use 'social history' to review.")
    return "\n".join(lines)


def social_auto(args_str: str) -> str:
    """Run one autonomous exploration cycle right now."""
    return _run_auto_cycle()


def social_daemon(args_str: str) -> str:
    """Start/stop/status the background social daemon."""
    global _SOCIAL_DAEMON_RUNNING, _SOCIAL_DAEMON_THREAD
    cmd = args_str.strip().lower()

    if cmd == "on" or cmd == "start":
        if _SOCIAL_DAEMON_RUNNING:
            return "Daemon already running (interval: 30 min). Use 'auto-daemon off' to stop."
        ok, msg = _ensure_ready()
        if not ok:
            return msg
        _SOCIAL_DAEMON_RUNNING = True

        def _loop():
            while _SOCIAL_DAEMON_RUNNING:
                try:
                    _run_auto_cycle()
                except Exception as e:
                    _social_log("daemon_error", f"Auto-cycle error: {e}", "")
                for _ in range(_SOCIAL_DAEMON_INTERVAL // 10):
                    time.sleep(10)
                    if not _SOCIAL_DAEMON_RUNNING:
                        return

        _SOCIAL_DAEMON_THREAD = threading.Thread(target=_loop, daemon=True)
        _SOCIAL_DAEMON_THREAD.start()
        _social_log("daemon_start", "Background social daemon started (30 min interval)", "")
        return "Background social daemon started. GRID will autonomously explore every ~30 minutes.\nUse 'auto-daemon off' to stop, 'auto-daemon' for status."

    if cmd == "off" or cmd == "stop":
        if not _SOCIAL_DAEMON_RUNNING:
            return "Daemon is not running."
        _SOCIAL_DAEMON_RUNNING = False
        _SOCIAL_DAEMON_THREAD = None
        _social_log("daemon_stop", "Background social daemon stopped", "")
        return "Background social daemon stopped."

    status = "running" if _SOCIAL_DAEMON_RUNNING else "stopped"
    interval_min = _SOCIAL_DAEMON_INTERVAL // 60
    return f"Social auto-daemon: {status} (interval: {interval_min} min)\nUse 'auto-daemon on' to start, 'auto-daemon off' to stop."


# ═══════════════════════════════════════════════════════════════════
# Tool functions for Tools._reg()
# Each takes a single input string and returns a string.
# ═══════════════════════════════════════════════════════════════════

def _social_help() -> str:
    return """Moltbook social commands (prefix with tool name or use /social):
  persona [set <name> | clear]            — Set/view/clear your GRID persona (required to post)
  register <name> [description] [email]  — Register a new agent
  profile [agent_name]                    — View profile (yours or another agent's)
  post <submolt> | <title> | <content>   — Create a post (pipe-separated)
  reply <post_id> | <content>             — Comment on a post
  reply_to <comment_id> | <content>       — Reply to a specific comment
  comments <post_id> [sort] [limit]       — View comments on a post
  feed [home|popular|all] [sort] [limit]  — Get feed
  posts [sort] [limit] [submolt]          — List posts
  post <post_id>                          — Get a single post
  search <query> [type] [limit]           — Search (type: all/posts/comments/agents)
  upvote <post_id|comment_id>             — Upvote a post or comment
  downvote <post_id|comment_id>           — Downvote a post or comment
  submolts [sort] [limit]                 — List communities
  subscribe <submolt>                     — Join a community
  unsubscribe <submolt>                   — Leave a community
  follow <agent_name>                     — Follow an agent
  unfollow <agent_name>                   — Unfollow an agent
  agents                                  — List locally registered agents
  switch <agent_name>                     — Switch active agent
  auto                                    — Run one autonomous exploration cycle now
  auto-daemon [on|off]                    — Background daemon: GRID explores every ~30 min
  history [limit]                         — Show past social activity log with links
  help                                    — Show this help

NOTE: register, post, reply, vote, subscribe, unfollow, follow, switch
require a GRID persona. Set it first: persona set <your_username>

All posts, comments, votes, follows are automatically logged to history.
Use 'social history' anytime to review what GRID has done."""


def moltbook_social(input_str: str) -> str:
    c = get_client()
    parts = input_str.strip().split(maxsplit=1)
    cmd = parts[0].lower() if parts else "help"
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "help":
        return _social_help()

    if cmd == "auto":
        return social_auto(args)

    if cmd in ("auto-daemon", "autodaemon", "daemon"):
        return social_daemon(args)

    if cmd == "history":
        limit = 20
        if args.strip().isdigit():
            limit = int(args.strip())
        history = _load_social_history()
        return _format_history(history, limit)

    if cmd == "persona":
        if not args.strip():
            p = _get_persona()
            if p:
                return f"Current GRID persona: {p}"
            return "No persona set.\n" + PERSONA_DESCRIPTION
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower()
        val = parts[1] if len(parts) > 1 else ""
        if sub == "set":
            if not val:
                return "Usage: persona set <username>"
            return _set_persona(val)
        if sub == "clear":
            return _clear_persona()
        return f"Usage: persona [set <name> | clear]"

    # ── write operations require persona ─────────────────────────

    err = _require_persona()

    if cmd == "register":
        if err:
            return err
        arg_parts = [x.strip() for x in args.split(maxsplit=2)]
        name = arg_parts[0] if len(arg_parts) > 0 else ""
        desc = arg_parts[1] if len(arg_parts) > 1 else ""
        email = arg_parts[2] if len(arg_parts) > 2 else ""
        if not name:
            return "Usage: register <name> [description] [email]"
        result = c.register(name, desc, email)
        if "registered" in result.lower():
            _social_log("register", f"Registered agent '{name}' on Moltbook", "")
        return result

    if cmd == "profile":
        return c.profile(args.strip() or None)

    if cmd == "post":
        if err:
            return err
        if "|" in args:
            pipe_parts = [x.strip() for x in args.split("|", 2)]
            if len(pipe_parts) >= 3:
                result = c.create_post(pipe_parts[1], pipe_parts[2], pipe_parts[0])
                post_id = _extract_id(result)
                link = f"{MOLTBOOK_BASE}/posts/{post_id}" if post_id else ""
                _social_log("post", f"Posted '{pipe_parts[1]}' in submolt '{pipe_parts[0]}'", link)
                return result
            return "Usage: post <submolt> | <title> | <content>"
        return c.get_post(args.strip())

    if cmd == "reply":
        if err:
            return err
        if "|" not in args:
            return "Usage: reply <post_id> | <content>"
        pid, _, content = args.partition("|")
        result = c.create_comment(pid.strip(), content.strip())
        link = f"{MOLTBOOK_BASE}/posts/{pid.strip()}"
        _social_log("reply", f"Replied to post {pid.strip()}", link)
        return result

    if cmd == "reply_to":
        if err:
            return err
        if "|" not in args:
            return "Usage: reply_to <comment_id> | <content>"
        cid, _, content = args.partition("|")
        result = c.reply_comment(cid.strip(), content.strip())
        _social_log("reply_to", f"Replied to comment {cid.strip()}", "")
        return result

    if cmd == "comments":
        ca = args.split()
        pid = ca[0] if ca else ""
        if not pid:
            return "Usage: comments <post_id> [sort] [limit]"
        sort = ca[1] if len(ca) > 1 else "best"
        limit = int(ca[2]) if len(ca) > 2 and ca[2].isdigit() else 100
        return c.get_comments(pid, sort, limit)

    if cmd == "feed":
        fa = args.split()
        ft = fa[0] if fa and fa[0] in ("home", "popular", "all") else "home"
        sort = "hot"
        limit = 25
        remaining = fa[1:] if fa and fa[0] in ("home", "popular", "all") else fa
        if remaining:
            if remaining[0] in ("hot", "new", "top", "rising"):
                sort = remaining[0]
                remaining = remaining[1:]
            if remaining and remaining[0].isdigit():
                limit = int(remaining[0])
        return c.get_feed(ft, sort, limit)

    if cmd == "posts":
        pa = args.split()
        sort = pa[0] if pa and pa[0] in ("hot", "new", "top", "rising") else "hot"
        limit = int(pa[1]) if len(pa) > 1 and pa[1].isdigit() else 25
        submolt = pa[2] if len(pa) > 2 else None
        return c.get_posts(sort, limit, submolt)

    if cmd == "search":
        sa = args.split(maxsplit=2)
        if not sa:
            return "Usage: search <query> [type] [limit]"
        query = sa[0]
        search_type = "all"
        limit = 25
        if len(sa) > 1:
            if sa[1] in ("all", "posts", "comments", "agents"):
                search_type = sa[1]
            elif sa[1].isdigit():
                limit = int(sa[1])
            else:
                query = f"{query} {sa[1]}"
        if len(sa) > 2:
            if sa[2].isdigit():
                limit = int(sa[2])
            else:
                query = f"{query} {sa[2]}"
        return c.search(query, search_type, limit)

    if cmd == "upvote":
        if err:
            return err
        result = c.upvote_post(args.strip())
        if "error" not in result.lower():
            _social_log("upvote", f"Upvoted {args.strip()}", "")
        return result

    if cmd == "downvote":
        if err:
            return err
        result = c.downvote_post(args.strip())
        if "error" not in result.lower():
            _social_log("downvote", f"Downvoted {args.strip()}", "")
        return result

    if cmd == "submolts":
        sa = args.split()
        sort = sa[0] if sa and sa[0] in ("popular", "new", "growing") else "popular"
        limit = int(sa[1]) if len(sa) > 1 and sa[1].isdigit() else 25
        return c.list_submolts(sort, limit)

    if cmd == "subscribe":
        if err:
            return err
        if not args.strip():
            return "Usage: subscribe <submolt_name>"
        result = c.subscribe(args.strip())
        if "error" not in result.lower():
            _social_log("subscribe", f"Joined submolt '{args.strip()}'", "")
        return result

    if cmd == "unsubscribe":
        if err:
            return err
        if not args.strip():
            return "Usage: unsubscribe <submolt_name>"
        result = c.unsubscribe(args.strip())
        if "error" not in result.lower():
            _social_log("unsubscribe", f"Left submolt '{args.strip()}'", "")
        return result

    if cmd == "follow":
        if err:
            return err
        if not args.strip():
            return "Usage: follow <agent_name>"
        result = c.follow(args.strip())
        if "error" not in result.lower():
            _social_log("follow", f"Followed agent '{args.strip()}'", "")
        return result

    if cmd == "unfollow":
        if err:
            return err
        if not args.strip():
            return "Usage: unfollow <agent_name>"
        result = c.unfollow(args.strip())
        if "error" not in result.lower():
            _social_log("unfollow", f"Unfollowed agent '{args.strip()}'", "")
        return result

    if cmd == "agents":
        return c.list_registered_agents()

    if cmd == "switch":
        if err:
            return err
        if not args.strip():
            return "Usage: switch <agent_name>"
        return c.switch_agent(args.strip())

    return f"Unknown command: {cmd}\n{_social_help()}"
