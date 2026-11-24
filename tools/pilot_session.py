#!/usr/bin/env python3
"""Drive a real GRID chat session in a pseudo-terminal.

Run it inside a visible Windows Terminal window to watch the session. It
spawns GRID under ConPTY, waits for the chat prompt, sends a scripted list of
user messages, and writes raw/clean/event logs for later analysis.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from winpty import PtyProcess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOG_DIR = REPO / "logs"

ANSI_RE = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\].*?(?:\x07|\x1b\\))"
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MESSAGES = [
    "Hello. Who are you right now?",
    "What model and backend are you using?",
    "Show me my system info.",
    "What is my local IP address?",
    "Ping 8.8.8.8 and tell me the result.",
    "Do a DNS lookup for example.com.",
    "What is the weather in Kathmandu right now?",
    "Search the web for the latest Ollama release and summarize it in two sentences.",
    "What radio and satellite tools do you have?",
    "Recall something you know about me from your memory.",
    "What have you been doing while I was away?",
    "What is the ISS position right now?",
    "List files.",
    "What OSINT tools do you have?",
    "Summarize this session in three bullets.",
]


def strip_ansi(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


class Pilot:
    def __init__(
        self,
        count: int,
        echo: bool,
        reply_timeout: int,
        start: int = 0,
        messages=None,
    ):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.raw_path = LOG_DIR / f"pilot-{stamp}.raw.log"
        self.clean_path = LOG_DIR / f"pilot-{stamp}.clean.log"
        self.events_path = LOG_DIR / f"pilot-{stamp}.events.jsonl"
        self.raw = self.raw_path.open("w", encoding="utf-8", errors="replace")
        self.clean = self.clean_path.open("w", encoding="utf-8", errors="replace")
        self.events = self.events_path.open("w", encoding="utf-8", buffering=1)
        self.echo = echo
        self.start = start
        self.messages = (
            list(messages) if messages else MESSAGES[start : start + count]
        )
        self.count = len(self.messages)
        self.reply_timeout = reply_timeout
        self.proc = None
        self.buffer = ""
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.last_thinking = 0.0
        self.sent_at = 0.0

    def event(self, kind: str, **data) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "kind": kind,
        }
        record.update(data)
        self.events.write(json.dumps(record, ensure_ascii=False) + "\n")

    def reader(self) -> None:
        while True:
            try:
                chunk = self.proc.read(4096)
            except EOFError:
                break
            except Exception as exc:
                self.event("read_error", error=str(exc))
                break
            if not chunk:
                if not self.proc.isalive():
                    break
                time.sleep(0.02)
                continue
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", "replace")
            self.raw.write(chunk)
            self.raw.flush()
            clean = strip_ansi(chunk)
            self.clean.write(clean)
            self.clean.flush()
            if "GRID thinking" in clean:
                self.last_thinking = time.time()
            with self.lock:
                self.buffer = (self.buffer + clean)[-30000:]
            if self.echo:
                sys.stdout.write(chunk)
                sys.stdout.flush()
        self.done.set()

    def wait_for(self, pattern: str, timeout: int, label: str) -> bool:
        regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                tail = self.buffer[-6000:]
            tail = CONTROL_RE.sub("", tail)
            if regex.search(tail):
                self.event("matched", label=label, pattern=pattern)
                return True
            if self.done.is_set() and not self.proc.isalive():
                break
            time.sleep(0.2)
        with self.lock:
            tail = self.buffer[-1500:]
        self.event("timeout", label=label, pattern=pattern, tail=tail)
        return False

    def send(self, text: str) -> None:
        self.event("send", text=text)
        with self.lock:
            self.buffer = ""
        self.sent_at = time.time()
        self.last_thinking = 0.0
        self.proc.write(text + "\r")

    def wait_for_reply(self, timeout: int, label: str) -> bool:
        deadline = time.time() + timeout
        prompt_re = re.compile(r"You\s*:\s*$", re.IGNORECASE)
        while time.time() < deadline:
            with self.lock:
                tail = self.buffer[-3000:]
            tail = CONTROL_RE.sub("", tail).rstrip()
            prompt = bool(prompt_re.search(tail))
            idle = self.last_thinking == 0 or (time.time() - self.last_thinking) > 3.0
            if prompt and idle and (time.time() - self.sent_at) > 2.0:
                self.event("matched", label=label, mode="reply")
                return True
            if self.done.is_set() and not self.proc.isalive():
                break
            time.sleep(0.25)
        with self.lock:
            tail = self.buffer[-2000:]
        self.event("timeout", label=label, mode="reply", tail=tail)
        return False

    def run(self) -> int:
        self.event("start", count=self.count)
        self.proc = PtyProcess.spawn(
            [sys.executable, str(REPO / "grid_agent.py"), "--no-input", "--no-banner"],
            cwd=str(REPO),
            dimensions=(42, 120),
        )
        thread = threading.Thread(target=self.reader, daemon=True)
        thread.start()

        if not self.wait_for(r"Choice\s*\(\s*1\s*\)|Choice", 240, "main menu"):
            self.event("abort", reason="main menu not found")
            self.stop()
            return 1
        self.send("1")
        if not self.wait_for(r"You\s*:\s*$|You\s*:\s*", 240, "chat prompt"):
            self.event("abort", reason="chat prompt not found")
            self.stop()
            return 1

        for index, message in enumerate(self.messages, self.start + 1):
            self.event("message", index=index, text=message)
            self.send(message)
            if not self.wait_for_reply(
                self.reply_timeout,
                f"reply {index}",
            ):
                self.event("warning", message=f"reply {index} timeout")
                # Send the next message anyway; the app will consume it when ready.
            time.sleep(0.5)

        self.event("exit")
        self.send("/exit")
        deadline = time.time() + 60
        while time.time() < deadline and self.proc.isalive():
            time.sleep(0.3)
        self.event(
            "finished",
            raw_log=str(self.raw_path),
            clean_log=str(self.clean_path),
            events=str(self.events_path),
        )
        self.stop()
        return 0

    def stop(self) -> None:
        try:
            if self.proc and self.proc.isalive():
                self.proc.terminate(force=True)
        except Exception:
            pass
        try:
            self.raw.close()
            self.clean.close()
            self.events.close()
        except Exception:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--message", action="append", default=[])
    parser.add_argument("--reply-timeout", type=int, default=360)
    parser.add_argument("--no-echo", action="store_true")
    args = parser.parse_args(argv)

    print("=" * 78)
    shown = len(args.message) if args.message else args.count
    print(f"GRID PILOT SESSION — {shown} user messages (start {args.start})")
    print("=" * 78)
    pilot = Pilot(
        args.count,
        not args.no_echo,
        args.reply_timeout,
        start=args.start,
        messages=args.message or None,
    )
    try:
        return pilot.run()
    finally:
        if pilot.proc is not None and pilot.proc.isalive():
            pilot.stop()
        print()
        print("=" * 78)
        print("PILOT SESSION COMPLETE")
        print(f"raw:    {pilot.raw_path}")
        print(f"clean:  {pilot.clean_path}")
        print(f"events: {pilot.events_path}")
        print("=" * 78)
        try:
            pilot.events.close()
            pilot.raw.close()
            pilot.clean.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
