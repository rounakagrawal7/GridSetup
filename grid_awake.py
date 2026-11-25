"""Foreground awake runner for GRID v3.

The runner gives GRID a goal, lets the normal orchestrator use the 70-tool
registry, shows the steps, and stops on a double Escape press. It is deliberately
foreground: background/tray delivery is the next slice.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from typing import Any, Dict, Optional

from grid_permissions import PermissionPolicy

# Same Matrix palette as grid_agent. Kept local so importing the 600 KB main
# module as a library (which would create a second Tools class) is unnecessary.
M = "#00FF00"
M_DIM = "green"
M_BRIGHT = "#66FF66"

SELF_DIRECT_RE = re.compile(
    r"\b(?:pick|choose|chose|decide|select|set)\b.*"
    r"\b(?:goal|next|yourself|your\s*self|something|anything|one)\b"
    r"|\b(?:your choice|your call|up to you|you decide|you choose|you pick|"
    r"surprise me|go ahead|whatever you want)\b",
    re.IGNORECASE,
)


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
    if backend_type in ("openrouter", "openai") and not cfg.get("allow_cloud_context", False):
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
        "You have the full 81-tool GRID registry available. Use a tool when "
        "it helps. You can search and load procedural skills with "
        "skill_search and skill_load; use skill_read for referenced files. "
        "Configured MCP tools are available through mcp_servers, mcp_tools "
        "and mcp_call.\n\n"
        f"Goal:\n{objective}\n"
        f"{note_block}\n"
        f"{context_block}\n"
        "If you need a decision, missing information, or the user's input, "
        "end your answer with exactly one line:\n"
        "ASK_USER: <one clear question>\n"
        "The harness will ask them and carry the answer into the next cycle. "
        "After tools finish, answer the goal directly in the user's requested "
        "format; do not paste raw tool output. If this is a one-shot task, "
        "finish it in this cycle. The harness will also ask before sensitive, "
        "external, file-writing, hardware or dangerous actions; do not claim "
        "you performed an action that was blocked. Keep the final answer short "
        "and report what you actually did. If you are blocked, say exactly "
        "what you need."
    )


def build_chat_prompt(life, user_text: str, context: str = "", notes=None) -> str:
    """A conversational prompt that deliberately does not expose tools.

    Idle talk should not turn every "how are you" into a tool call. If the
    user asks for real work, the model appends a single GOAL: line and the
    autopilot starts a normal tool-using cycle.
    """
    ident = life.identity()
    name = ident.get("name") or "GRID"
    try:
        goals = life.list_goals("active")
    except Exception:
        goals = []
    if goals:
        goal_block = "Current active goals:\n" + "\n".join(
            f"- {goal.get('title', 'untitled')}" for goal in goals[:5]
        )
    else:
        goal_block = (
            "Current active goals: none. You have not created a goal yet, so do "
            "not claim that you have one."
        )
    note_block = ""
    if notes:
        note_block = "\nRecent follow-ups:\n" + "\n".join(
            f"- {note}" for note in list(notes)[-4:]
        ) + "\n"
    context_block = f"\nWhat you know right now:\n{context}\n" if context else ""
    return (
        f"You are {name}, a persistent agent living on the user's Windows "
        "desktop. You have your own clock, memory, goals and iLog; you are not "
        "a stateless chatbot. You are between work cycles and your human is "
        "talking to you.\n\n"
        f"{life.identity_text()}\n"
        f"{goal_block}\n"
        f"{note_block}{context_block}\n"
        f"The human said: {user_text}\n\n"
        "Reply in your own voice, in 1-4 sentences. This is conversation, not "
        "a work cycle: do not claim to have run tools, and do not dump system "
        "facts unless the human asked for them. Never reveal secrets from the "
        "context. A goal only exists when it appears under Current active "
        "goals. The harness creates goals; a GOAL line is a request to it.\n"
        "If (and only if) the human asked you to do something concrete that "
        "needs work, end with exactly one line:\n"
        "GOAL: <short, specific goal title>\n"
        "Otherwise do not add a GOAL line."
    )


def build_self_goal_prompt(life, context: str = "") -> str:
    """Ask the model to choose one small next action for itself."""
    ident = life.identity()
    name = ident.get("name") or "GRID"
    context_block = f"\nRecent life context:\n{context}\n" if context else ""
    return (
        f"You are {name}, a persistent agent with your own clock and agenda. "
        "You have no active goal right now. Choose ONE small, concrete, safe, "
        "local-first next action that is genuinely useful today and that you "
        "can finish in a few minutes.\n\n"
        f"{life.identity_text()}\n"
        f"{context_block}\n"
        "Do not choose anything destructive, expensive, external, or that "
        "needs the human's permission. Prefer reviewing memory, tidying your "
        "notes, preparing a brief, checking something local, or learning a "
        "skill you will use later.\n"
        "Reply with exactly one line:\n"
        "GOAL: <short goal title>\n"
        "or, if resting is the right choice:\n"
        "REST"
    )


class AwakeRunner:
    def __init__(
        self,
        life,
        orchestrator,
        console,
        permissions: Optional[Dict[str, Any]] = None,
        tools=None,
    ):
        self.life = life
        self.orchestrator = orchestrator
        self.console = console
        self.tools = tools
        self.policy = PermissionPolicy(
            permissions or {},
            approval_callback=self._approve,
        )
        self.token: Optional[CancelToken] = None

    def _tools(self):
        """Resolve the live Tools class, not a duplicate import of __main__."""
        if self.tools is not None:
            return self.tools
        main = sys.modules.get("__main__")
        candidate = getattr(main, "Tools", None)
        if candidate is not None:
            self.tools = candidate
            return candidate
        from grid_agent import Tools

        self.tools = Tools
        return Tools

    def _approve(self, tool_name: str, tool_input: str, risk: str) -> str:
        from rich.markup import escape
        from rich.panel import Panel
        from rich.prompt import Prompt

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

        Tools = self._tools()

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
    """Continuous foreground autopilot. Esc twice returns to manual.

    The loop is deliberately long-lived: an empty agenda, a pause, or the
    optional daily throttle produces rest, never an exit. Only Esc twice
    (or Ctrl+C) stops it.
    """

    def __init__(
        self,
        life,
        orchestrator,
        console,
        permissions=None,
        interval=None,
        tools=None,
    ):
        super().__init__(
            life, orchestrator, console, permissions=permissions, tools=tools
        )
        cfg = getattr(self.life, "cfg", {}) or {}
        self.interval = max(5, int(interval or cfg.get("autopilot_interval_seconds", 20)))
        self.checkin_cycles = max(0, int(cfg.get("autopilot_checkin_cycles", 3)))
        self.idle_interval = max(15, int(cfg.get("autopilot_idle_seconds", 60)))
        self.self_direct = bool(cfg.get("autopilot_self_direct", True))
        self.max_self_goals = max(0, int(cfg.get("max_self_goals_per_day", 24)))
        self.followups: list[str] = []
        self.watcher = None
        self._heartbeat_at = 0.0
        self._budget_notice_at = 0.0
        self._pause_notice_at = 0.0
        self._talked = False
        self.deliver_messages = True
        self._seen_messages = set()
        self.startup_grace_until = 0.0

    # -- user interaction -----------------------------------------------

    def _ask_user(self, question: str, title: str = "GRID asks") -> str:
        from rich.markup import escape
        from rich.panel import Panel
        from rich.prompt import Prompt


        self.console.print(Panel(
            escape(question),
            title=f"[bold {M}]{title}[/]",
            border_style=M,
            padding=(0, 1),
        ))
        try:
            answer = Prompt.ask(
                f"  [{M}]Your reply (Enter lets me choose)[/]",
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
        while time.time() < end and not self._should_stop():
            time.sleep(0.2)

    def _should_stop(self) -> bool:
        return bool(self.token and self.token.is_set())

    def _farewell(self) -> str:
        return "Autopilot stopped. Back to manual."

    def _input_hint(self) -> str:
        return "Press Esc twice to return to manual."

    # -- delivery / heartbeat --------------------------------------------

    def _deliver_pending(self) -> None:
        from rich.markup import escape
        from rich.panel import Panel


        pending = getattr(self.life, "pending_messages", None)
        mark = getattr(self.life, "mark_delivered", None)
        if not callable(pending):
            return
        for message in pending():
            if not self.deliver_messages:
                if message["id"] not in self._seen_messages:
                    self._seen_messages.add(message["id"])
                    self.console.print(Panel(
                        escape(message.get("detail") or message.get("summary") or ""),
                        title=f"[bold {M}]GRID message (waiting for you)[/]",
                        border_style=M,
                        padding=(0, 1),
                    ))
                continue
            self.console.print(Panel(
                escape(message.get("detail") or message.get("summary") or ""),
                title=f"[bold {M}]GRID[/]",
                border_style=M,
                padding=(0, 1),
            ))
            if callable(mark):
                mark(message["id"])

    def _heartbeat(self) -> None:
        """Surface briefs, commitments and reflection during a long run.

        Autopilot does its own goal work, so the heartbeat runs with
        work_goals=False and only handles messages and reflection.
        """
        cfg = getattr(self.life, "cfg", {}) or {}
        try:
            minutes = max(1, int(cfg.get("heartbeat_minutes", 30)))
        except (TypeError, ValueError):
            minutes = 30
        now = time.time()
        if self._heartbeat_at and now - self._heartbeat_at < minutes * 60:
            return
        self._heartbeat_at = now
        tick = getattr(self.life, "tick", None)
        if not callable(tick):
            return
        try:
            result = tick(manual=True, work_goals=False)
        except TypeError:
            try:
                result = tick(manual=True)
            except Exception:
                return
        except Exception:
            return
        if result.get("action") == "reflect":
            from rich.markup import escape
            from rich.panel import Panel


            self.console.print(Panel(
                escape(result.get("detail") or result.get("summary") or ""),
                title=f"[bold {M}]GRID reflection[/]",
                border_style=M_DIM,
                padding=(0, 1),
            ))

    def _rest_if_needed(self) -> bool:
        """Rest through pause/throttle without leaving autopilot."""
        from rich.markup import escape
        from rich.panel import Panel


        paused = getattr(self.life, "is_paused", None)
        if callable(paused) and paused():
            now = time.time()
            if now - self._pause_notice_at > 300:
                self.console.print(Panel(
                    "GRID Life is paused. I will stay here quietly. "
                    "Send /life resume in manual chat when you want me back.",
                    border_style=M,
                    padding=(0, 1),
                ))
                self._pause_notice_at = now
            self._wait(30)
            return True

        can_act = getattr(self.life, "can_act", None)
        if callable(can_act) and not can_act():
            now = time.time()
            if now - self._budget_notice_at > 3600:
                self.console.print(Panel(
                    "The optional daily throttle is reached, so I am resting. "
                    "I am still alive and will continue when it resets. Set "
                    "life.max_actions_per_day to 0 for unlimited.\n"
                    "Press Esc twice to return to manual.",
                    border_style=M,
                    padding=(0, 1),
                ))
                self._budget_notice_at = now
            self._wait(300)
            return True
        return False

    # -- model helpers ---------------------------------------------------

    @staticmethod
    def _extract_goal(reply: str) -> str:
        for line in (reply or "").splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("GOAL:"):
                return stripped[5:].strip()[:180]
        return ""

    @staticmethod
    def _wants_self_direction(text: str) -> bool:
        text = (text or "").strip()
        if re.match(r"^(which|what|who|did|have|has|do|does|why|how)\b", text, re.I):
            return False
        return bool(SELF_DIRECT_RE.search(text))

    def _backend_chat(self, system_prompt: str, user_text: str, temperature: float = 0.7) -> str:
        backend = getattr(self.orchestrator, "backend", None)
        if backend is None or not hasattr(backend, "chat"):
            return ""
        try:
            return backend.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=temperature,
            ) or ""
        except Exception as exc:
            return f"[Conversation error] {exc}"

    def _chat_reply(self, text: str) -> str:
        context = build_local_context(self.orchestrator, self.life)
        prompt = build_chat_prompt(
            self.life, text, context=context, notes=self.followups
        )
        reply = self._backend_chat(prompt, text, temperature=0.7)
        memory = getattr(self.orchestrator, "memory", None)
        add_turn = getattr(memory, "add_turn", None)
        if callable(add_turn) and reply and not reply.startswith("[Conversation error]"):
            try:
                add_turn(text, reply)
            except Exception:
                pass
        return reply

    # -- work ------------------------------------------------------------

    def _work_once(self, goal: Dict[str, Any]) -> str:
        from rich.markup import escape
        from rich.panel import Panel


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
                escape(display),
                title=f"[bold {M}]GRID[/]",
                border_style=M,
                padding=(0, 1),
            ))
        if question and not self._should_stop():
            event = self.life.record_event(
                "message", "Follow-up question", question, goal.get("id", "")
            )
            self.life.mark_delivered(event["id"])
            answer = self._ask_user(question)
            if answer:
                self.followups.append(answer)
        if self._should_stop():
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

    # -- idle / self-direction -------------------------------------------

    def _self_direct(self) -> bool:
        if not self.self_direct or self.max_self_goals <= 0:
            return False
        counter = getattr(self.life, "self_goals_today", None)
        count = 0
        if callable(counter):
            try:
                count = int(counter())
            except Exception:
                count = 0
        if count >= self.max_self_goals:
            return False
        return self._propose_goal()

    def _propose_goal(self, fallback: bool = False) -> bool:
        from rich.markup import escape
        from rich.panel import Panel


        context = build_local_context(self.orchestrator, self.life)
        prompt = build_self_goal_prompt(self.life, context=context)
        self.console.print(f"  [{M_DIM}]Choosing what to do...[/]")
        reply = self._backend_chat(
            prompt, "What is your next small goal?", temperature=0.8
        )
        title = self._extract_goal(reply)
        if not title:
            if not fallback:
                return False
            title = "Review recent memory and summarize what matters"
        add = getattr(self.life, "add_goal", None)
        if not callable(add):
            return False
        try:
            add(title, priority=2, goal_type="once", created_by="self")
        except TypeError:
            add(title, priority=2, goal_type="once")
        self.console.print(Panel(
            f"I gave myself a goal: {escape(title)}",
            title=f"[bold {M}]GRID[/]",
            border_style=M,
            padding=(0, 1),
        ))
        return True

    def _idle(self) -> None:
        from rich.markup import escape
        from rich.panel import Panel


        question = (
            "Anything else on your mind, or should I pick my next goal?"
            if self._talked
            else "I'm awake with no active goals. What should I work on next?"
        )
        record = getattr(self.life, "record_event", None)
        if callable(record) and self.deliver_messages:
            event = record("message", "Autopilot idle", question)
            mark = getattr(self.life, "mark_delivered", None)
            if event and callable(mark):
                mark(event.get("id"))
        answer = self._ask_user(question, title="GRID is awake")
        if self._should_stop():
            return
        if not answer:
            self._talked = False
            if self.startup_grace_until and time.time() < self.startup_grace_until:
                remaining = max(1, int(self.startup_grace_until - time.time()))
                self.console.print(
                    f"  [{M_DIM}]Startup grace: waiting {remaining}s before "
                    "choosing a goal.[/]"
                )
                self._wait(remaining)
                self.startup_grace_until = 0.0
                return
            if self._self_direct():
                return
            self._wait(self.idle_interval)
            return

        # "pick your next goal", "you choose", "surprise me" and similar
        # phrases should commit a real goal instead of producing more prose.
        if self._wants_self_direction(answer):
            self._talked = False
            if self._propose_goal(fallback=True):
                return

        self.console.print(f"  [{M_DIM}]Thinking...[/]")
        reply = self._chat_reply(answer)
        if self._should_stop():
            return
        goal_title = self._extract_goal(reply)
        display = reply.split("GOAL:")[0].strip() if goal_title else reply.strip()
        if display:
            self.console.print(Panel(
                escape(display),
                title=f"[bold {M}]GRID[/]",
                border_style=M,
                padding=(0, 1),
            ))
        if callable(record):
            record("conversation", "Conversation", f"You: {answer}\nGRID: {reply}")
        if goal_title:
            self._talked = False
            add = getattr(self.life, "add_goal", None)
            if callable(add):
                add(goal_title, priority=1, goal_type="once")
                self.console.print(Panel(
                    f"New goal: {escape(goal_title)}\nStarting work.",
                    border_style=M,
                    padding=(0, 1),
                ))
        else:
            self._talked = True
            if not reply.strip():
                self._wait(self.idle_interval)

    # -- lifecycle -------------------------------------------------------

    def _start(self) -> bool:
        Tools = self._tools()

        self.token = CancelToken()
        self.watcher = DoubleEscapeWatcher(self.token)
        Tools.cancel_token = self.token
        Tools.policy = self.policy
        return bool(self.watcher.start())

    def _stop(self) -> None:
        Tools = self._tools()

        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None
        Tools.cancel_token = None
        Tools.policy = None

    def _loop(self) -> None:
        from rich.markup import escape
        from rich.panel import Panel


        cycles = 0
        while not self._should_stop():
            self._deliver_pending()
            self._heartbeat()
            if self._rest_if_needed():
                continue

            goals = self.life.list_goals("active")
            if not goals:
                self._idle()
                continue

            goal = goals[cycles % len(goals)]
            cycles += 1
            self.console.print(Panel(
                f"[bold {M}]Cycle {cycles}[/]\n{escape(goal['title'])}",
                border_style=M,
                padding=(0, 1),
            ))
            response = self._work_once(goal)
            if self._should_stop():
                break

            failed = response.startswith("[Autopilot error]") or response.startswith("[Blocked]")
            if failed:
                self.life.pause_goal(goal["id"], response[:500])
                self.console.print(Panel(
                    "Goal paused. I'm staying awake; tell me what to change.",
                    border_style=M,
                    padding=(0, 1),
                ))
                self._wait(self.interval)
                continue

            if goal.get("goal_type", "once") == "once":
                self.life.complete_goal(goal["id"])
                self.console.print(Panel(
                    f"Goal complete: {escape(goal['title'])}\nI'm staying awake.",
                    border_style=M,
                    padding=(0, 1),
                ))
                self.console.print(
                    f"  [{M_DIM}]Resting {self.interval}s before the next goal...[/]"
                )
                self._wait(self.interval)
                continue

            if self.checkin_cycles and cycles % self.checkin_cycles == 0:
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
                if self._should_stop():
                    break

            self.console.print(f"  [{M_DIM}]Resting {self.interval}s...[/]")
            self._wait(self.interval)

    def run(self, focus: Optional[str] = None) -> str:
        from rich.markup import escape
        from rich.panel import Panel


        if focus:
            self.life.add_goal(focus.strip(), priority=1, goal_type="once")
        goals = self.life.list_goals("active")

        ident = self.life.identity()
        name = ident.get("name", "GRID")
        if goals:
            greeting = (
                f"I'm awake as {name}. I'll start with '{goals[0]['title']}'.\n"
                "I'll work, report progress and ask when I need you.\n"
                f"{self._input_hint()}"
            )
        else:
            greeting = (
                f"I'm awake as {name}. I have no active goals; "
                "I'll choose what to do.\n"
                f"{self._input_hint()}"
            )
        record = getattr(self.life, "record_event", None)
        if callable(record):
            event = record(
                "message",
                "Autopilot started",
                greeting,
                goals[0].get("id", "") if goals else "",
            )
            mark = getattr(self.life, "mark_delivered", None)
            if event and callable(mark):
                mark(event.get("id"))
        self.console.print(Panel(
            f"[bold {M}]GRID autopilot[/]\n{escape(greeting)}",
            border_style=M,
            padding=(0, 1),
        ))
        if not self._start():
            self.console.print(
                f"  [{M_DIM}]Esc watcher unavailable; Ctrl+C still stops the run.[/]"
            )

        try:
            self._loop()
        except KeyboardInterrupt:
            if self.token:
                self.token.cancel()
        finally:
            self._stop()

        self.console.print(Panel(
            self._farewell(),
            border_style=M,
            padding=(0, 1),
        ))
        return "Autopilot stopped."


class ResidentAutopilot(AutopilotRunner):
    """Headless autopilot for the always-on resident process.

    It never prompts, never installs a keyboard hook, logs to the resident
    log, sleeps through quiet hours, and exits when the handoff event fires
    so the interactive app can take the database.
    """

    def __init__(
        self,
        life,
        orchestrator,
        console,
        permissions=None,
        stop_event=None,
        log=None,
        tools=None,
    ):
        super().__init__(
            life,
            orchestrator,
            console,
            permissions=permissions,
            tools=tools,
        )
        cfg = getattr(self.life, "cfg", {}) or {}
        self.interval = max(30, int(cfg.get("resident_interval_seconds", 300)))
        self.idle_interval = max(60, int(cfg.get("resident_idle_seconds", 900)))
        self.checkin_cycles = 0
        self.self_direct = bool(cfg.get("autopilot_self_direct", True))
        self.stop_event = stop_event or threading.Event()
        self.log = log
        self.quiet_hours = bool(cfg.get("resident_quiet_hours", True))
        self._logged_quiet = False
        self.deliver_messages = False
        try:
            grace = max(0, int(cfg.get("resident_startup_grace_seconds", 120)))
        except (TypeError, ValueError):
            grace = 120
        self.startup_grace_until = time.time() + grace if grace else 0.0

    def _log(self, text: str) -> None:
        if self.log:
            try:
                self.log(text)
            except Exception:
                pass

    def _ask_user(self, question: str, title: str = "GRID asks") -> str:
        self._log(f"[ask] {question}")
        return ""

    def _approve(self, tool_name: str, tool_input: str, risk: str) -> str:
        self._log(f"[denied] {tool_name} ({risk}): {tool_input[:300]}")
        return "n"

    def _start(self) -> bool:
        Tools = self._tools()

        self.token = CancelToken()
        Tools.cancel_token = self.token
        Tools.policy = self.policy

        def _watch() -> None:
            while not self.token.is_set():
                if self.stop_event.wait(0.5):
                    self.token.cancel()
                    return

        threading.Thread(
            target=_watch,
            name="grid-resident-handoff",
            daemon=True,
        ).start()
        return True

    def _stop(self) -> None:
        Tools = self._tools()

        Tools.cancel_token = None
        Tools.policy = None
        memory = getattr(self.orchestrator, "memory", None)
        save = getattr(memory, "save", None)
        if callable(save):
            try:
                save()
            except Exception:
                pass

    def _should_stop(self) -> bool:
        return (
            bool(self.token and self.token.is_set())
            or self.stop_event.is_set()
        )

    def _wait(self, seconds: int) -> None:
        end = time.time() + max(1, seconds)
        while time.time() < end and not self._should_stop():
            time.sleep(0.5)

    def _farewell(self) -> str:
        return "Resident stopped; handing back to the app."

    def _input_hint(self) -> str:
        return "I keep my own clock and rest when there is nothing to do."

    def _rest_if_needed(self) -> bool:
        in_quiet = getattr(self.life, "in_quiet_hours", None)
        if self.quiet_hours and callable(in_quiet) and in_quiet():
            seconds = 300
            until_end = getattr(self.life, "seconds_until_quiet_end", None)
            if callable(until_end):
                try:
                    seconds = max(60, int(until_end()))
                except Exception:
                    seconds = 300
            if not self._logged_quiet:
                self._log(f"[sleep] quiet hours: resting {seconds}s")
                try:
                    self.life.record_event("rest", "Resident sleeping (quiet hours)")
                except Exception:
                    pass
                self._logged_quiet = True
            self.console.print(
                f"  Quiet hours: sleeping {max(1, seconds // 60)} min."
            )
            self._wait(seconds)
            return True
        self._logged_quiet = False
        return super()._rest_if_needed()
