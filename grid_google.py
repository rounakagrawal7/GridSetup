"""
GRID v2 — Google API Integration
Calendar, and extensible for Drive, Gmail, and other Google APIs.
OAuth2 — user credentials NEVER stored in source, only in config.json + token.json.
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

CONFIG_FILE = "config.json"
TOKEN_FILE = "google_token.json"
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]
SCOPES_DEFAULT = SCOPES_CALENDAR


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


def _google_creds_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("google_client_id") and cfg.get("google_client_secret"))


# ── Auth ────────────────────────────────────────────────────────

GOOGLE_SETUP_HELP = """\
GRID needs Google API credentials to access Calendar (and other Google APIs).
These are YOUR credentials from Google Cloud Console — they stay on your machine.

Setup steps:
  1. Go to https://console.cloud.google.com/apis/credentials
  2. Create a project (or select existing)
  3. Enable the Google Calendar API (and any others you want)
  4. Create OAuth 2.0 Client ID → "Desktop app"
  5. Copy the Client ID and Client Secret
  6. In GRID:  /gcal setup <client_id> <client_secret>

Credentials are saved in config.json — never in source code.
"""


def _get_credentials() -> Optional[any]:
    """Returns google.oauth2.credentials.Credentials or None."""
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES_DEFAULT)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        if creds and creds.valid:
            return creds

    cfg = _load_config()
    cid = cfg.get("google_client_id")
    csecret = cfg.get("google_client_secret")
    if not cid or not csecret:
        return None

    client_config = {
        "installed": {
            "client_id": cid,
            "client_secret": csecret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES_DEFAULT)
    creds = flow.run_local_server(port=0, open_browser=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds


# ── CalendarClient ──────────────────────────────────────────────

class CalendarClient:
    def __init__(self):
        self.service = None

    def _ensure(self):
        if self.service:
            return
        creds = _get_credentials()
        if not creds:
            raise RuntimeError("Google not authenticated. Run /gcal setup first.")
        from googleapiclient.discovery import build
        self.service = build("calendar", "v3", credentials=creds)

    # ── Calendar list ───────────────────────────────────────────

    def list_calendars(self) -> str:
        self._ensure()
        result = self.service.calendarList().list().execute()
        items = result.get("items", [])
        if not items:
            return "No calendars found."
        lines = [f"Calendars ({len(items)}):"]
        for cal in items:
            lines.append(f"  {cal.get('summary', '?')}  [{cal['id']}]")
        return "\n".join(lines)

    # ── Events ──────────────────────────────────────────────────

    def list_events(self, calendar_id: str = "primary", max_results: int = 10,
                    time_min: Optional[str] = None, time_max: Optional[str] = None) -> str:
        self._ensure()
        now = datetime.utcnow().isoformat() + "Z"
        params = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": time_min or now,
        }
        if time_max:
            params["timeMax"] = time_max
        events = self.service.events().list(**params).execute()
        items = events.get("items", [])
        if not items:
            return "No upcoming events found."
        lines = [f"Events ({len(items)}):"]
        for e in items:
            start = e["start"].get("dateTime", e["start"].get("date"))
            lines.append(f"  {start}  {e.get('summary', '(no title)')}  [{e['id']}]")
        return "\n".join(lines)

    def create_event(self, calendar_id: str, summary: str,
                     start_dt: str, end_dt: str,
                     description: str = "", location: str = "") -> str:
        self._ensure()
        event = {
            "summary": summary,
            "start": {"dateTime": start_dt, "timeZone": "UTC"},
            "end": {"dateTime": end_dt, "timeZone": "UTC"},
        }
        if description:
            event["description"] = description
        if location:
            event["location"] = location
        created = self.service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"Event created: {created.get('htmlLink', created['id'])}"

    def update_event(self, calendar_id: str, event_id: str,
                     summary: Optional[str] = None,
                     start_dt: Optional[str] = None,
                     end_dt: Optional[str] = None,
                     description: Optional[str] = None,
                     location: Optional[str] = None) -> str:
        self._ensure()
        event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        if summary:
            event["summary"] = summary
        if start_dt:
            event["start"] = {"dateTime": start_dt, "timeZone": "UTC"}
        if end_dt:
            event["end"] = {"dateTime": end_dt, "timeZone": "UTC"}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        updated = self.service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        return f"Event updated: {updated.get('htmlLink', updated['id'])}"

    def delete_event(self, calendar_id: str, event_id: str) -> str:
        self._ensure()
        self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return f"Event {event_id} deleted."

    def get_event(self, calendar_id: str, event_id: str) -> str:
        self._ensure()
        event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        lines = [f"Event: {event.get('summary', '(no title)')}"]
        s = event["start"].get("dateTime", event["start"].get("date"))
        e = event["end"].get("dateTime", event["end"].get("date"))
        lines.append(f"  Start: {s}")
        lines.append(f"  End:   {e}")
        if event.get("location"):
            lines.append(f"  Location: {event['location']}")
        if event.get("description"):
            lines.append(f"  Description: {event['description'][:500]}")
        lines.append(f"  ID: {event['id']}")
        return "\n".join(lines)

    def search_events(self, query: str, calendar_id: str = "primary", max_results: int = 10) -> str:
        self._ensure()
        now = datetime.utcnow().isoformat() + "Z"
        events = self.service.events().list(
            calendarId=calendar_id, maxResults=max_results,
            singleEvents=True, orderBy="startTime",
            timeMin=now, q=query
        ).execute()
        items = events.get("items", [])
        if not items:
            return f"No matching events for: {query}"
        lines = [f"Events matching '{query}':"]
        for e in items:
            start = e["start"].get("dateTime", e["start"].get("date"))
            lines.append(f"  {start}  {e.get('summary', '(no title)')}  [{e['id']}]")
        return "\n".join(lines)


# ── Global client singleton ──────────────────────────────────────

_client: Optional[CalendarClient] = None


def get_client() -> CalendarClient:
    global _client
    if _client is None:
        _client = CalendarClient()
    return _client


# ═══════════════════════════════════════════════════════════════════
# Tool function
# ═══════════════════════════════════════════════════════════════════

def _gcal_help() -> str:
    return """Google Calendar commands (prefix with tool name or use /gcal):
  setup <client_id> <client_secret>   — Authenticate with Google (first time)
  calendars                            — List your calendars
  events [cal_id] [count]              — List upcoming events
  event <event_id> [cal_id]            — Get event details
  create <cal_id> | <summary> | <start> | <end> [| desc] [| loc]
                                       — Create an event (ISO 8601 times)
  update <event_id> [cal_id] | <field>=<value> ...
                                       — Update event fields (summary/start/end/desc/loc)
  delete <event_id> [cal_id]           — Delete an event
  search <query> [cal_id] [count]      — Search events
  help                                 — Show this help

