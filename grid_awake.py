"""Foreground awake runner for GRID v3.

The runner gives GRID a goal, lets the normal orchestrator use the 70-tool
registry, shows the steps, and stops on a double Escape press. It is deliberately
foreground: background/tray delivery is the next slice.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, Optional

from grid_permissions import PermissionPolicy


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


class DoubleEscapeWatcher:
    """Best-effort global double-Escape watcher.

    The keyboard hook is global for the duration of an awake run. If the
    keyboard package cannot install a hook, the runner still supports Ctrl+C.
    """

    def __init__(self, token: CancelToken, window: float = 1.2):
        self.token = token
        self.window = float(window)
        self._last = 0.0
        self._hook = None
        self.available = False

    def _on_escape(self, _event=None) -> None:
        now = time.monotonic()
        if self._last and now - self._last <= self.window:
            self.token.cancel()
            self._last = 0.0
        else:
            self._last = now

    def start(self) -> bool:
        try:
            import keyboard

            self._hook = keyboard.on_press_key("esc", self._on_escape, suppress=False)
            self.available = True
        except Exception:
            self.available = False
        return self.available

    def stop(self) -> None:
        if self._hook is None:
            return
        try:
            import keyboard

            keyboard.unhook(self._hook)
        except Exception:
            pass
        self._hook = None


_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*\S+"
)


def _redact(value: Any) -> str:
    return _SECRET_RE.sub(r"\1=[redacted]", str(value))


def build_local_context(orchestrator, life) -> str:
    """Summarize local chats, memory and DB activity for the awake prompt."""
    cfg = getattr(life, "cfg", {}) or {}
    if not cfg.get("include_local_context", True):
        return ""
    backend = getattr(orchestrator, "backend", None)
    backend_type = str(getattr(backend, "type", "") or "").lower()
    if backend_type == "openrouter" and not cfg.get("allow_cloud_context", False):
        return (
            "Local context omitted: the cloud backend is active. "
            "Set life.allow_cloud_context=true to include it."
        )

    parts = []
    memory = getattr(orchestrator, "memory", None)
    history = getattr(memory, "history", None) or []
    if history:
        lines = []
        for turn in history[-8:]:
            role = turn.get("role", "?")
            content = _redact(turn.get("content", "")).replace("\n", " ").strip()
            if content:
                label = "USER" if role == "user" else "GRID"
                lines.append(f"  {label}: {content[:300]}")
        if lines:
            parts.append("Recent conversation:\n" + "\n".join(lines))

    db = getattr(life, "db", None)
    conn = getattr(db, "conn", None)
    if conn is not None:
        def rows(sql):
            try:
                return conn.execute(sql).fetchall()
            except Exception:
                return []

        def scalar(sql):
            try:
                row = conn.execute(sql).fetchone()
                return row[0] if row else None
            except Exception:
                return None

        atoms = rows(
            "SELECT fact FROM memory_atoms ORDER BY created_at DESC LIMIT 5"
        )
        scenarios = rows(
            "SELECT title FROM memory_scenarios ORDER BY created_at DESC LIMIT 3"
        )
        tools = rows(
            "SELECT tool_name, status FROM tool_logs ORDER BY created_at DESC LIMIT 5"
        )
        scans = rows(
            "SELECT target, scan_type FROM scan_results ORDER BY created_at DESC LIMIT 3"
        )
        if atoms:
            parts.append(
                "Durable memory:\n"
                + "\n".join(f"  - {_redact(row[0])[:220]}" for row in atoms)
            )
        if scenarios:
            parts.append(
                "Scenarios:\n"
                + "\n".join(f"  - {_redact(row[0])[:160]}" for row in scenarios)
            )
        if tools:
            parts.append(
                "Recent tools:\n"
                + "\n".join(f"  - {row[0]} ({row[1]})" for row in tools)
            )
        if scans:
            parts.append(
                "Recent scans:\n"
                + "\n".join(f"  - {row[0]} ({row[1]})" for row in scans)
            )

        try:
            goals = life.list_goals("active")
            commitments = life.list_commitments("open")
            if goals:
                parts.append(
                    "Life goals:\n"
                    + "\n".join(f"  - {goal['title']}" for goal in goals[:5])
                )
            if commitments:
                parts.append(
                    "Open commitments:\n"
                    + "\n".join(
                        f"  - {item['description']}" for item in commitments[:5]
                    )
                )
        except Exception:
            pass

        counts = []
        for label, table in (
            ("tool calls", "tool_logs"),
            ("scans", "scan_results"),
            ("memory atoms", "memory_atoms"),
            ("scenarios", "memory_scenarios"),
            ("cache entries", "web_cache"),
        ):
            count = scalar(f"SELECT COUNT(*) FROM {table}")
            if count is not None:
                counts.append(f"{count} {label}")
        if counts:
            parts.append("Local database: " + ", ".join(counts) + ".")
        parts.append(
            "You may inspect more with db_query. Tables: tool_logs, "
            "scan_results, web_cache, sessions, memory_atoms, memory_scenarios, "
            "memory_refs, life_identity, life_goals, life_commitments, "
            "life_events, life_relationships, life_state."
        )
    return "\n\n".join(parts)


def build_awake_prompt(life, objective: str, notes=None, context: str = "") -> str:
    ident = life.identity()
    name = ident.get("name") or "GRID"
    persona = getattr(life, "persona", "") or ""
    social = (
        f"You are known as {persona} on Moltbook and have a persistent "
        "social history there."
        if persona
        else "You have no Moltbook persona configured."
    )
    note_block = ""
    if notes:
        note_block = "\nUser follow-ups:\n" + "\n".join(
            f"- {note}" for note in list(notes)[-5:]
        ) + "\n"
    context_block = ""
    if context:
        context_block = f"\nLocal context:\n{context}\n"
    return (
        f"You are {name}, the persistent GRID agent awake on the user's "
        "Windows desktop.\n\n"
        f"{life.identity_text()}\n\n"
        f"Social presence: {social}\n"
        "You have the full 70-tool GRID registry available. Use a tool when "
        "it helps. You can search and load procedural skills with "
        "skill_search and skill_load; use skill_read for referenced files.\n\n"
        f"Goal:\n{objective}\n"
        f"{note_block}\n"
        f"{context_block}\n"
        "If you need a decision, missing information, or the user's input, "
        "end your answer with exactly one line:\n"
        "ASK_USER: <one clear question>\n"
        "The harness will ask them and carry the answer into the next cycle. "
        "The harness will also ask the user before sensitive, external, "
        "file-writing, hardware or dangerous actions; do not claim you "
        "performed an action that was blocked. Keep the final answer short "
        "and report what you actually did. If you are blocked, say exactly "
        "what you need."
    )


class AwakeRunner:
    def __init__(
        self,
        life,
        orchestrator,
        console,
        permissions: Optional[Dict[str, Any]] = None,
    ):
        self.life = life
        self.orchestrator = orchestrator
        self.console = console
        self.policy = PermissionPolicy(
            permissions or {},
            approval_callback=self._approve,
        )
        self.token: Optional[CancelToken] = None

    def _approve(self, tool_name: str, tool_input: str, risk: str) -> str:
        from rich.markup import escape
        from rich.panel import Panel
        from rich.prompt import Prompt

        from grid_agent import M

        body = (
            f"[bold {M}]GRID wants to run a tool[/]\n"
            f"  Tool:  {escape(tool_name)}\n"
            f"  Risk:  {escape(self.policy.describe(tool_name))}\n"
            f"  Input: {escape(tool_input[:500])}"
        )
        self.console.print(Panel(body, border_style=M, padding=(0, 1)))
        answer = Prompt.ask(
            f"  [{M}]Allow? y = once / a = always this session / n = no[/]",
            default="n",
        )
        return answer.strip().lower()

    def run(self, focus: Optional[str] = None) -> str:
        from rich.markup import escape
        from rich.panel import Panel

        from grid_agent import M, M_DIM, Tools

        goal = None if focus else self.life.focus_goal()
        if not focus and not goal:
            return (
                "No active goals. Add one with /life goal add <title>, "
                "or run /awake <what to do>."
            )

        summary = (focus or goal.get("title") or "awake run").strip()
        goal_id = goal.get("id", "") if goal else ""
        detail = (goal.get("description") or "") if goal else ""
        objective = summary + (f"\n{detail}" if detail else "")

        self.token = CancelToken()
        watcher = DoubleEscapeWatcher(self.token)
        Tools.cancel_token = self.token
        Tools.policy = self.policy

        self.console.print(Panel(
            f"[bold {M}]GRID is awake[/]\n"
            f"Goal: {escape(summary)}\n"
            f"Tools are permissioned. Press [bold]Esc twice[/] to stop.",
            border_style=M,
            padding=(0, 1),
        ))
        if not watcher.start():
            self.console.print(
                f"  [{M_DIM}]Esc watcher unavailable; Ctrl+C still stops the run.[/]"
            )

        context = build_local_context(self.orchestrator, self.life)
        prompt = build_awake_prompt(self.life, objective, context=context)

        step_logs = []
        started = time.time()
        response = ""
        try:
            self.console.print(f"  [{M_DIM}]Thinking...[/]")
            response = self.orchestrator.process(prompt, stream=True, step_logs=step_logs)
        except KeyboardInterrupt:
            self.token.cancel()
            response = "[Cancelled by user]"
        except Exception as exc:
            response = f"[Awake error] {exc}"
        finally:
            watcher.stop()
            Tools.cancel_token = None
            Tools.policy = None

        for step in step_logs:
            self.console.print(step)
        if response:
            self.console.print(Panel(
                response,
                title=f"[bold {M}]GRID[/]",
                border_style=M,
                padding=(0, 1),
            ))

        elapsed = max(0.0, time.time() - started)
        if self.token.is_set():
            self.life.record_event(
                "cancelled",
                f"Cancelled awake run: {summary}",
                response[:2000],
                goal_id,
            )
        else:
            self.life.record_work(
                f"Awake run: {summary}",
                response[:3000],
                goal_id,
            )
        self.console.print(
            f"  [{M_DIM}]Awake run finished in {elapsed:.1f}s.[/]\n"
        )
        return response

class AutopilotRunner(AwakeRunner):
    """Continuous foreground autopilot. Esc twice returns to manual."""

    def __init__(self, life, orchestrator, console, permissions=None, interval=None):
        super().__init__(life, orchestrator, console, permissions=permissions)
        cfg = getattr(self.life, "cfg", {}) or {}
        self.interval = max(5, int(interval or cfg.get("autopilot_interval_seconds", 20)))
        self.checkin_cycles = max(
            1, int(cfg.get("autopilot_checkin_cycles", 3))
        )
        self.followups: list[str] = []

    def _ask_user(self, question: str, title: str = "GRID asks") -> str:
        from rich.markup import escape
        from rich.panel import Panel
        from rich.prompt import Prompt

        from grid_agent import M

        self.console.print(Panel(
            escape(question),
            title=f"[bold {M}]{title}[/]",
            border_style=M,
            padding=(0, 1),
        ))
        try:
            answer = Prompt.ask(
                f"  [{M}]Your reply (Enter to keep going)[/]",
                default="",
            ).strip()
        except (EOFError, KeyboardInterrupt):
            self.token.cancel()
            return ""
        if answer.lower() in ("stop", "pause", "quit", "exit"):
            self.token.cancel()
        return answer

    def _wait(self, seconds: int) -> None:
        end = time.time() + max(1, seconds)
        while time.time() < end and not self.token.is_set():
            time.sleep(0.2)

    def _work_once(self, goal: Dict[str, Any]) -> str:
        from rich.markup import escape
        from rich.panel import Panel

        from grid_agent import M, M_DIM

        objective = goal.get("title") or "Continue the current goal."
        if goal.get("description"):
            objective += "\n" + goal["description"]
        context = build_local_context(self.orchestrator, self.life)
        prompt = build_awake_prompt(
            self.life, objective, notes=self.followups, context=context
        )
        step_logs = []
        self.console.print(f"  [{M_DIM}]Thinking...[/]")
        try:
            response = self.orchestrator.process(prompt, stream=True, step_logs=step_logs)
        except KeyboardInterrupt:
            self.token.cancel()
            response = "[Cancelled by user]"
        except Exception as exc:
            response = f"[Autopilot error] {exc}"

        display = response
        question = ""
        if "ASK_USER:" in response:
            before, after = response.split("ASK_USER:", 1)
            display = before.strip() or response
            question = after.strip().splitlines()[0].strip() if after.strip() else ""

        for step in step_logs:
            self.console.print(step)
        if display:
            self.console.print(Panel(
                display,
                title=f"[bold {M}]GRID[/]",
                border_style=M,
                padding=(0, 1),
            ))
        if question and not self.token.is_set():
            event = self.life.record_event(
                "message", "Follow-up question", question, goal.get("id", "")
            )
            self.life.mark_delivered(event["id"])
            answer = self._ask_user(question)
            if answer:
                self.followups.append(answer)
        if self.token.is_set():
            self.life.record_event(
                "cancelled",
                f"Cancelled autopilot: {escape(objective[:80])}",
                response[:2000],
                goal.get("id", ""),
            )
        else:
            self.life.record_work(
                f"Autopilot: {objective[:120]}",
                response[:3000],
                goal.get("id", ""),
            )
        return response

    def run(self, focus: Optional[str] = None) -> str:
        from rich.markup import escape
        from rich.panel import Panel

        from grid_agent import M, M_DIM, Tools

        if focus:
            self.life.add_goal(focus.strip(), priority=1)
        goals = self.life.list_goals("active")
        if not goals:
            return "No active goals. Run /life <task> to start one."

        self.token = CancelToken()
        watcher = DoubleEscapeWatcher(self.token)
        Tools.cancel_token = self.token
        Tools.policy = self.policy

        ident = self.life.identity()
        name = ident.get("name", "GRID")
        greeting = (
            f"I'm awake as {name}. I'll start with '{goals[0]['title']}'.\n"
            "I'll work, report progress and ask when I need you.\n"
            "Press Esc twice to return to manual."
        )
        event = self.life.record_event(
            "message", "Autopilot started", greeting, goals[0].get("id", "")
        )
        self.life.mark_delivered(event["id"])
        self.console.print(Panel(
            f"[bold {M}]GRID autopilot[/]\n"
            f"{escape(greeting)}",
            border_style=M,
            padding=(0, 1),
        ))
        if not watcher.start():
            self.console.print(
                f"  [{M_DIM}]Esc watcher unavailable; Ctrl+C still stops the run.[/]"
            )

        cycles = 0
        try:
            while not self.token.is_set():
                for message in self.life.pending_messages():
                    self.console.print(Panel(
                        message.get("detail") or message.get("summary") or "",
                        title=f"[bold {M}]GRID[/]",
                        border_style=M,
                        padding=(0, 1),
                    ))
                    self.life.mark_delivered(message["id"])

                if not self.life.can_act():
                    self.console.print(
                        f"  [{M_DIM}]Daily action budget reached. "
                        f"Press Esc twice to return to manual.[/]"
                    )
                    self._wait(30)
                    continue

                goals = self.life.list_goals("active")
                if not goals:
                    self.console.print(
                        f"  [{M_DIM}]No active goals. Press Esc twice to return to manual.[/]"
                    )
                    self._wait(30)
                    continue

                goal = goals[cycles % len(goals)]
                cycles += 1
                self.console.print(Panel(
                    f"[bold {M}]Cycle {cycles}[/]\n{escape(goal['title'])}",
                    border_style=M,
                    padding=(0, 1),
                ))
                self._work_once(goal)
                if self.token.is_set():
                    break

                if cycles % self.checkin_cycles == 0:
                    question = (
                        f"Check-in: I've completed {cycles} cycle(s) on "
                        f"'{goal['title']}'. Anything you want me to change "
                        "or prioritize?"
                    )
                    event = self.life.record_event(
                        "message", "Autopilot check-in", question, goal.get("id", "")
                    )
                    self.life.mark_delivered(event["id"])
                    answer = self._ask_user(question, title="GRID check-in")
                    if answer:
                        self.followups.append(answer)
                    if self.token.is_set():
                        break

                self.console.print(f"  [{M_DIM}]Resting {self.interval}s...[/]")
                self._wait(self.interval)
        except KeyboardInterrupt:
            self.token.cancel()
        finally:
            watcher.stop()
            Tools.cancel_token = None
            Tools.policy = None

        self.console.print(Panel(
            "Autopilot stopped. Back to manual.",
            border_style=M,
            padding=(0, 1),
        ))
        return "Autopilot stopped."
