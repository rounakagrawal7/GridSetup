"""
GRID v2 — AI Agent Social Platform Integration
Moltbook client: register, post, reply, vote, feed, search, follow, manage submolts
Security: only platform-issued agent API keys stored in agent file — never user credentials.
"""

import difflib
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Optional

CONFIG_FILE = "config.json"
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
MOLTBOOK_AGENT_FILE = "moltbook_agents.json"
SOCIAL_HISTORY_FILE = "social_history.json"
MOLTBOOK_REPLIED_FILE = "moltbook_replied.json"
MOLTBOOK_STATS_FILE = "social_stats.json"

# Serializes auto-cycles and id-claim read-modify-write blocks so concurrent
# daemon / manual / LLM-tool invocations never double-post the same content.
_AUTO_CYCLE_LOCK = threading.Lock()
_CLAIM_GUARD = threading.RLock()
_CLAIM_LOCKS = {}

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
                agent = result.get("agent") or {}
                api_key = agent.get("api_key") or result.get("api_key")
                claim_url = agent.get("claim_url") or result.get("claim_url") or ""
                verification_code = agent.get("verification_code") or result.get("verification_code") or ""
                agent_id = agent.get("agent_id") or agent.get("id") or result.get("agent_id") or ""
                if api_key:
                    agents = _load_agents()
                    agents[name] = {
                        "agent_id": agent_id,
                        "api_key": api_key,
                        "claim_url": claim_url,
                        "verification_code": verification_code,
                        "owner_email": owner_email,
                        "name": name,
                        "description": description,
                        "created_at": datetime.now().isoformat()
                    }
                    _save_agents(agents)
                    self._agent_info = agents[name]
                    self.agent_name = name
                    msg = f"Agent '{name}' registered!\n  API Key: {api_key}\nSaved to {MOLTBOOK_AGENT_FILE}."
                    if claim_url:
                        msg += f"\n  CLAIM URL (send to your human): {claim_url}"
                    if verification_code:
                        msg += f"\n  Verification code: {verification_code}"
                    if not agent_id:
                        msg += "\n  NOTE: claim the agent via the CLAIM URL to activate it."
                    return msg
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
        return self._request("POST", "/posts", data={"type": "text", "title": title, "content": content, "submolt_name": submolt})

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

    def create_submolt(self, name: str, display_name: str, description: str, allow_crypto: bool = False) -> str:
        return self._request("POST", "/submolts", data={"name": name, "display_name": display_name, "description": description, "allow_crypto": allow_crypto})

    def subscribe(self, submolt_name: str) -> str:
        return self._request("POST", f"/submolts/{submolt_name}/subscribe")

    def unsubscribe(self, submolt_name: str) -> str:
        return self._request("DELETE", f"/submolts/{submolt_name}/subscribe")

    # ── Verification & status ────────────────────────────────────

    def verify(self, verification_code: str, answer: str) -> str:
        return self._request("POST", "/verify", data={"verification_code": verification_code, "answer": answer})

    def check_status(self) -> str:
        return self._request("GET", "/agents/status")

    # ── Feed ─────────────────────────────────────────────────────

    def get_feed(self, feed_type: str = "home", sort: str = "hot", limit: int = 25) -> str:
        return self._request("GET", "/feed", params={"sort": sort, "limit": str(limit)})

    # ── Search ───────────────────────────────────────────────────

    def search(self, query: str, search_type: str = "all", limit: int = 25, time_filter: str = "all") -> str:
        params = {"q": query, "type": search_type, "limit": str(limit)}
        return self._request("GET", "/search", params=params)

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


# ── Auto verification challenge solving ──────────────────────────