ISO 8601 format: 2026-07-29T14:00:00 or 2026-07-29 (all-day)
Calendar ID defaults to 'primary' (your main calendar)."""


def google_calendar(input_str: str) -> str:
    parts = input_str.strip().split(maxsplit=1)
    cmd = parts[0].lower() if parts else "help"
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "help":
        return _gcal_help()

    if cmd == "setup":
        sa = args.split(maxsplit=1)
        cid = sa[0] if sa else ""
        csecret = sa[1] if len(sa) > 1 else ""
        if not cid or not csecret:
            return "Usage: setup <client_id> <client_secret>\n" + GOOGLE_SETUP_HELP
        cfg = _load_config()
        cfg["google_client_id"] = cid
        cfg["google_client_secret"] = csecret
        _save_config(cfg)
        return "Google credentials saved. Now run the same command again to complete OAuth.\n/gcal events"

    try:
        c = get_client()
    except Exception as e:
        return f"Google auth error: {e}\nRun /gcal setup first."

    try:
        if cmd == "calendars":
            return c.list_calendars()

        if cmd == "events":
            ea = args.split()
            cal_id = ea[0] if ea else "primary"
            count = int(ea[1]) if len(ea) > 1 and ea[1].isdigit() else 10
            return c.list_events(calendar_id=cal_id, max_results=count)

        if cmd == "event":
            ea = args.split()
            eid = ea[0] if ea else ""
            if not eid:
                return "Usage: event <event_id> [calendar_id]"
            cal_id = ea[1] if len(ea) > 1 else "primary"
            return c.get_event(cal_id, eid)

        if cmd == "create":
            if "|" not in args:
                return "Usage: create <cal_id> | <summary> | <start> | <end> [| desc] [| loc]"
            pipe = [x.strip() for x in args.split("|")]
            cal_id = pipe[0] if len(pipe) > 0 else "primary"
            summary = pipe[1] if len(pipe) > 1 else ""
            start = pipe[2] if len(pipe) > 2 else ""
            end = pipe[3] if len(pipe) > 3 else ""
            desc = pipe[4] if len(pipe) > 4 else ""
            loc = pipe[5] if len(pipe) > 5 else ""
            if not summary or not start or not end:
                return "Usage: create <cal_id> | <summary> | <start> | <end> [| desc] [| loc]"
            return c.create_event(cal_id, summary, start, end, desc, loc)

        if cmd == "update":
            if "|" not in args:
                return "Usage: update <event_id> [cal_id] | <field>=<value> ..."
            left, _, right = args.partition("|")
            left_parts = left.strip().split()
            eid = left_parts[0] if left_parts else ""
            cal_id = left_parts[1] if len(left_parts) > 1 else "primary"
            if not eid:
                return "Usage: update <event_id> [cal_id] | <field>=<value> ..."
            kwargs = {}
            for pair in right.split("|"):
                pair = pair.strip()
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    k = k.strip().lower()
                    if k in ("summary", "start", "end", "description", "desc", "location", "loc"):
                        if k in ("desc",):
                            k = "description"
                        if k in ("loc",):
                            k = "location"
                        kwargs[k] = v.strip()
            if not kwargs:
                return "No fields to update. Use: summary=..., start=..., end=..., desc=..., loc=..."
            return c.update_event(cal_id, eid, **kwargs)

        if cmd == "delete":
            ea = args.split()
            eid = ea[0] if ea else ""
            if not eid:
                return "Usage: delete <event_id> [calendar_id]"
            cal_id = ea[1] if len(ea) > 1 else "primary"
            return c.delete_event(cal_id, eid)

        if cmd == "search":
            # search <query> [cal_id] [count]
            sa = args.split(maxsplit=2)
            if not sa:
                return "Usage: search <query> [calendar_id] [count]"
            query = sa[0]
            cal_id = "primary"
            count = 10
            if len(sa) > 1:
                if sa[1].isdigit():
                    count = int(sa[1])
                else:
                    cal_id = sa[1]
            if len(sa) > 2:
                if sa[2].isdigit():
                    count = int(sa[2])
            return c.search_events(query, cal_id, count)

        return f"Unknown command: {cmd}\n{_gcal_help()}"
    except Exception as e:
        return f"Error: {e}"
