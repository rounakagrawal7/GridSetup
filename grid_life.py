"""GRID Life - persistent identity, agenda, heartbeat, and iLog.

This module is deliberately independent of grid_agent.py so the life loop can
be tested without a model, network, terminal, or the full tool registry.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional


LIFE_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "heartbeat_minutes": 30,
    "quiet_hours": ["22:00", "08:00"],
    "brief_time": "09:00",
    "brief_window_minutes": 30,
    "max_actions_per_day": 12,
    "max_messages_per_day": 6,
    "goal_stale_hours": 6,
    "reflection_hours": 24,
    "commitment_repeat_hours": 6,
    "identity_name": "GRID",
    "voice": "direct, curious, calm",
    "values": "local-first, honesty, consent, usefulness",
    "boundaries": (
        "Ask before external actions. No continuous screen or microphone "
        "capture. Rest when paused."
    ),
}


def _merge_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(LIFE_DEFAULTS)
    if config:
        for key, value in config.items():
            if value is not None:
                merged[key] = value
    return merged


def _parse_hhmm(value: Any) -> Optional[dtime]:
    try:
        hour, minute = str(value).split(":", 1)
        return dtime(int(hour), int(minute))
    except (TypeError, ValueError):
        return None


def _in_quiet_hours(now: datetime, quiet: Any) -> bool:
    if not isinstance(quiet, (list, tuple)) or len(quiet) != 2:
        return False
    start = _parse_hhmm(quiet[0])
    end = _parse_hhmm(quiet[1])
    if start is None or end is None:
        return False
    current = now.time()
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class LifeEngine:
    """Durable life state stored in the same DuckDB as the rest of GRID."""

    def __init__(
        self,
        db,
        config: Optional[Dict[str, Any]] = None,
        now_fn=None,
        persona: Optional[str] = None,
    ):
        self.db = db
        self.conn = db.conn
        self.cfg = _merge_config(config)
        self.now_fn = now_fn or datetime.now
        self.persona = (persona or "").strip()
        self._ensure_schema()
        self._seed()

    # -- schema and seed -------------------------------------------------

    def _ensure_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_identity (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                voice VARCHAR,
                values_text VARCHAR,
                boundaries_text VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_goals (
                id VARCHAR PRIMARY KEY,
                title VARCHAR,
                description VARCHAR,
                status VARCHAR DEFAULT 'active',
                priority INTEGER DEFAULT 3,
                due_at TIMESTAMP,
                created_by VARCHAR DEFAULT 'user',
                approved BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                last_worked_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_commitments (
                id VARCHAR PRIMARY KEY,
                description VARCHAR,
                due_at TIMESTAMP,
                status VARCHAR DEFAULT 'open',
                source VARCHAR DEFAULT 'user',
                created_at TIMESTAMP,
                last_notified_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_events (
                id VARCHAR PRIMARY KEY,
                kind VARCHAR,
                summary VARCHAR,
                detail VARCHAR,
                goal_id VARCHAR,
                created_at TIMESTAMP,
                delivered BOOLEAN DEFAULT FALSE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_relationships (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                kind VARCHAR,
                trust INTEGER DEFAULT 50,
                notes VARCHAR,
                last_seen TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS life_state (
                state_key VARCHAR PRIMARY KEY,
                value VARCHAR
            )
        """)

    def _seed(self) -> None:
        row = self.conn.execute("SELECT COUNT(*) FROM life_identity").fetchone()
        if not row or row[0] == 0:
            now = self.now_fn()
            self.conn.execute(
                """
                INSERT INTO life_identity
                    (id, name, voice, values_text, boundaries_text, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(self.persona or self.cfg.get("identity_name", "GRID")),
                    str(self.cfg.get("voice", "")),
                    str(self.cfg.get("values", "")),
                    str(self.cfg.get("boundaries", "")),
                    now,
                    now,
                ],
            )
        if self.persona:
            self.conn.execute(
                "UPDATE life_identity SET name = ?, updated_at = ? WHERE id = 1",
                [self.persona, self.now_fn()],
            )
            self.set_state("persona_prompted", "1")
        for key, value in (
            ("paused", "0"),
            ("created_at", self.now_fn().isoformat()),
        ):
            if self.get_state(key) is None:
                self.set_state(key, value)

    # -- state -----------------------------------------------------------

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM life_state WHERE state_key = ?", [key]
        ).fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO life_state (state_key, value) VALUES (?, ?)",
            [key, str(value)],
        )

    def is_paused(self) -> bool:
        return self.get_state("paused", "0") == "1"

    def set_paused(self, paused: bool) -> str:
        current = self.is_paused()
        self.set_state("paused", "1" if paused else "0")
        if paused != current:
            self._event(
                "pause" if paused else "resume",
                "GRID Life paused" if paused else "GRID Life resumed",
            )
        return "GRID Life paused." if paused else "GRID Life resumed."

    # -- identity --------------------------------------------------------

    def identity(self) -> Dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT name, voice, values_text, boundaries_text, created_at, updated_at
            FROM life_identity WHERE id = 1
            """
        ).fetchone()
        if not row:
            return {}
        return {
            "name": row[0],
            "voice": row[1],
            "values": row[2],
            "boundaries": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def identity_text(self) -> str:
        ident = self.identity()
        if not ident:
            return "GRID Life has no identity yet."
        social = (
            f"Moltbook as {self.persona}"
            if self.persona
            else "not configured (use /persona set <name>)"
        )
        return "\n".join(
            [
                "GRID Life identity",
                f"  Name:        {ident.get('name')}",
                f"  Voice:       {ident.get('voice')}",
                f"  Values:      {ident.get('values')}",
                f"  Boundaries:  {ident.get('boundaries')}",
                f"  Social:      {social}",
            ]
        )

    def needs_persona(self) -> bool:
        if self.persona:
            return False
        if self.get_state("persona_prompted", "0") == "1":
            return False
        return (self.identity().get("name") or "GRID") in ("", "GRID")

    def mark_persona_prompted(self) -> None:
        self.set_state("persona_prompted", "1")

    def adopt_persona(self, name: str, record: bool = True) -> str:
        name = (name or "").strip()
        if not name:
            return "Error: persona name is required."
        self.persona = name
        now = self.now_fn()
        self.conn.execute(
            "UPDATE life_identity SET name = ?, updated_at = ? WHERE id = 1",
            [name, now],
        )
        self.set_state("persona_prompted", "1")
        if record:
            self._event("identity", f"Persona adopted: {name}", "", now=now)
        return f"GRID Life is now {name}."

    def clear_persona(self) -> str:
        old = self.persona
        self.persona = ""
        now = self.now_fn()
        self.conn.execute(
            "UPDATE life_identity SET name = 'GRID', updated_at = ? WHERE id = 1",
            [now],
        )
        self.set_state("persona_prompted", "0")
        self._event(
            "identity",
            f"Persona cleared: {old}" if old else "Persona cleared",
            "",
            now=now,
        )
        return "GRID Life persona cleared. It will ask on the next wake."

    # -- events / iLog ---------------------------------------------------

    def _event(
        self,
        kind: str,
        summary: str,
        detail: str = "",
        goal_id: str = "",
        now: Optional[datetime] = None,
        delivered: bool = False,
    ) -> Dict[str, Any]:
        now = now or self.now_fn()
        event_id = _new_id("e")
        self.conn.execute(
            """
            INSERT INTO life_events
                (id, kind, summary, detail, goal_id, created_at, delivered)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event_id,
                kind,
                str(summary)[:240],
                str(detail)[:4000],
                goal_id or "",
                now,
                bool(delivered),
            ],
        )
        return {
            "id": event_id,
            "kind": kind,
            "summary": summary,
            "detail": detail,
            "created_at": now,
        }

    def record_event(
        self,
        kind: str,
        summary: str,
        detail: str = "",
        goal_id: str = "",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Public event writer for the awake runner and future tray."""
        return self._event(kind, summary, detail, goal_id, now)

    def log_text(self, limit: int = 20) -> str:
        rows = self.conn.execute(
            """
            SELECT created_at, kind, summary, delivered
            FROM life_events ORDER BY created_at DESC LIMIT ?
            """,
            [max(1, int(limit))],
        ).fetchall()
        lines = ["GRID Life - iLog", "-" * 58]
        if not rows:
            lines.append("(empty)")
        for created, kind, summary, delivered in rows:
            mark = "*" if kind == "message" and not delivered else " "
            stamp = created.strftime("%Y-%m-%d %H:%M") if created else "?"
            lines.append(f"{mark} {stamp}  {str(kind):9}  {summary}")
        return "\n".join(lines)

    # -- goals -----------------------------------------------------------

    def add_goal(
        self,
        title: str,
        description: str = "",
        priority: int = 3,
        due_at: Optional[datetime] = None,
        created_by: str = "user",
        approved: bool = True,
        now: Optional[datetime] = None,
    ) -> str:
        title = (title or "").strip()
        if not title:
            return "Error: goal title is required."
        now = now or self.now_fn()
        goal_id = _new_id("g")
        self.conn.execute(
            """
            INSERT INTO life_goals
                (id, title, description, status, priority, due_at,
                 created_by, approved, created_at, updated_at, last_worked_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, NULL)
            """,
            [
                goal_id,
                title[:240],
                (description or "")[:2000],
                int(priority),
                due_at,
                created_by,
                bool(approved),
                now,
                now,
            ],
        )
        self._event("goal_added", f"Goal added: {title}", description, goal_id, now)
        return f"Goal added: {title} ({goal_id})"

    def _find_goal(self, goal_id: str):
        goal_id = (goal_id or "").strip()
        if not goal_id:
            return None
        row = self.conn.execute(
            "SELECT id, title FROM life_goals WHERE id = ?", [goal_id]
        ).fetchone()
        if row:
            return row
        return self.conn.execute(
            "SELECT id, title FROM life_goals WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
            [goal_id + "%"],
        ).fetchone()

    def complete_goal(self, goal_id: str) -> str:
        row = self._find_goal(goal_id)
        if not row:
            return f"Error: goal '{goal_id}' not found."
        now = self.now_fn()
        self.conn.execute(
            "UPDATE life_goals SET status = 'done', updated_at = ? WHERE id = ?",
            [now, row[0]],
        )
        self._event("goal_done", f"Goal completed: {row[1]}", "", row[0], now)
        return f"Goal completed: {row[1]} ({row[0]})"

    def list_goals(self, status: Optional[str] = "active") -> List[Dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                """
                SELECT id, title, description, status, priority, due_at,
                       created_by, approved, created_at, last_worked_at
                FROM life_goals WHERE status = ?
                ORDER BY priority ASC, created_at ASC
                """,
                [status],
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT id, title, description, status, priority, due_at,
                       created_by, approved, created_at, last_worked_at
                FROM life_goals ORDER BY priority ASC, created_at ASC
                """
            ).fetchall()
        keys = [
            "id", "title", "description", "status", "priority", "due_at",
            "created_by", "approved", "created_at", "last_worked_at",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def focus_goal(self) -> Optional[Dict[str, Any]]:
        goals = self.list_goals("active")
        return goals[0] if goals else None

    def record_work(
        self,
        summary: str,
        detail: str = "",
        goal_id: str = "",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now = now or self.now_fn()
        if goal_id:
            self.conn.execute(
                """
                UPDATE life_goals SET last_worked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                [now, now, goal_id],
            )
        return self._event("work", summary, detail, goal_id, now)

    def goals_text(self, status: Optional[str] = "active") -> str:
        goals = self.list_goals(status)
        label = status or "all"
        if not goals:
            return f"No {label} goals."
        lines = [f"GRID Life - {label} goals"]
        for goal in goals:
            marker = "!" if not goal.get("approved") else "-"
            due = f"  due {goal['due_at']:%Y-%m-%d %H:%M}" if goal.get("due_at") else ""
            lines.append(f" {marker} {goal['id']}  {goal['title']}{due}")
        return "\n".join(lines)

    # -- commitments -----------------------------------------------------

    def add_commitment(
        self,
        description: str,
        due_at: Optional[datetime] = None,
        source: str = "user",
        now: Optional[datetime] = None,
    ) -> str:
        description = (description or "").strip()
        if not description:
            return "Error: commitment description is required."
        now = now or self.now_fn()
        commitment_id = _new_id("c")
        self.conn.execute(
            """
            INSERT INTO life_commitments
                (id, description, due_at, status, source, created_at, last_notified_at)
            VALUES (?, ?, ?, 'open', ?, ?, NULL)
            """,
            [commitment_id, description[:1000], due_at, source, now],
        )
        self._event("commitment_added", f"Commitment added: {description}", "", "", now)
        return f"Commitment added: {description} ({commitment_id})"

    def _find_commitment(self, commitment_id: str):
        commitment_id = (commitment_id or "").strip()
        if not commitment_id:
            return None
        row = self.conn.execute(
            "SELECT id, description FROM life_commitments WHERE id = ?",
            [commitment_id],
        ).fetchone()
        if row:
            return row
        return self.conn.execute(
            """
            SELECT id, description FROM life_commitments
            WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1
            """,
            [commitment_id + "%"],
        ).fetchone()

    def complete_commitment(self, commitment_id: str) -> str:
        row = self._find_commitment(commitment_id)
        if not row:
            return f"Error: commitment '{commitment_id}' not found."
        now = self.now_fn()
        self.conn.execute(
            "UPDATE life_commitments SET status = 'done' WHERE id = ?", [row[0]]
        )
        self._event(
            "commitment_done", f"Commitment completed: {row[1]}", "", "", now
        )
        return f"Commitment completed: {row[1]} ({row[0]})"

    def list_commitments(self, status: str = "open") -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, description, due_at, status, source, created_at, last_notified_at
            FROM life_commitments WHERE status = ? ORDER BY created_at ASC
            """,
            [status],
        ).fetchall()
        keys = [
            "id", "description", "due_at", "status", "source",
            "created_at", "last_notified_at",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def commitments_text(self, status: str = "open") -> str:
        items = self.list_commitments(status)
        if not items:
            return f"No {status} commitments."
        lines = [f"GRID Life - {status} commitments"]
        for item in items:
            due = f"  due {item['due_at']:%Y-%m-%d %H:%M}" if item.get("due_at") else ""
            lines.append(f" - {item['id']}  {item['description']}{due}")
        return "\n".join(lines)

    # -- messages --------------------------------------------------------

    def pending_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, summary, detail, created_at
            FROM life_events
            WHERE kind = 'message' AND delivered = FALSE
            ORDER BY created_at ASC LIMIT ?
            """,
            [max(1, int(limit))],
        ).fetchall()
        return [
            {"id": r[0], "summary": r[1], "detail": r[2], "created_at": r[3]}
            for r in rows
        ]

    def mark_delivered(self, event_id: str) -> None:
        self.conn.execute(
            "UPDATE life_events SET delivered = TRUE WHERE id = ?", [event_id]
        )

    # -- heartbeat -------------------------------------------------------

    def _day_range(self, now: datetime):
        start = datetime.combine(now.date(), dtime.min)
        return start, start + timedelta(days=1)

    def _count(self, sql: str, params=()) -> int:
        row = self.conn.execute(sql, list(params)).fetchone()
        return int(row[0]) if row else 0

    def _actions_today(self, now: datetime) -> int:
        start, end = self._day_range(now)
        return self._count(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind IN ('message', 'work', 'reflect')
              AND created_at >= ? AND created_at < ?
            """,
            (start, end),
        )

    def _messages_today(self, now: datetime) -> int:
        start, end = self._day_range(now)
        return self._count(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind = 'message' AND created_at >= ? AND created_at < ?
            """,
            (start, end),
        )

    def _recent_rest(self, summary: str, now: datetime) -> bool:
        row = self.conn.execute(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind = 'rest' AND summary = ? AND created_at >= ?
            """,
            [summary, now - timedelta(hours=6)],
        ).fetchone()
        return bool(row and row[0])

    def _rest(self, now: datetime, reason: str) -> Dict[str, Any]:
        summary = f"Rested: {reason}"
        if not self._recent_rest(summary, now):
            self._event("rest", summary, "", now=now)
        return {
            "action": "rest",
            "summary": summary,
            "detail": "",
            "event_id": None,
            "reason": reason,
        }

    def _due_commitment(self, now: datetime) -> Optional[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, description, due_at, last_notified_at
            FROM life_commitments
            WHERE status = 'open' AND due_at IS NOT NULL AND due_at <= ?
            ORDER BY due_at ASC
            """,
            [now],
        ).fetchall()
        repeat = timedelta(hours=float(self.cfg.get("commitment_repeat_hours", 6)))
        for commitment_id, description, due_at, last_notified in rows:
            if last_notified is None or now - last_notified >= repeat:
                return {
                    "id": commitment_id,
                    "description": description,
                    "due_at": due_at,
                }
        return None

    def _brief_due(self, now: datetime) -> bool:
        brief = _parse_hhmm(self.cfg.get("brief_time", "09:00"))
        if brief is None:
            return False
        target = datetime.combine(now.date(), brief)
        window = timedelta(minutes=int(self.cfg.get("brief_window_minutes", 30)))
        if not (target <= now < target + window):
            return False
        start, end = self._day_range(now)
        count = self._count(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind = 'message' AND summary = 'Daily brief'
              AND created_at >= ? AND created_at < ?
            """,
            (start, end),
        )
        return count == 0

    def _reflection_due(self, now: datetime) -> bool:
        row = self.conn.execute(
            "SELECT MAX(created_at) FROM life_events WHERE kind = 'reflect'"
        ).fetchone()
        last = row[0] if row else None
        if last is None:
            return True
        return now - last >= timedelta(hours=float(self.cfg.get("reflection_hours", 24)))

    def _stale_goal(self, now: datetime) -> Optional[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, title, description, created_at, last_worked_at
            FROM life_goals
            WHERE status = 'active' AND approved = TRUE
            ORDER BY priority ASC, created_at ASC
            """
        ).fetchall()
        stale = timedelta(hours=float(self.cfg.get("goal_stale_hours", 6)))
        for goal_id, title, description, created_at, last_worked in rows:
            last = last_worked or created_at
            if last is None or now - last >= stale:
                return {
                    "id": goal_id,
                    "title": title,
                    "description": description,
                }
        return None

    def _brief_text(self, now: datetime) -> str:
        goals = self.list_goals("active")
        commitments = self.list_commitments("open")
        lines = [
            f"Here is your brief for {now:%A, %d %B %Y}.",
            f"{len(goals)} active goal(s), {len(commitments)} open commitment(s).",
        ]
        for goal in goals[:3]:
            lines.append(f"- Goal: {goal['title']}")
        for item in commitments[:3]:
            lines.append(f"- Commitment: {item['description']}")
        if not goals and not commitments:
            lines.append("Nothing is scheduled. Add a goal with /life goal add <title>.")
        return "\n".join(lines)

    def _reflection_text(self, now: datetime) -> str:
        actions = self._count(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind IN ('message', 'work', 'reflect')
              AND created_at >= ? AND created_at < ?
            """,
            (now - timedelta(hours=24), now),
        )
        messages = self._count(
            """
            SELECT COUNT(*) FROM life_events
            WHERE kind = 'message' AND created_at >= ? AND created_at < ?
            """,
            (now - timedelta(hours=24), now),
        )
        goals = len(self.list_goals("active"))
        commitments = len(self.list_commitments("open"))
        return (
            f"Reflection for {now:%Y-%m-%d}: {actions} action(s) and "
            f"{messages} message(s) in the last 24 hours. "
            f"{goals} active goal(s), {commitments} open commitment(s)."
        )

    def _tick(self, now: datetime, manual: bool = False) -> Dict[str, Any]:
        if not self.cfg.get("enabled", True):
            return self._rest(now, "life disabled")
        if self.is_paused():
            return self._rest(now, "paused")
        if not manual and _in_quiet_hours(now, self.cfg.get("quiet_hours")):
            return self._rest(now, "quiet hours")

        max_actions = int(self.cfg.get("max_actions_per_day", 12))
        max_messages = int(self.cfg.get("max_messages_per_day", 6))
        if not manual and self._actions_today(now) >= max_actions:
            return self._rest(now, "daily action budget reached")

        can_message = self._messages_today(now) < max_messages

        due = self._due_commitment(now)
        if due and can_message:
            text = f"Commitment due: {due['description']}"
            if due.get("due_at"):
                text += f"\nDue: {due['due_at']:%Y-%m-%d %H:%M}"
            event = self._event("message", "Commitment due", text, now=now)
            self.conn.execute(
                "UPDATE life_commitments SET last_notified_at = ? WHERE id = ?",
                [now, due["id"]],
            )
            return {
                "action": "message",
                "summary": "Commitment due",
                "detail": text,
                "event_id": event["id"],
            }

        if can_message and self._brief_due(now):
            text = self._brief_text(now)
            event = self._event("message", "Daily brief", text, now=now)
            return {
                "action": "message",
                "summary": "Daily brief",
                "detail": text,
                "event_id": event["id"],
            }

        if self._reflection_due(now):
            text = self._reflection_text(now)
            event = self._event("reflect", "Reflection", text, now=now)
            return {
                "action": "reflect",
                "summary": "Reflection",
                "detail": text,
                "event_id": event["id"],
            }

        goal = self._stale_goal(now)
        if goal:
            self.conn.execute(
                """
                UPDATE life_goals SET last_worked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                [now, now, goal["id"]],
            )
            next_step = goal.get("description") or "Define the next concrete step."
            text = f"Goal: {goal['title']}\nNext step: {next_step}"
            event = self._event(
                "work", f"Worked on: {goal['title']}", text, goal["id"], now
            )
            return {
                "action": "work",
                "summary": f"Worked on: {goal['title']}",
                "detail": text,
                "event_id": event["id"],
            }

        return self._rest(now, "nothing due")

    def tick(self, now: Optional[datetime] = None, manual: bool = False) -> Dict[str, Any]:
        """Run one heartbeat.

        Scheduled heartbeats call this with manual=False and respect quiet hours
        and budgets. A user-invoked wake calls it with manual=True, so GRID can
        always be woken on demand.
        """
        now = now or self.now_fn()
        result = self._tick(now, manual=manual)
        self.set_state("last_tick", now.isoformat())
        return result

    # -- status ----------------------------------------------------------

    def status_text(self, now: Optional[datetime] = None) -> str:
        now = now or self.now_fn()
        ident = self.identity()
        paused = self.is_paused()
        enabled = bool(self.cfg.get("enabled", True))
        state = "disabled" if not enabled else ("paused" if paused else "awake")

        last_tick_raw = self.get_state("last_tick")
        last_tick = None
        if last_tick_raw:
            try:
                last_tick = datetime.fromisoformat(last_tick_raw)
            except ValueError:
                last_tick = None

        heartbeat = int(self.cfg.get("heartbeat_minutes", 30))
        if last_tick is None:
            next_wake = "on next tick"
        else:
            next_at = last_tick + timedelta(minutes=heartbeat)
            next_wake = "due now" if next_at <= now else next_at.strftime("%H:%M")

        active_goals = len(self.list_goals("active"))
        open_commitments = len(self.list_commitments("open"))
        pending = len(self.pending_messages())
        quiet = self.cfg.get("quiet_hours") or []
        quiet_text = f"{quiet[0]}-{quiet[1]}" if len(quiet) == 2 else "off"

        lines = [
            "GRID Life - status",
            f"  Identity:     {ident.get('name', 'GRID')}",
            f"  State:        {state}",
            f"  Last tick:    {last_tick.strftime('%Y-%m-%d %H:%M') if last_tick else 'never'}",
            f"  Next wake:    {next_wake}",
            f"  Heartbeat:    {heartbeat} min",
            f"  Quiet hours:  {quiet_text}",
            f"  Budget:       {self._actions_today(now)}/{self.cfg.get('max_actions_per_day', 12)} actions, "
            f"{self._messages_today(now)}/{self.cfg.get('max_messages_per_day', 6)} messages today",
            f"  Goals:        {active_goals} active",
            f"  Commitments:  {open_commitments} open",
            f"  Messages:     {pending} pending",
        ]
        return "\n".join(lines)


# -- standalone CLI ------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _print_tick(life: LifeEngine) -> None:
    result = life.tick(manual=True)
    print(result.get("summary", "Tick complete."))
    if result.get("detail"):
        print(result["detail"])
    for message in life.pending_messages():
        print()
        print(message.get("detail") or message.get("summary") or "")
        life.mark_delivered(message["id"])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="GRID Life - local persistent agent loop")
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        help="status, tick, log, goals, goal-add, goal-done, commitments, "
             "commitment-add, commitment-done, pause, resume, identity",
    )
    parser.add_argument("args", nargs="*")
    parsed = parser.parse_args(argv)

    try:
        from grid_db import GridDB
    except ImportError:
        print("Error: duckdb is not installed. Run: pip install duckdb")
        return 1

    db_path = os.environ.get("GRID_DB_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "grid_data.duckdb"
    )
    try:
        db = GridDB(db_path)
    except Exception as exc:
        print(f"Error: cannot open {db_path}: {exc}")
        print("Close GRID first, or use /life inside the running app.")
        return 1

    try:
        life = LifeEngine(db, _load_config().get("life", {}))
        command = parsed.command.lower()
        args = parsed.args

        if command == "status":
            print(life.status_text())
        elif command == "tick":
            _print_tick(life)
        elif command == "log":
            limit = int(args[0]) if args and args[0].isdigit() else 20
            print(life.log_text(limit))
        elif command == "goals":
            print(life.goals_text())
        elif command == "goal-add":
            print(life.add_goal(" ".join(args)))
        elif command == "goal-done":
            print(life.complete_goal(args[0] if args else ""))
        elif command == "commitments":
            print(life.commitments_text())
        elif command == "commitment-add":
            print(life.add_commitment(" ".join(args)))
        elif command == "commitment-done":
            print(life.complete_commitment(args[0] if args else ""))
        elif command == "pause":
            print(life.set_paused(True))
        elif command == "resume":
            print(life.set_paused(False))
        elif command == "identity":
            print(life.identity_text())
        else:
            parser.print_help()
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
