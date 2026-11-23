"""Foreground awake runner for GRID v3.

The runner gives GRID a goal, lets the normal orchestrator use the 70-tool
registry, shows the steps, and stops on a double Escape press. It is deliberately
foreground: background/tray delivery is the next slice.
"""

from __future__ import annotations

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

        ident = self.life.identity()
        name = ident.get("name") or "GRID"
        persona = getattr(self.life, "persona", "") or ""
        social = (
            f"You are known as {persona} on Moltbook and have a persistent "
            "social history there."
            if persona
            else "You have no Moltbook persona configured."
        )
        prompt = (
            f"You are {name}, the persistent GRID agent awake on the user's "
            "Windows desktop.\n\n"
            f"{self.life.identity_text()}\n\n"
            f"Social presence: {social}\n"
            "You have the full 70-tool GRID registry available. Use a tool when "
            "it helps.\n\n"
            f"Goal:\n{objective}\n\n"
            "The harness will ask the user before sensitive, external, "
            "file-writing, hardware or dangerous actions; do not claim you "
            "performed an action that was blocked. Keep the final answer short "
            "and report what you actually did. If you are blocked, say exactly "
            "what you need."
        )

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