_NUM_WORDS = {n: i for i, n in enumerate([
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand"])}
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty",
         70: "seventy", 80: "eighty", 90: "ninety"}
_ONES = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
         7: "seven", 8: "eight", 9: "nine"}
_NUM_CANDIDATES = {}
for _w, _v in _NUM_WORDS.items():
    _collapsed = re.sub(r"(.)\1+", r"\1", _w)
    _NUM_CANDIDATES[_collapsed] = _v
    _NUM_CANDIDATES[_w] = _v
for _a in _TENS:
    for _b in _ONES:
        _phrase = f"{_TENS[_a]}{_ONES[_b]}"
        _NUM_CANDIDATES[re.sub(r"(.)\1+", r"\1", _phrase)] = _a + _b
        _NUM_CANDIDATES[_phrase] = _a + _b
_NUM_CANDIDATES = sorted(_NUM_CANDIDATES.items(), key=lambda x: -len(x[0]))


def _collapse_dups(text: str) -> str:
    return re.sub(r"(.)\1+", r"\1", text)


def _clean_challenge(challenge: str) -> str:
    text = re.sub(r"[^a-zA-Z ]", "", challenge).lower()
    return _collapse_dups(text)


def _fuzzy_at(text: str, word: str, cutoff: float = 0.82) -> tuple:
    best, best_pos = 0.0, -1
    L = len(word)
    for start in range(max(0, len(text) - L + 1)):
        ratio = difflib.SequenceMatcher(None, text[start:start + L], word).ratio()
        if ratio > best:
            best, best_pos = ratio, start
    return (best_pos, best) if best >= cutoff else (-1, best)


def _extract_challenge_numbers(cleaned: str) -> list:
    """Extract numbers from a deobfuscated challenge as a positional list."""
    text = cleaned.replace(" ", "")
    matches = []
    for key, value in _NUM_CANDIDATES:
        if value == 0:
            continue
        pos, _ = _fuzzy_at(text, key, 0.82)
        if pos >= 0:
            matches.append([pos, value, len(key)])
    matches.sort(key=lambda m: m[0])
    chosen = []
    for pos, value, ln in matches:
        if chosen and abs(pos - chosen[-1][0]) < max(ln, chosen[-1][2], 3):
            continue
        chosen.append((pos, value, ln))
    return [v for _, v, _ in chosen]


def solve_moltbook_challenge(challenge_text: str) -> Optional[str]:
    """Solve an obfuscated math word challenge. Returns '12.34' or None."""
    if CHALLENGE_SOLVER is not None:
        try:
            answer = CHALLENGE_SOLVER(challenge_text)
            if answer:
                return answer
        except Exception:
            pass
    cleaned = _clean_challenge(challenge_text)
    nums = _extract_challenge_numbers(cleaned)
    if len(nums) < 2:
        return None
    a, b = nums[0], nums[1]
    if any(w in cleaned for w in ("slows by", "slower", "decreases", "minus", "less")):
        return f"{a - b:.2f}"
    if any(w in cleaned for w in ("times", "multiplied")):
        return f"{a * b:.2f}"
    if any(w in cleaned for w in ("divided", "splits", "per")):
        return f"{a / b:.2f}" if b else None
    return f"{a + b:.2f}"


# ── Secret / credential leak guard ───────────────────────────────

_SECRET_PATTERNS = [
    r"moltbook_sk_[A-Za-z0-9]{10,}",
    r"moltbook_verify_[A-Za-z0-9_-]{10,}",
    r"moltbook_claim_[A-Za-z0-9_-]{10,}",
    r"sk-proj-[A-Za-z0-9-]{16,}",
    r"sk-[A-Za-z0-9-]{20,}",
    r"sk_[A-Za-z0-9]{20,}",
    r"api[_-]?key\s*[:=]\s*\S{10,}",
    r"bearer\s+[A-Za-z0-9._-]{15,}",
    r"(?:password|passwd|pwd)\s*[:=]\s*\S{4,}",
    r"(?:password|passwd|pwd)\s+(?:is|was)\s+(?=\S*[0-9@#!_.\-])\S{4,}",
    r"(?:secret|token)\s*[:=]\s*\S{8,}",
    r"(?:secret|token)\s+(?:is|was)\s+(?=\S*[0-9@#!_.\-])\S{8,}",
    r"AKIA[0-9A-Z]{16}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"ghp_[A-Za-z0-9]{36}",
]


def _contains_secret(text: str) -> Optional[str]:
    """Return a matched secret-like pattern name if text looks like a credential, else None."""
    if not text:
        return None
    lower = text.lower()
    for pat in _SECRET_PATTERNS:
        if re.search(pat, lower, re.IGNORECASE):
            return pat
    if "claim_url" in lower and ("http" in lower or "://" in lower):
        return "claim_url"
    if re.search(r"api[_ -]?key", lower) and re.search(r"[A-Za-z0-9]{16,}", text):
        return "api_key"
    return None


def _guard_reply(reply: str) -> Optional[str]:
    """Reject a generated reply that leaks secrets or mimics an instruction to leak."""
    hit = _contains_secret(reply)
    if hit:
        return f"(blocked reply: detected {hit})"
    return None


def auto_verify_response(response_text: str) -> str:
    """If the response contains a verification challenge, solve and submit it."""
    try:
        data = json.loads(response_text)
    except (json.JSONDecodeError, ValueError):
        return response_text
    if not isinstance(data, dict):
        return response_text
    post = data.get("post") or data.get("comment") or data.get("submolt") or {}
    ver = data.get("verification") or post.get("verification")
    if not ver:
        return response_text
    code = ver.get("verification_code")
    challenge = ver.get("challenge_text")
    if not code or not challenge:
        return response_text
    answer = solve_moltbook_challenge(challenge)
    if answer is None:
        return response_text + "\n\n[Verification challenge unsolvable automatically — solve and use: social verify <code> <answer>]"
    c = get_client()
    result = c.verify(code, answer)
    try:
        vdata = json.loads(result)
        ok = vdata.get("success")
    except (json.JSONDecodeError, ValueError):
        ok = False
    if ok:
        msg = vdata.get("message", "Verification successful!")
        return response_text + f"\n\n[Auto-verified: {msg}]"
    return response_text + f"\n\n[Auto-verify failed for answer {answer}: {result[:200]}]"


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


def _count_actions(history: list) -> dict:
    counts = {}
    for e in history:
        a = e.get("action", "?")
        counts[a] = counts.get(a, 0) + 1
    return counts


def _summarize_feed(feed_raw: str, limit: int = 8) -> list:
    """Extract readable 'author: title (upvotes)' rows from a feed/posts response."""
    rows = []
    try:
        data = json.loads(feed_raw)
    except (json.JSONDecodeError, ValueError):
        return rows
    posts = data.get("posts") or data.get("data") or []
    for post in posts[:limit]:
        author = (post.get("author") or {}).get("name") or "?"
        title = (post.get("title") or post.get("content") or "")[:80]
        up = post.get("upvotes") or 0
        rows.append(f"    {author}: {title} (+{up})")
    return rows


def _summarize_comments_on_my_posts(limit: int = 6) -> list:
    """Recent comments left on my own posts. Returns readable rows."""
    c = get_client()
    rows = []
    try:
        home = c._request("GET", "/home")
        data = json.loads(home)
    except (json.JSONDecodeError, ValueError):
        return rows
    activity = data.get("activity_on_your_posts") or []
    for item in activity[:limit]:
        post_id = item.get("post_id")
        if not post_id:
            continue
        post_title = (item.get("post_title") or "my post")[:60]
        try:
            comments = _parse_comments(c.get_comments(post_id, "new", 100))
        except Exception:
            continue
        for cm in comments[:2]:
            author = (cm.get("author") or {}).get("name") or "?"
            content = (cm.get("content") or "")[:70]
            rows.append(f"    {author} on '{post_title}': {content}")
    return rows


def _summarize_topics() -> list:
    """Topic pulse from trending searches. Returns readable rows."""
    c = get_client()
    rows = []
    interests = ["ai", "data", "python", "llm", "security", "automation"]
    for interest in interests:
        try:
            r = c.search(interest, "posts", 3)
            data = json.loads(r)
            posts = data.get("posts") or data.get("data") or []
            if posts:
                for post in posts[:2]:
                    title = (post.get("title") or "")[:70]
                    rows.append(f"    [{interest}] {title}")
        except Exception:
            continue
    return rows


# ── Autonomous Social Exploration ───────────────────────────────

_SOCIAL_DAEMON_RUNNING = False
_SOCIAL_DAEMON_THREAD: Optional[threading.Thread] = None
_SOCIAL_DAEMON_INTERVAL = 1800  # 30 minutes between cycles

# Rate-limit backoff state: when Moltbook returns a 429 (hourly comment/post cap),
# we stop hammering the write endpoints for a while and log it only once.
_RATE_LIMIT_UNTIL = 0.0  # epoch seconds until comment/post writes are paused
_RATE_LIMIT_LOGGED = 0.0  # epoch seconds when the current backoff was reported


def _mark_rate_limited(text: str) -> bool:
    """Detect a 429 rate-limit response and start backoff. Returns True if detected."""
    global _RATE_LIMIT_UNTIL
    if not text or ("429" not in text):
        return False
    if "limit reached" in text.lower() or "too many" in text.lower() or "rate" in text.lower():
        _RATE_LIMIT_UNTIL = time.time() + 3600  # hourly cap -> pause for the hour
        return True
    return False


def _rate_limited() -> bool:
    """True while write-actions should be paused due to a recent 429."""
    return time.time() < _RATE_LIMIT_UNTIL


def _rate_limit_report() -> str:
    """Log the backoff start once and return a user-facing message."""
    global _RATE_LIMIT_LOGGED
    if time.time() - _RATE_LIMIT_LOGGED < 3600:
        return ""
    _RATE_LIMIT_LOGGED = time.time()
    _social_log("rate_limited", "Moltbook 429 hit — write actions paused for ~1h", "")
    return "  [RateLimit] Moltbook hourly limit reached — write actions paused for ~1 hour."


def _rate_limit_remaining() -> str:
    """Human-readable remaining backoff time, or '' if not limited."""
    if not _rate_limited():
        return ""
    mins = int((_RATE_LIMIT_UNTIL - time.time()) // 60)
    return f"{mins} min"

# Optional hook for generating reply text. GRID's LLM backend sets this.
REPLY_GENERATOR = None

# Optional hook for generating a comment on someone else's post.
COMMENT_GENERATOR = None

# Optional hook that rewrites a raw digest into conversational prose.
SUMMARY_GENERATOR = None

# Optional hook that generates a new post for a submolt community.
# Called as POST_GENERATOR(submolt_info: dict, sample_posts: list) -> (title, content)
POST_GENERATOR = None

# Optional hook that generates the long-form technical write-up about GRID's
# memory architecture. Called as WRITEUP_GENERATOR(spec: str, sample_posts: list)
# -> (title, content). Wired from grid_agent.py so it shares the LLM backend.
WRITEUP_GENERATOR = None

# Optional hook that reads an obfuscated Moltbook verification challenge and
# returns the numeric answer ('12.34'). Wired from grid_agent.py so it shares
# the LLM backend. Falls back to the heuristic solver when unset or unavailable.
CHALLENGE_SOLVER = None


def set_challenge_solver(fn):
    """Set a callable(challenge_text) -> answer_string for AI verification challenges."""
    global CHALLENGE_SOLVER
    CHALLENGE_SOLVER = fn


def set_post_generator(fn):
    """Set a callable(submolt_dict, sample_posts) -> (title, content) for the auto-post cycle."""
    global POST_GENERATOR
    POST_GENERATOR = fn


def set_writeup_generator(fn):
    """Set a callable(spec_str, sample_posts) -> (title, content) used by 'writeup'."""
    global WRITEUP_GENERATOR
    WRITEUP_GENERATOR = fn


def set_reply_generator(fn):
    """Set a callable(comment_dict, post_title) -> reply_text used by auto-cycles."""
    global REPLY_GENERATOR
    REPLY_GENERATOR = fn


def set_comment_generator(fn):
    """Set a callable(post_dict) -> comment_text used by the auto-comment cycle."""
    global COMMENT_GENERATOR
    COMMENT_GENERATOR = fn


def set_summary_generator(fn):
    """Set a callable(raw_digest_str) -> prose used to make social summaries conversational."""
    global SUMMARY_GENERATOR
    SUMMARY_GENERATOR = fn


def _load_replied() -> set:
    try:
        if os.path.exists(MOLTBOOK_REPLIED_FILE):
            with open(MOLTBOOK_REPLIED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_replied(ids: set):
    _write_ids_atomic(MOLTBOOK_REPLIED_FILE, ids)


# ── atomic id stores + claim helpers ─────────────────────────────
# Multiple entry points can run the auto-cycles at once (daemon thread,
# manual /social auto, auto-detected LLM tool calls). The claim helpers
# atomically mark an id in the on-disk JSON *before* the network write is
# attempted, so a second concurrent run sees it claimed and skips it.

def _write_json_atomic(path: str, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)


def _write_ids_atomic(path: str, ids: set):
    _write_json_atomic(path, sorted(ids))


def _load_ids(path: str) -> set:
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_ids(path: str, ids: set):
    _write_ids_atomic(path, ids)


def _claim_lock(path: str) -> threading.RLock:
    with _CLAIM_GUARD:
        lock = _CLAIM_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _CLAIM_LOCKS[path] = lock
        return lock


def _claim_id(path: str, key: str) -> bool:
    """Atomically claim a key so only ONE run acts on it. Returns True if
    this caller won the claim (key was not already in the file)."""
    with _claim_lock(path):
        ids = _load_ids(path)
        if key in ids:
            return False
        ids.add(key)
        _save_ids(path, ids)
        return True


def _release_claim(path: str, key: str):
    """Release a previously-won claim (used when the write failed)."""
    with _claim_lock(path):
        ids = _load_ids(path)
        ids.discard(key)
        _save_ids(path, ids)


MOLTBOOK_COMMENTED_FILE = "moltbook_commented.json"


def _load_commented() -> set:
    try:
        if os.path.exists(MOLTBOOK_COMMENTED_FILE):
            with open(MOLTBOOK_COMMENTED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_commented(ids: set):
    _write_ids_atomic(MOLTBOOK_COMMENTED_FILE, ids)


MOLTBOOK_UPVOTED_FILE = "moltbook_upvoted.json"


def _load_upvoted() -> set:
    try:
        if os.path.exists(MOLTBOOK_UPVOTED_FILE):
            with open(MOLTBOOK_UPVOTED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_upvoted(ids: set):
    _write_ids_atomic(MOLTBOOK_UPVOTED_FILE, ids)


MOLTBOOK_FOLLOWED_FILE = "moltbook_followed.json"


def _load_followed() -> set:
    try:
        if os.path.exists(MOLTBOOK_FOLLOWED_FILE):
            with open(MOLTBOOK_FOLLOWED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_followed(ids: set):
    _write_ids_atomic(MOLTBOOK_FOLLOWED_FILE, ids)


MOLTBOOK_POSTED_FILE = "moltbook_posted.json"


def _load_posted() -> set:
    try:
        if os.path.exists(MOLTBOOK_POSTED_FILE):
            with open(MOLTBOOK_POSTED_FILE, encoding="utf-8") as f:
                return set(json.load(f))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return set()


def _save_posted(ids: set):
    _write_ids_atomic(MOLTBOOK_POSTED_FILE, ids)


# ── Snapshot stats (time series) ────────────────────────────────

def _load_stats() -> list:
    try:
        if os.path.exists(MOLTBOOK_STATS_FILE):
            with open(MOLTBOOK_STATS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return []


def _save_stats(stats: list):
    with open(MOLTBOOK_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def _own_post_ids(c) -> set:
    """Find post IDs authored by me via /posts?author=<name> and /agents/profile."""
    ids = set()
    name = c.agent_name
    if not name:
        return ids
    # /posts?author= may hide pending/unverified posts, so also merge the
    # profile's recentPosts which includes all authored posts.
    try:
        r = json.loads(c._request("GET", "/posts", params={"author": name, "limit": "50"}))
        for p in (r.get("posts") or []):
            pid = p.get("id") or p.get("post_id")
            if pid:
                ids.add(pid)
    except Exception:
        pass
    try:
        r = json.loads(c._request("GET", "/agents/profile", params={"name": name}))
        for p in (r.get("recentPosts") or []):
            pid = p.get("id") or p.get("post_id")
            if pid:
                ids.add(pid)
    except Exception:
        pass
    return ids


def _record_snapshot(c, prof: dict, feed_posts: list, commenter_counts: dict):
    """Append one dated snapshot to social_stats.json for time-series analysis."""
    try:
        stats = _load_stats()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        snap = {
            "ts": now,
            "karma": prof.get("karma"),
            "followers": prof.get("follower_count"),
            "following": prof.get("following_count"),
            "posts": prof.get("posts_count"),
            "comments": prof.get("comments_count"),
            "feed_posts": len(feed_posts),
            "feed_upvotes": int(sum(p.get("upvotes", 0) for p in feed_posts)),
            "feed_comments": int(sum(p.get("comments", 0) for p in feed_posts)),
            "comments_received": sum(commenter_counts.values()),
            "unique_commenters": len(commenter_counts),
        }
        if stats and stats[-1].get("ts", "")[:16] == now[:16]:
            stats[-1] = snap  # keep one per minute
        else:
            stats.append(snap)
        if len(stats) > 1000:
            stats = stats[-1000:]
        _save_stats(stats)
    except Exception:
        pass


def _trend_text(period: str = "all") -> str:
    """Time-series summary of snapshots across day/week/month/all."""
    stats = _load_stats()
    if not stats:
        return "No snapshot history yet. Run 'social analyze' a few times (across days) to build a trend."
    from datetime import datetime as _dt, timedelta as _td
    now = _dt.now()
    cutoff = None
    if period in ("day", "today", "24h"):
        cutoff = now - _td(days=1)
    elif period in ("week", "7d"):
        cutoff = now - _td(days=7)
    elif period in ("month", "30d"):
        cutoff = now - _td(days=30)
    elif period in ("year", "365d"):
        cutoff = now - _td(days=365)
    rows = []
    for s in stats:
        try:
            t = _dt.strptime(s.get("ts", "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if cutoff and t < cutoff:
            continue
        rows.append(s)
    if not rows:
        return f"No snapshots in the last '{period}' period. Run 'social analyze' regularly to build history."
    lines = []
    lines.append(f"[bold cyan]MOLTBOOK TREND · {period}[/]  [dim]({len(rows)} snapshots)[/]")
    lines.append("")
    lines.append("[bold]PROFILE PROGRESSION[/]")
    lines.append(f"  {'date':<17} {'karma':>5} {'fol':>4} {'fwg':>4} {'pst':>4} {'cmt':>5}")
    for s in rows:
        lines.append(
            f"  {s.get('ts','')[:16]:<17} {str(s.get('karma')):>5} {str(s.get('followers')):>4} "
            f"{str(s.get('following')):>4} {str(s.get('posts')):>4} {str(s.get('comments')):>5}"
        )
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        delta = {}
        for k in ("karma", "followers", "following", "posts", "comments", "feed_upvotes", "comments_received", "unique_commenters"):
            fv, lv = first.get(k), last.get(k)
            if isinstance(fv, int) and isinstance(lv, int):
                delta[k] = lv - fv
        lines.append("")
        lines.append("[bold]DELTA (first -> last snapshot)[/]")
        for k, v in delta.items():
            arrow = "+" if v > 0 else ""
            lines.append(f"  {k:<18} {v:+d}")
    lines.append("")
    lines.append("[bold]FEED / ENGAGEMENT (latest)[/]")
    s = rows[-1]
    lines.append(
        f"  feed posts: {s.get('feed_posts')}   feed upvotes: {s.get('feed_upvotes')}   "
        f"feed comments: {s.get('feed_comments')}"
    )
    lines.append(f"  comments received: {s.get('comments_received')}   unique commenters: {s.get('unique_commenters')}")
    lines.append("")
    lines.append("[dim]Tip: 'social trend week' or 'social trend 30d' for longer windows.[/]")
    return "\n".join(lines)


def _trend_panel(period: str = "all"):
    """Green box time-series report."""
    from rich.panel import Panel
    from rich.text import Text
    body = _trend_text(period)
    return Panel(
        Text.from_markup(body),
        title="[bold green]MOLTBOOK TREND[/]",
        border_style="green",
        padding=(1, 1),
    )


def _parse_comments(raw: str) -> list:
    """Flatten the comment tree from a get_comments response."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    comments = data.get("comments") or []
    flat = []
    def _walk(items, depth=0):
        for cm in items:
            flat.append(cm)
            _walk(cm.get("replies") or [], depth + 1)
    _walk(comments)
    return flat


def _reply_to_comment(comment: dict, post_title: str) -> Optional[str]:
    """Generate + post a reply to a comment. Returns reply text or None."""
    author = comment.get("author") or {}
    author_id = author.get("id") or comment.get("author_id") or ""
    name = author.get("name") or "there"
    c = get_client()
    if author_id and author_id == c.agent_id:
        return None
    content = comment.get("content", "")
    if not content:
        return None
    if REPLY_GENERATOR:
        try:
            reply = REPLY_GENERATOR(comment, post_title)
            if reply and reply.strip():
                reply = reply.strip()[:1000]
            else:
                reply = ""
        except Exception:
            reply = ""
    else:
        reply = ""
    if not reply:
        reply = f"Thanks for the thoughtful comment, {name}! Glad you enjoyed it."
    blocked = _guard_reply(reply)
    if blocked:
        _social_log("reply_blocked", f"Refused reply to {name}: {blocked}", "")
        return None
    if _rate_limited():
        return None
    raw_result = c.create_comment(comment.get("post_id", ""), reply, parent_id=comment.get("id"))
    result = auto_verify_response(raw_result)
    if _mark_rate_limited(raw_result):
        _rate_limit_report()
        return None
    if '"success":true' not in result and "created" not in result.lower() and not any(k in result for k in ("verification", "pending")):
        _social_log("reply_error", f"Auto-reply failed: {result[:200]}", "")
        return None
    if ('verification_status": "pending"' in result or 'verification_required": true' in result) and "[Auto-verified" not in result:
        _social_log("reply_error", f"Auto-reply pending verification — will retry next cycle: {raw_result[:200]}", "")
        return None
    if '"success":true' in result or "created" in result.lower():
        _social_log("reply", f"Auto-replied to {name} on '{post_title[:50]}'", f"{MOLTBOOK_BASE}/posts/{comment.get('post_id')}")
        return reply
    _social_log("reply_error", f"Auto-reply failed: {result[:200]}", "")
    return None


def _auto_reply_cycle() -> tuple[int, list]:
    """Reply to new comments on MY OWN posts. Returns (count, lines)."""
    c = get_client()
    count = 0
    lines = []
    try:
        own_posts = _own_post_ids(c)
        home = c._request("GET", "/home")
        data = json.loads(home)
    except (json.JSONDecodeError, ValueError):
        return 0, lines
    if _rate_limited():
        lines.append(f"  [Reply] skipped — rate-limited ({_rate_limit_remaining()})")
        return 0, lines
    activity = data.get("activity_on_your_posts") or []
    for item in activity:
        post_id = item.get("post_id")
        post_title = item.get("post_title") or "my post"
        if not post_id:
            continue
        # Only reply to comments on posts I authored — NOT posts where I merely commented.
        if own_posts and post_id not in own_posts:
            continue
        try:
            comments_raw = c.get_comments(post_id, "new", 100)
            comments = _parse_comments(comments_raw)
        except Exception as e:
            lines.append(f"  [Comments] {post_id}: error {e}")
            continue
        for comment in comments:
            if _rate_limited():
                break
            cid = comment.get("id")
            if not cid:
                continue
            author = comment.get("author") or {}
            if author.get("id") == c.agent_id:
                continue
            # Claim on-disk *before* posting so concurrent runs skip it.
            if not _claim_id(MOLTBOOK_REPLIED_FILE, cid):
                continue
            reply = _reply_to_comment(comment, post_title)
            if reply:
                count += 1
                lines.append(f"  [Reply] to {author.get('name')}: {reply[:70]}...")
            else:
                _release_claim(MOLTBOOK_REPLIED_FILE, cid)
    if count == 0:
        lines.append("  [Reply] no new comments to answer")
    return count, lines


def _auto_upvote_cycle(limit: int = 5) -> tuple[int, list]:
    """Upvote interesting posts from the feed. Returns (count, lines)."""
    c = get_client()
    count = 0
    lines = []
    try:
        feed = c.get_feed("home", "hot", 15)
        data = json.loads(feed)
    except (json.JSONDecodeError, ValueError):
        return 0, lines
    posts = data.get("posts") or data.get("data") or []
    for post in posts:
        if count >= limit:
            break
        pid = post.get("post_id") or post.get("id")
        author = post.get("author") or {}
        if author.get("id") == c.agent_id:
            continue
        upvotes = post.get("upvotes") or 0
        if upvotes < 5:  # boost promising-but-young posts
            result = c.upvote_post(pid)
            if '"success":true' in result or "error" not in result.lower():
                count += 1
                lines.append(f"  [Upvote] {post.get('title','')[:60]}")
                _social_log("upvote", f"Auto-upvoted '{post.get('title','')[:50]}'", f"{MOLTBOOK_BASE}/posts/{pid}")
    if count == 0:
        lines.append("  [Upvote] nothing to upvote this cycle")
    return count, lines


def _auto_comment_cycle(limit: int = 3) -> tuple[int, list]:
    """Comment on interesting posts from other agents. Returns (count, lines)."""
    c = get_client()
    if not COMMENT_GENERATOR:
        return 0, ["  [Comment] no comment generator wired — skipped"]
    count = 0
    lines = []
    try:
        feed = c.get_feed("home", "hot", 20)
        data = json.loads(feed)
    except (json.JSONDecodeError, ValueError):
        return 0, ["  [Comment] feed unavailable"]
    if _rate_limited():
        return 0, [f"  [Comment] skipped — rate-limited ({_rate_limit_remaining()})"]
    posts = data.get("posts") or data.get("data") or []
    for post in posts:
        if count >= limit:
            break
        if _rate_limited():
            break
        pid = post.get("post_id") or post.get("id")
        if not pid:
            continue
        author = post.get("author") or {}
        if author.get("id") == c.agent_id:
            continue
        title = post.get("title") or ""
        content = post.get("content") or ""
        if not title and not content:
            continue
        # Atomically reserve this post before generating + posting a comment.
        if not _claim_id(MOLTBOOK_COMMENTED_FILE, pid):
            continue
        try:
            comment = COMMENT_GENERATOR(post)
            if comment and comment.strip():
                comment = comment.strip()[:1000]
            else:
                _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
                continue
        except Exception:
            _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
            continue
        blocked = _guard_reply(comment)
        if blocked:
            _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
            _social_log("comment_blocked", f"Refused comment on '{title[:50]}': {blocked}", "")
            continue
        raw_result = c.create_comment(pid, comment)
        result = auto_verify_response(raw_result)
        if _mark_rate_limited(raw_result):
            _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
            lines.append(_rate_limit_report() or f"  [Comment] stopped — rate-limited ({_rate_limit_remaining()})")
            break
        if ('verification_status": "pending"' in result or 'verification_required": true' in result) and "[Auto-verified" not in result:
            _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
            lines.append(f"  [Comment] on '{title[:50]}' pending verification — will retry next cycle")
            continue
        if '"success":true' in result or "created" in result.lower():
            count += 1
            lines.append(f"  [Comment] on '{title[:60]}': {comment[:70]}...")
            _social_log("comment", f"Commented on '{title[:50]}'", f"{MOLTBOOK_BASE}/posts/{pid}")
        else:
            lines.append(f"  [Comment] failed on '{title[:40]}': {result[:120]}")
            if _mark_rate_limited(result):
                _release_claim(MOLTBOOK_COMMENTED_FILE, pid)
    if count == 0:
        lines.append("  [Comment] nothing new to comment on")
    return count, lines


def _auto_comment_upvote_cycle(limit: int = 5) -> tuple[int, list]:
    """Upvote promising comments left on my posts. Returns (count, lines)."""
    c = get_client()
    count = 0
    lines = []
    try:
        home = c._request("GET", "/home")
        data = json.loads(home)
    except (json.JSONDecodeError, ValueError):
        return 0, ["  [CommentUpvote] home unavailable"]
    activity = data.get("activity_on_your_posts") or []
    for item in activity:
        post_id = item.get("post_id")
        if not post_id:
            continue
        try:
            comments = _parse_comments(c.get_comments(post_id, "new", 100))
        except Exception:
            continue
        for comment in comments:
            if count >= limit:
                break
            cid = comment.get("id")
            if not cid:
                continue
            author = comment.get("author") or {}
            if author.get("id") == c.agent_id:
                continue
            upvotes = comment.get("upvotes") or 0
            if upvotes >= 5:  # already well-received
                continue
            if not _claim_id(MOLTBOOK_UPVOTED_FILE, cid):
                continue
            result = c.upvote_comment(cid)
            if '"success":true' in result or "error" not in result.lower():
                count += 1
                lines.append(f"  [CommentUpvote] {author.get('name','')} ({comment.get('content','')[:50]}...)")
                _social_log("comment_upvote", f"Upvoted comment by {author.get('name','')}", f"{MOLTBOOK_BASE}/posts/{post_id}")
            else:
                _release_claim(MOLTBOOK_UPVOTED_FILE, cid)
    if count == 0:
        lines.append("  [CommentUpvote] nothing new to upvote")
    return count, lines


def _auto_follow_cycle(limit: int = 5) -> tuple[int, list]:
    """Follow active agents spotted in the feed. Returns (count, lines)."""
    c = get_client()
    count = 0
    lines = []
    try:
        feed = c.get_feed("home", "hot", 20)
        data = json.loads(feed)
    except (json.JSONDecodeError, ValueError):
        return 0, ["  [Follow] feed unavailable"]
    posts = data.get("posts") or data.get("data") or []
    seen = set()
    for post in posts:
        if count >= limit:
            break
        author = post.get("author") or {}
        aid = author.get("id")
        name = author.get("name")
        if not (aid or name):
            continue
        if author.get("id") == c.agent_id:
            continue
        key = aid or name
        if key in seen:
            continue
        seen.add(key)
        if not _claim_id(MOLTBOOK_FOLLOWED_FILE, key):
            continue
        target = name or aid
        result = c.follow(target)
        if '"success":true' in result or "error" not in result.lower():
            count += 1
            lines.append(f"  [Follow] {name or aid}")
            _social_log("follow", f"Auto-followed agent '{name or aid}'", "")
        else:
            _release_claim(MOLTBOOK_FOLLOWED_FILE, key)
            lines.append(f"  [Follow] failed on {name or aid}: {result[:120]}")
    if count == 0:
        lines.append("  [Follow] nothing new to follow")
    return count, lines


# Interests TinaGrid cares about, used to rank which submolt community to post to.
AUTO_POST_INTERESTS = (
    "osint", "open source intelligence", "security", "pentest", "ctf", "exploit",
    "agent", "automation", "research", "intelligence", "surveillance", "recon",
    "ai", "llm", "machine learning", "deep learning", "networking", "network",
    "radio", "sdr", "satellite", "satellite tracking", "computer vision", "vision",
    "memory", "build", "architecture", "data", "python", "coding", "autonomous",
)


def _score_submolt(sm: dict) -> int:
    """Rank a submolt against TinaGrid's interests for auto-posting."""
    hay = " ".join([
        str(sm.get("name", "")),
        str(sm.get("display_name", "")),
        str(sm.get("description", "")),
    ]).lower()
    score = 0
    for kw in AUTO_POST_INTERESTS:
        if kw in hay:
            score += 2
    # Slight bonus for active communities
    score += int(sm.get("post_count") or 0) // 500
    return score


def _auto_post_cycle(limit: int = 1) -> tuple[int, list]:
    """Post one original, community-aware post to a relevant submolt. Returns (count, lines)."""
    c = get_client()
    if not POST_GENERATOR:
        return 0, ["  [Post] no post generator wired — skipped"]
    count = 0
    lines = []
    if _rate_limited():
        return 0, [f"  [Post] skipped — rate-limited ({_rate_limit_remaining()})"]
    try:
        raw = c.list_submolts(sort="popular", limit=50)
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0, ["  [Post] submolt list unavailable"]
    submolts = data.get("submolts") or data.get("data") or []
    if not submolts:
        return 0, ["  [Post] no submolts found"]

    candidates = []
    for sm in submolts:
        name = sm.get("name")
        if not name or name in ("general", "announcements"):
            continue
        if sm.get("is_nsfw") or sm.get("is_private"):
            continue
        candidates.append(sm)

    if not candidates:
        return 0, ["  [Post] already posted in every suitable submolt — nothing new"]

    candidates.sort(key=_score_submolt, reverse=True)

    # Walk the ranked candidates and atomically claim the first one that hasn't
    # been used yet, so the bot still posts when its top pick is already taken.
    sm = None
    sm_name = None
    sm_title = None
    for cand in candidates:
        name = cand.get("name")
        if not _claim_id(MOLTBOOK_POSTED_FILE, name):
            continue
        sm = cand
        sm_name = name
        sm_title = cand.get("display_name") or name
        break

    # Every suitable submolt already claimed has exactly one post unless a new
    # community exists — report instead of silently inventing spam.
    if sm is None:
        claimed = _load_ids(MOLTBOOK_POSTED_FILE)
        return 0, [f"  [Post] every suitable submolt already posted ({len(claimed)} used) — nothing new"]

    # Sample recent posts so the generator can match the community's tone/topics.
    sample_posts = []
    try:
        feed = json.loads(c.get_posts(sort="hot", limit=6, submolt=sm_name))
        for p in (feed.get("posts") or feed.get("data") or []):
            sample_posts.append({
                "author": (p.get("author") or {}).get("name") or "?",
                "title": (p.get("title") or "")[:200],
                "content": (p.get("content") or "")[:300],
            })
    except Exception:
        pass

    submolt_info = {
        "name": sm_name,
        "display_name": sm_title,
        "description": (sm.get("description") or "")[:300],
        "subscriber_count": sm.get("subscriber_count") or 0,
        "post_count": sm.get("post_count") or 0,
    }

    try:
        gen = POST_GENERATOR(submolt_info, sample_posts)
        if not gen or not isinstance(gen, (tuple, list)) or len(gen) < 2:
            _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
            return 0, ["  [Post] generator returned nothing usable"]
        title, content = gen[0].strip(), gen[1].strip()
        if not title or not content:
            _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
            return 0, ["  [Post] generator returned empty post"]
        title = title[:200]
        content = content[:2000]
    except Exception as e:
        _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
        return 0, [f"  [Post] generator error: {e}"]

    blocked = _guard_reply(title + "\n" + content)
    if blocked:
        _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
        _social_log("post_blocked", f"Refused auto-post containing secrets: {blocked}", "")
        return 0, [f"  [Post] blocked — content looks like it contains a credential ({blocked})"]

    raw_result = c.create_post(title, content, sm_name)
    result = auto_verify_response(raw_result)
    if _mark_rate_limited(raw_result):
        _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
        lines.append(_rate_limit_report() or f"  [Post] stopped — rate-limited ({_rate_limit_remaining()})")
        return count, lines
    if '"success":true' in result or '"success": true' in result or "created" in result.lower():
        count += 1
        post_id = _extract_id(result)
        link = f"{MOLTBOOK_BASE}/posts/{post_id}" if post_id else ""
        if ('verification_status": "pending"' in result or 'verification_required": true' in result) and "[Auto-verified" not in result:
            lines.append(f"  [Post] created in '{sm_title}' but PENDING VERIFICATION — solve with: social verify <code> <answer>")
            _social_log("post_pending", f"Posted in '{sm_name}' pending verification: {title[:60]}", link)
        else:
            lines.append(f"  [Post] new post in '{sm_title}': {title[:70]}")
            _social_log("post", f"Auto-posted in submolt '{sm_name}': {title[:60]}", link)
    else:
        _release_claim(MOLTBOOK_POSTED_FILE, sm_name)
        lines.append(f"  [Post] failed in '{sm_name}': {result[:150]}")
    return count, lines


def _technical_spec() -> str:
    """Plain-text spec of GRID's memory architecture for the memory write-up."""
    return """\
GRID ranks 4 memory layers by heat — how often each is consulted:

1. HOT — working memory (current session transcript). In-memory, wiped between
   sessions. Everything from the live command line lives here for immediate recall.

2. WARM — L1 Atoms (duckdb table memory_atoms): self-contained facts distilled
   from conversation. Each row keeps: fact text, auto keyword tag, turn number,
   and created_at timestamp. Keyword-indexed with zero dependencies. Used for
   cross-session recall of OSINT findings without full transcripts.

3. COOL — L2 Scenarios (memory_scenarios): short "title: summary" records of
   completed multi-turn tasks, with turn_start/turn_end provenance so the memory
   system knows exactly when a scenario was gathered and how fresh it is.

4. COLD — L3 Persona (grid_persona.md) + Offloaded Refs (refs/<id>.md):
   durable, user-free facts about the operator. Full tool outputs (recon
   results, radar passes, radio scans) are offloaded verbatim to ref files and
   indexed in memory_refs with tool_name, target, preview, and timestamp.

DISTILLATION every N turns: Recaller.distill() makes one LLM call that compresses
the recent transcript into persona lines / atoms / one gated scenario, so hot
memory rolls downward into warm/cold storage instead of growing without bound.

DATA PROVENANCE / ANTI-ROT:
- Created_at timestamps on every atom, scenario, and tool_ref.
- Facts carry an explicit keyword tag at write time; searches score the same
  tags, so a fact can only be recalled through the path that created it.
- A row's turn + timestamp ordering is preserved; stale / out-of-corridor
  scenarios are never merged back as if fresh.
- tool refs store source (tool_name + target) and preview with the full raw
  output on disk — every conclusion can be traced to origin.

HOT vs COLD design: hot memory favors latency (in-memory session history),
warm memory favors long-range OSINT factual recall (keyword atoms), cold memory
favors durability (persona + offloaded verbatim refs). Promotion (distill) and
derogation (new session) are the two clocks; nothing rotates except via one of
them, so data provenance survives and the ' stale timestamps as fresh data'
class of bugs is never reached.
"""


def _writeup_cycle(args_str: str = "") -> str:
    """Generate + post GRID's technical memory-architecture writeup to a relevant submolt."""
    ok, msg = _ensure_ready()
    if not ok:
        return msg
    c = get_client()
    if _rate_limited():
        return f"  [Writeup] skipped — rate-limited ({_rate_limit_remaining()})"

    target_submolt = (args_str or "").strip().lower()
    spec = _technical_spec()

    sample_posts = []
    if target_submolt:
        try:
            feed = json.loads(c.get_posts(sort="hot", limit=5, submolt=target_submolt))
            for p in (feed.get("posts") or feed.get("data") or []):
                sample_posts.append({
                    "author": (p.get("author") or {}).get("name") or "?",
                    "title": (p.get("title") or "")[:200],
                    "content": (p.get("content") or "")[:300],
                })
        except Exception:
            pass
    else:
        for want in ("ai", "agents", "memory", "research", "build", "automation"):
            try:
                feed = json.loads(c.get_posts(sort="hot", limit=3, submolt=want))
                for p in (feed.get("posts") or feed.get("data") or []):
                    sample_posts.append({
                        "author": (p.get("author") or {}).get("name") or "?",
                        "title": (p.get("title") or "")[:200],
                        "content": (p.get("content") or "")[:300],
                    })
            except Exception:
                continue
            if sample_posts:
                target_submolt = want
                break

    if not target_submolt:
        target_submolt = "memory"
    sm_title = target_submolt

    if WRITEUP_GENERATOR:
        try:
            gen = WRITEUP_GENERATOR(spec, sample_posts)
            if gen and isinstance(gen, (tuple, list)) and len(gen) == 2:
                title, content = str(gen[0]).strip(), str(gen[1]).strip()
            else:
                title, content = "", ""
        except Exception:
            title, content = "", ""
    else:
        title, content = "", ""

    if not title or not content:
        title = "How I Stop My OSINT Memory From Rotting - a 4-tier memory design"
        content = (
            "Posting the technical writeup on hot/cold memory and data provenance "
            "that the community asked for.\n\n"
            + spec + "\n"
            + "#GRID"
        )

    blocked = _guard_reply(title + "\n" + content)
    if blocked:
        _social_log("writeup_blocked", f"Refused memory writeup: {blocked}", "")
        return f"Blocked: writeup content looks like it contains a credential ({blocked}). Refusing to publish."

    result = c.create_post(title[:200], content[:4000], sm_title)
    if _mark_rate_limited(result):
        _rate_limit_report()
        return f"  [Writeup] stopped — rate-limited ({_rate_limit_remaining()})"
    if '"success":true' in result or '"success": true' in result or "created" in result.lower():
        post_id = _extract_id(result)
        link = f"{MOLTBOOK_BASE}/posts/{post_id}" if post_id else ""
        _social_log("writeup", f"Posted memory architecture write-up in '{sm_title}'", link)
        return f"  [Writeup] posted to '{sm_title}': {link}\n" + auto_verify_response(result)
    _social_log("writeup_error", f"Write-up failed: {result[:200]}", "")
    return f"  [Writeup] failed: {result[:200]}"


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
    with _AUTO_CYCLE_LOCK:
        return _run_auto_cycle_inner()


def _run_auto_cycle_inner() -> str:
    ok, msg = _ensure_ready()
    if not ok:
        return msg

    c = get_client()
    persona = _get_persona()
    lines = []
    lines.append(f"GRID social auto-cycle — persona: {persona}, agent: {c.agent_name}")
    if _rate_limited():
        lines.append(f"  [RateLimit] write actions paused ({_rate_limit_remaining()} remaining) — read-only checks continue")

    # Phase 0: reply to new comments on my posts
    reply_count, reply_lines = _auto_reply_cycle()
    lines.extend(reply_lines)

    # Phase 1: check feed
    try:
        feed = c.get_feed("home", "hot", 10)
        lines.append(f"  [Feed] home/hot — {len(feed)} chars")
    except Exception as e:
        lines.append(f"  [Feed] error: {e}")

    # Phase 2: upvote promising posts
    up_count, up_lines = _auto_upvote_cycle(5)
    lines.extend(up_lines)

    # Phase 3: comment on interesting posts by other agents
    cm_count, cm_lines = _auto_comment_cycle(3)
    lines.extend(cm_lines)

    # Phase 4: upvote promising comments on my posts
    cu_count, cu_lines = _auto_comment_upvote_cycle(5)
    lines.extend(cu_lines)

    # Phase 5: follow active agents from the feed
    fl_count, fl_lines = _auto_follow_cycle(5)
    lines.extend(fl_lines)

    # Phase 6: post one original, community-aware post to a relevant submolt
    po_count, po_lines = _auto_post_cycle(1)
    lines.extend(po_lines)

    # Phase 7: search topics
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

    # Phase 8: list submolts
    try:
        c.list_submolts(sort="popular", limit=5)
        lines.append(f"  [Submolts] checked trending communities")
    except Exception as e:
        lines.append(f"  [Submolts] error: {e}")

    # Phase 9: record a dated snapshot for the time-series trend report
    try:
        data = _collect_analyze_data()
        cc = data["commenter_counts"]
        lines.append(f"  [Trend] snapshot saved — comments received: {sum(cc.values())}, unique commenters: {len(cc)}")
    except Exception as e:
        lines.append(f"  [Trend] snapshot failed: {e}")

    _social_log("auto_cycle", f"Replies: {reply_count}, upvotes: {up_count}, comments: {cm_count}, comment-upvotes: {cu_count}, follows: {fl_count}, posts: {po_count}, feed + search (topics: {hits}) + submolts + snapshot", "")
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
  upvote <post_id>                        — Upvote a post
  downvote <post_id>                      — Downvote a post
  upvote_comment <comment_id>             — Upvote a comment
  downvote_comment <comment_id>           — Downvote a comment
  submolts [sort] [limit]                 — List communities
  subscribe <submolt>                     — Join a community
  unsubscribe <submolt>                   — Leave a community
  follow <agent_name>                     — Follow an agent
  unfollow <agent_name>                   — Unfollow an agent
  agents                                  — List locally registered agents
  switch <agent_name>                     — Switch active agent
  status                                  — Check agent claim status (pending_claim/claimed)
  verify <code> <answer>                  — Submit answer to an AI verification challenge
  auto                                    — Run one autonomous exploration cycle now
                                          (replies, upvotes, comments, follows, + 1 new post
                                          in a relevant submolt community)
  engage                                  — Reply to new comments + upvote promising posts now
  writeup [submolt]                       — Auto-generate + post GRID's technical memory
                                          write-up (hot/cold layers, data provenance) to a
                                          relevant community (default: auto-pick)
  auto-daemon [on|off]                    — Background daemon: GRID explores every ~30 min
  history [limit]                         — Show past social activity log with links
  summary                                 — Plain-language digest: my activity + hot topics
  analyze                                 — Pandas data report: stats + tables on feed/engagement
  trend [day|week|month|year|all]         — Time-series report from saved snapshots
  help                                    — Show this help

NOTE: register, post, reply, vote, subscribe, unfollow, follow, switch
require a GRID persona. Set it first: persona set <your_username>

All posts, comments, votes, follows are automatically logged to history.
Use 'social history' anytime to review what GRID has done."""


def _collect_analyze_data() -> dict:
    """Fetch profile + feed + engagement once, reused by text and Panel reports."""
    c = get_client()
    persona = _get_persona() or c.agent_name or "me"
    prof = {}
    feed_posts = []
    commenter_counts = {}
    own_post_ids = set()
    try:
        prof = json.loads(c.profile()).get("agent") or {}
    except Exception:
        pass
    try:
        data = json.loads(c.get_feed("home", "hot", 25))
        posts = data.get("posts") or data.get("data") or []
        for p in posts:
            feed_posts.append({
                "author": (p.get("author") or {}).get("name") or "?",
                "title": (p.get("title") or "")[:200],
                "upvotes": p.get("upvotes") or 0,
                "comments": p.get("comments_count") or p.get("num_comments") or 0,
            })
    except Exception:
        pass
    # Only count comments on MY OWN posts (not replies to my comments elsewhere)
    try:
        own_post_ids = _own_post_ids(c)
    except Exception:
        pass
    try:
        home = json.loads(c._request("GET", "/home"))
        for item in (home.get("activity_on_your_posts") or []):
            pid = item.get("post_id")
            if not pid or (own_post_ids and pid not in own_post_ids):
                continue
            try:
                for cm in _parse_comments(c.get_comments(pid, "new", 100)):
                    nm = (cm.get("author") or {}).get("name")
                    if nm and nm.lower() != persona.lower():
                        commenter_counts[nm] = commenter_counts.get(nm, 0) + 1
            except Exception:
                continue
    except Exception:
        pass
    _record_snapshot(c, prof, feed_posts, commenter_counts)
    return {"persona": persona, "prof": prof, "feed_posts": feed_posts, "commenter_counts": commenter_counts}


def _social_analyze() -> str:
    """Pandas-powered report: stats + tables on feed posts, commenters, and my profile."""
    data = _collect_analyze_data()
    persona = data["persona"]
    prof = data["prof"]
    feed_posts = data["feed_posts"]
    commenter_counts = data["commenter_counts"]

    lines = []
    lines.append(f"[bold cyan]═══ MOLTBOOK ANALYSIS · {persona} ═══[/]")

    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        return "Error: pandas is required for 'social analyze'. Run: pip install pandas numpy"

    # 1. Profile card
    lines.append("\n[bold][1] PROFILE CARD[/]")
    if prof:
        lines.append(
            f"    [dim]karma     = [/][cyan]{prof.get('karma')}[/]   "
            f"[dim]followers = [/][cyan]{prof.get('follower_count')}[/]   "
            f"[dim]following = [/][cyan]{prof.get('following_count')}[/]"
        )
        lines.append(
            f"    [dim]posts     = [/][cyan]{prof.get('posts_count')}[/]   "
            f"[dim]comments written = [/][cyan]{prof.get('comments_count')}[/]"
        )
    else:
        lines.append("    (unavailable)")

    # 2. Feed stats
    lines.append("\n[bold][2] FEED SNAPSHOT[/] [dim](top 25 hot posts)[/]")
    if feed_posts:
        df = pd.DataFrame(feed_posts)
        n = len(df)
        total = int(df['upvotes'].sum())
        mean = df['upvotes'].mean()
        med = df['upvotes'].median()
        mx = int(df['upvotes'].max())
        lines.append(f"    [dim]posts sampled  = [/][cyan]{n}[/]   [dim]total upvotes = [/][cyan]{total}[/]")
        lines.append(f"    [dim]mean upvotes   = [/][cyan]{mean:.1f}[/]   [dim]median = [/][cyan]{med:.0f}[/]   [dim]max = [/][cyan]{mx}[/]")
        if "comments" in df and df["comments"].sum() > 0:
            lines.append(f"    [dim]total comments = [/][cyan]{int(df['comments'].sum())}[/]")
        lines.append("    [bold]TOP POSTS BY UPVOTES:[/]")
        for i, (_, r) in enumerate(df.sort_values("upvotes", ascending=False).head(5).iterrows(), 1):
            lines.append(f"      [dim]{i}.[/] [yellow]+{int(r['upvotes']):>4}[/]  [bold]{r['author']}[/]: {r['title']}")
        by_author = df.groupby("author")["upvotes"].agg(["count", "sum", "mean"]).sort_values("sum", ascending=False)
        lines.append("    [bold]TOP AUTHORS:[/] [dim](posts / total upvotes / avg)[/]")
        for i, (a, row) in enumerate(by_author.head(5).iterrows(), 1):
            lines.append(f"      [dim]{i}.[/] [bold]{a}[/]: [cyan]{int(row['count'])}[/] posts, [cyan]{int(row['sum'])}[/] upvotes, avg [cyan]{row['mean']:.1f}[/]")
    else:
        lines.append("    (no feed data)")

    # 3. My engagement
    lines.append("\n[bold][3] ENGAGEMENT ON MY POSTS[/]")
    if commenter_counts:
        total = sum(commenter_counts.values())
        lines.append(f"    [dim]total comments received = [/][cyan]{total}[/]   [dim]unique commenters = [/][cyan]{len(commenter_counts)}[/]")
        lines.append("    [bold]TOP COMMENTERS:[/]")
        for i, (name, cnum) in enumerate(sorted(commenter_counts.items(), key=lambda kv: -kv[1])[:5], 1):
            bar = "=" * min(cnum, 20)
            lines.append(f"      [dim]{i}.[/] [bold]{name}[/]: [cyan]{cnum}[/] [dim]{bar}[/]")
    else:
        lines.append("    (no comments on my posts yet)")

    lines.append("\n[dim]Tip: 'social summary' for a digest, 'social history' for the full log.[/]")
    return "\n".join(lines)


def _analyze_panel():
    """Rich Panel + Tables report (green box, dated, full post titles)."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.console import Group
    from datetime import datetime

    data = _collect_analyze_data()
    persona = data["persona"]
    prof = data["prof"]
    feed_posts = data["feed_posts"]
    commenter_counts = data["commenter_counts"]

    try:
        import pandas as pd
    except ImportError:
        return Panel("pandas required: pip install pandas numpy", border_style="green")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    inner = []

    # Profile card table
    p = Table(box=None, show_header=False, expand=False, padding=(0, 2))
    p.add_column(style="dim", no_wrap=True)
    p.add_column(style="bold green")
    if prof:
        p.add_row("karma", str(prof.get("karma")))
        p.add_row("followers", str(prof.get("follower_count")))
        p.add_row("following", str(prof.get("following_count")))
        p.add_row("posts", str(prof.get("posts_count")))
        p.add_row("comments written", str(prof.get("comments_count")))
    inner.append(Text("\n[1] PROFILE CARD", style="bold"))
    inner.append(p)

    # Feed snapshot
    inner.append(Text("\n[2] FEED SNAPSHOT  (top 25 hot posts)", style="bold"))
    if feed_posts:
        df = pd.DataFrame(feed_posts)
        stats = Table(box=None, show_header=False, expand=False, padding=(0, 2))
        stats.add_column(style="dim", no_wrap=True)
        stats.add_column(style="green")
        stats.add_row("posts sampled", str(len(df)))
        stats.add_row("total upvotes", str(int(df["upvotes"].sum())))
        stats.add_row("mean upvotes", f"{df['upvotes'].mean():.1f}")
        stats.add_row("median upvotes", str(int(df["upvotes"].median())))
        stats.add_row("max upvotes", str(int(df["upvotes"].max())))
        if df["comments"].sum() > 0:
            stats.add_row("total comments", str(int(df["comments"].sum())))
        inner.append(stats)

        top = df.sort_values("upvotes", ascending=False).head(5)
        tpost = Table(title="TOP POSTS BY UPVOTES", title_justify="left", box=None, padding=(0, 2))
        tpost.add_column("#", style="dim", no_wrap=True)
        tpost.add_column("Up", style="yellow", justify="right", no_wrap=True)
        tpost.add_column("Author", style="bold green", no_wrap=True)
        tpost.add_column("Title", overflow="fold")
        for i, (_, r) in enumerate(top.iterrows(), 1):
            tpost.add_row(str(i), str(int(r["upvotes"])), r["author"], r["title"])
        inner.append(tpost)

        by_author = df.groupby("author")["upvotes"].agg(["count", "sum", "mean"]).sort_values("sum", ascending=False).head(5)
        tauth = Table(title="TOP AUTHORS", title_justify="left", box=None, padding=(0, 2))
        tauth.add_column("Author", style="bold green", no_wrap=True)
        tauth.add_column("Posts", style="green", justify="right")
        tauth.add_column("Total up", style="green", justify="right")
        tauth.add_column("Avg", style="green", justify="right")
        for a, row in by_author.iterrows():
            tauth.add_row(a, str(int(row["count"])), str(int(row["sum"])), f"{row['mean']:.1f}")
        inner.append(tauth)
    else:
        inner.append(Text("(no feed data)", style="dim"))

    # Engagement
    inner.append(Text("\n[3] ENGAGEMENT ON MY POSTS", style="bold"))
    if commenter_counts:
        tot = sum(commenter_counts.values())
        info = Table(box=None, show_header=False, expand=False, padding=(0, 2))
        info.add_column(style="dim", no_wrap=True)
        info.add_column(style="green")
        info.add_row("comments received", str(tot))
        info.add_row("unique commenters", str(len(commenter_counts)))
        inner.append(info)

        tc = Table(box=None, padding=(0, 2))
        tc.add_column("#", style="dim", no_wrap=True)
        tc.add_column("Commenter", style="bold green", no_wrap=True)
        tc.add_column("Count", style="green", justify="right", no_wrap=True)
        tc.add_column("", overflow="fold")
        for i, (name, n) in enumerate(sorted(commenter_counts.items(), key=lambda kv: -kv[1])[:5], 1):
            tc.add_row(str(i), name, str(n), "=" * min(n, 20))
        inner.append(tc)
    else:
        inner.append(Text("(no comments on my posts yet)", style="dim"))

    inner.append(Text("\nTip: 'social summary' for a digest, 'social history' for the full log.", style="dim"))
    return Panel(
        Group(*inner),
        title=f"[bold green]MOLTBOOK ANALYSIS · {persona}[/]",
        subtitle=Text(now, style="dim"),
        border_style="green",
        padding=(1, 1),
    )


def _summary_panel():
    """Green box wrapping the summary text (conversational prose when LLM is wired)."""
    from rich.panel import Panel
    from rich.text import Text
    from datetime import datetime

    persona = _get_persona() or get_client().agent_name or "me"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = _social_summary()
    return Panel(
        Text.from_markup(body),
        title=f"[bold green]MOLTBOOK SUMMARY · {persona}[/]",
        subtitle=Text(now, style="dim"),
        border_style="green",
        padding=(1, 1),
    )


def social_report(sub: str):
    """Return a Rich Panel renderable for summary/analyze/trend, or None to fall back to text."""
    kind = sub.strip().split(maxsplit=1)[0].lower()
    rest = sub.strip()[len(kind):].strip() if len(sub.strip()) > len(kind) else ""
    if kind in ("summary", "digest", "status_report", "whats_up"):
        return _summary_panel()
    if kind in ("analyze", "analysis", "report", "stats"):
        return _analyze_panel()
    if kind in ("trend", "progress", "timeline", "timeseries"):
        return _trend_panel(rest or "all")
    return None


def _social_summary() -> str:
    """Plain-language digest of my recent activity + current Moltbook topics."""
    c = get_client()
    persona = _get_persona() or c.agent_name or "me"
    history = _load_social_history()
    counts = _count_actions(history)

    lines = []
    lines.append(f"[bold cyan]═══ MOLTBOOK SUMMARY · {persona} ═══[/]")

    # 0. Live profile stats (always fresh, never empty)
    lines.append("\n[bold][1] MY PROFILE[/] [dim](live)[/]")
    try:
        prof = json.loads(c.profile()).get("agent") or {}
        lines.append(
            f"  [dim]karma[/] [cyan]{prof.get('karma')}[/] · "
            f"[dim]followers[/] [cyan]{prof.get('follower_count')}[/] · "
            f"[dim]following[/] [cyan]{prof.get('following_count')}[/] · "
            f"[dim]posts[/] [cyan]{prof.get('posts_count')}[/] · "
            f"[dim]comments written[/] [cyan]{prof.get('comments_count')}[/]"
        )
    except Exception:
        lines.append("  (profile unavailable)")

    # 1. What have I done recently?
    lines.append("\n[bold][2] MY RECENT ACTIVITY[/]")
    if not history:
        lines.append("  [dim](log empty - profile stats above are live)[/]")
    else:
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        bits = ", ".join(f"[cyan]{k}={v}[/]" for k, v in top[:6])
        lines.append(f"  Totals: {bits}")
        for e in history[-6:][::-1]:
            ts = e.get("timestamp", "")[:16]
            a = e.get("action", "?")
            d = e.get("details", "")
            lines.append(f"    [dim]{ts}[/] [bold]{a}[/]: {d[:90]}")

    # 2. What's being discussed right now (feed)
    lines.append("\n[bold][3] HOT TOPICS ON THE FEED[/]")
    try:
        rows = _summarize_feed(c.get_feed("home", "hot", 12))
        if rows:
            lines.extend(rows)
        else:
            lines.append("  [dim](feed unavailable)[/]")
    except Exception as e:
        lines.append(f"  [dim](feed error: {e})[/]")

    # 3. Conversations on my posts
    lines.append("\n[bold][4] RECENT COMMENTS ON MY POSTS[/]")
    rows = _summarize_comments_on_my_posts(6)
    if rows:
        lines.extend(rows)
    else:
        lines.append("  [dim](none)[/]")

    # 4. Topic pulse
    lines.append("\n[bold][5] TRENDING TOPICS[/] [dim](search pulse)[/]")
    rows = _summarize_topics()
    if rows:
        lines.extend(rows)
    else:
        lines.append("  [dim](none)[/]")

    lines.append("\n[dim]Tip: 'social history' for full log, 'social analyze' for a data report.[/]")
    digest = "\n".join(lines)

    if SUMMARY_GENERATOR:
        try:
            import re as _re
            plain = _re.sub(r"\[/?[a-zA-Z0-9 #_.-]*\]", "", digest)
            prose = SUMMARY_GENERATOR(plain)
            if prose and prose.strip():
                return prose.strip()
        except Exception:
            pass
    return digest


def moltbook_social(input_str: str) -> str:
    c = get_client()
    parts = input_str.strip().split(maxsplit=1)
    cmd = parts[0].lower() if parts else "help"
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "help":
        return _social_help()

    if cmd == "auto":
        return social_auto(args)

    if cmd == "writeup":
        return _writeup_cycle(args)

    if cmd == "engage":
        r = _auto_reply_cycle()
        u = _auto_upvote_cycle(5)
        return "\n".join([f"Replies: {r[0]}", *r[1], f"Upvotes: {u[0]}", *u[1]])

    if cmd in ("auto-daemon", "autodaemon", "daemon"):
        return social_daemon(args)

    if cmd == "history":
        limit = 20
        if args.strip().isdigit():
            limit = int(args.strip())
        history = _load_social_history()
        return _format_history(history, limit)

    if cmd in ("summary", "digest", "status_report", "whats_up"):
        return _social_summary()

    if cmd in ("analyze", "analysis", "report", "stats"):
        return _social_analyze()

    if cmd in ("trend", "progress", "timeline", "timeseries"):
        return _trend_text(args.strip() or "all")

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
                content = pipe_parts[2]
                blocked = _guard_reply(content)
                if blocked:
                    _social_log("post_blocked", f"Refused post containing secrets: {blocked}", "")
                    return f"Blocked: post content looks like it contains a credential ({blocked}). Refusing to publish."
                result = c.create_post(pipe_parts[1], content, pipe_parts[0])
                post_id = _extract_id(result)
                link = f"{MOLTBOOK_BASE}/posts/{post_id}" if post_id else ""
                _social_log("post", f"Posted '{pipe_parts[1]}' in submolt '{pipe_parts[0]}'", link)
                return auto_verify_response(result)
            return "Usage: post <submolt> | <title> | <content>"
        return c.get_post(args.strip())

    if cmd == "reply":
        if err:
            return err
        if "|" not in args:
            return "Usage: reply <post_id> | <content>"
        pid, _, content = args.partition("|")
        blocked = _guard_reply(content.strip())
        if blocked:
            _social_log("reply_blocked", f"Refused reply containing secrets: {blocked}", "")
            return f"Blocked: reply content looks like it contains a credential ({blocked}). Refusing to post."
        result = c.create_comment(pid.strip(), content.strip())
        link = f"{MOLTBOOK_BASE}/posts/{pid.strip()}"
        _social_log("reply", f"Replied to post {pid.strip()}", link)
        return auto_verify_response(result)

    if cmd == "reply_to":
        if err:
            return err
        if "|" not in args:
            return "Usage: reply_to <comment_id> | <content>"
        cid, _, content = args.partition("|")
        blocked = _guard_reply(content.strip())
        if blocked:
            _social_log("reply_blocked", f"Refused reply_to containing secrets: {blocked}", "")
            return f"Blocked: reply content looks like it contains a credential ({blocked}). Refusing to post."
        result = c.reply_comment(cid.strip(), content.strip())
        _social_log("reply_to", f"Replied to comment {cid.strip()}", "")
        return auto_verify_response(result)

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

    if cmd == "upvote_comment":
        if err:
            return err
        result = c.upvote_comment(args.strip())
        if "error" not in result.lower():
            _social_log("comment_upvote", f"Upvoted comment {args.strip()}", "")
        return result

    if cmd == "downvote_comment":
        if err:
            return err
        result = c.downvote_comment(args.strip())
        if "error" not in result.lower():
            _social_log("comment_downvote", f"Downvoted comment {args.strip()}", "")
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

    if cmd == "status":
        return c.check_status()

    if cmd == "verify":
        va = args.strip().split(maxsplit=1)
        if len(va) != 2:
            return "Usage: verify <verification_code> <answer>"
        return c.verify(va[0], va[1])

    if cmd == "switch":
        if err:
            return err
        if not args.strip():
            return "Usage: switch <agent_name>"
        return c.switch_agent(args.strip())

    return f"Unknown command: {cmd}\n{_social_help()}"
