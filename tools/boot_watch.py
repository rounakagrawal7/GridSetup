#!/usr/bin/env python3
"""One-reboot Windows boot watcher.

Runs hidden from the Startup folder for a few minutes, records every visible
window that appears (with its process, command line and parent chain) plus
interesting process starts, then removes its own Startup shortcut.

Usage:
    pythonw tools/boot_watch.py --duration 300 --remove-shortcut "<path>"
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
import traceback
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOG_DIR = REPO / "logs"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EVENT_OBJECT_SHOW = 0x8002
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OBJID_WINDOW = 0
CHILDID_SELF = 0
WM_QUIT = 0x0012

CONSOLE_CLASSES = {
    "ConsoleWindowClass",
    "CASCADIA_HOSTING_WINDOW_CLASS",
    "PseudoConsoleWindow",
    "VirtualConsoleClass",
    "mintty",
}
INTERESTING_NAMES = {
    "pythonw.exe", "python.exe", "ollama.exe", "ollama app.exe", "llama-server.exe",
    "conhost.exe", "openconsole.exe", "windowsterminal.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
    "node.exe", "npx.cmd", "java.exe", "wsl.exe",
    "steam.exe", "epicgameslauncher.exe", "adobe acrobat synchronizer.exe",
    "teams.exe", "chrome.exe", "msedge.exe", "bingwallpaperdaemon.exe",
}

WinEventProc = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.HWND,
    wintypes.LONG,
    wintypes.LONG,
    wintypes.DWORD,
    wintypes.DWORD,
)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HMODULE,
    WinEventProc,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
]
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


def _text(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _safe_cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return ""


def process_info(pid: int) -> dict:
    info = {"pid": pid}
    try:
        proc = psutil.Process(pid)
        info["name"] = proc.name()
        info["exe"] = ""
        try:
            info["exe"] = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        info["cmdline"] = _safe_cmdline(proc)
        info["ppid"] = proc.ppid()
        chain = []
        parent = proc.parent()
        while parent is not None and len(chain) < 5:
            chain.append(
                {
                    "pid": parent.pid,
                    "name": parent.name(),
                    "cmdline": _safe_cmdline(parent),
                }
            )
            parent = parent.parent()
        info["parents"] = chain
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return info


def _console_like(window: dict, proc: dict) -> bool:
    text = " ".join(
        [
            window.get("class", ""),
            window.get("title", ""),
            proc.get("name", ""),
            proc.get("cmdline", ""),
        ]
    ).lower()
    return window.get("class") in CONSOLE_CLASSES or any(
        hint in text
        for hint in ("cmd", "powershell", "ollama", "llama", "conhost", "terminal", "python")
    )


def window_info(hwnd: int) -> dict:
    return {
        "hwnd": hwnd,
        "class": _class(hwnd),
        "title": _text(hwnd),
        "pid": _pid(hwnd),
    }


def enumerate_visible_windows() -> list[int]:
    results = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            results.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return results


def snapshot_processes() -> dict:
    procs = {}
    for proc in psutil.process_iter(
        ["pid", "ppid", "name", "cmdline", "create_time", "exe"]
    ):
        try:
            data = dict(proc.info)
            data["cmdline"] = " ".join(data.get("cmdline") or [])
            procs[data["pid"]] = data
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


class Watcher:
    def __init__(self, duration: int, log_path: Path, remove_shortcut: str = ""):
        self.duration = max(10, int(duration))
        self.log_path = log_path
        self.remove_shortcut = remove_shortcut
        self.started = time.time()
        self.log = log_path.open("a", encoding="utf-8", buffering=1)
        self.events: "queue.Queue" = queue.Queue()
        self.seen_windows: set = set()
        self.hook_thread = None
        self.hook_tid = 0
        self.console_windows = []
        self.interesting_processes = []
        self._callback = None

    def emit(self, kind: str, **payload) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "uptime": round(time.time() - self.started, 3),
            "kind": kind,
        }
        record.update(payload)
        self.log.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- WinEvent hook ---------------------------------------------------

    def _on_event(self, hook, event, hwnd, id_object, id_child, _thread, _ms):
        if not hwnd or id_object != OBJID_WINDOW or id_child != CHILDID_SELF:
            return
        if user32.IsWindowVisible(hwnd):
            self.events.put((int(event), int(hwnd), time.time()))

    def _hook_loop(self, ready: threading.Event) -> None:
        self._callback = WinEventProc(self._on_event)
        hooks = [
            user32.SetWinEventHook(
                EVENT_OBJECT_SHOW,
                EVENT_OBJECT_SHOW,
                None,
                self._callback,
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            ),
            user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                None,
                self._callback,
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            ),
        ]
        self.hook_tid = kernel32.GetCurrentThreadId()
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hook in hooks:
                if hook:
                    user32.UnhookWinEvent(hook)

    def start_hook(self) -> None:
        ready = threading.Event()
        self.hook_thread = threading.Thread(
            target=self._hook_loop, args=(ready,), name="boot-watch-hook", daemon=True
        )
        self.hook_thread.start()
        ready.wait(3)

    def stop_hook(self) -> None:
        if self.hook_tid:
            user32.PostThreadMessageW(self.hook_tid, WM_QUIT, 0, 0)
        if self.hook_thread is not None:
            self.hook_thread.join(timeout=2)

    # -- main ------------------------------------------------------------

    def run(self) -> None:
        boot = datetime.fromtimestamp(psutil.boot_time()).isoformat(timespec="seconds")
        self.emit(
            "start",
            pid=os.getpid(),
            boot_time=boot,
            cwd=os.getcwd(),
            log=str(self.log_path),
            psutil=psutil.__version__,
        )
        startup = Path(
            os.environ.get("APPDATA", "")
        ) / "Microsoft/Windows/Start Menu/Programs/Startup"
        self.emit(
            "startup_folder",
            path=str(startup),
            entries=[
                {"name": p.name, "path": str(p), "size": p.stat().st_size}
                for p in startup.iterdir()
                if p.exists()
            ]
            if startup.exists()
            else [],
        )

        # Start the hook before the potentially slow baseline snapshot so the
        # first windows at login are not missed.
        self.start_hook()
        for hwnd in enumerate_visible_windows():
            window = window_info(hwnd)
            if not window["title"] and window["class"] not in CONSOLE_CLASSES:
                continue
            proc = process_info(window["pid"])
            self.emit(
                "baseline_window",
                window=window,
                process=proc,
                console_like=_console_like(window, proc),
            )
        baseline = snapshot_processes()
        for pid, info in baseline.items():
            name = (info.get("name") or "").lower()
            if name in INTERESTING_NAMES:
                self.emit(
                    "baseline_process",
                    pid=pid,
                    ppid=info.get("ppid"),
                    name=info.get("name"),
                    cmdline=info.get("cmdline", ""),
                )

        known = baseline
        last_snapshot = 0.0
        try:
            while time.time() - self.started < self.duration:
                self._drain_windows()

                now = time.time()
                if now - last_snapshot >= 0.1:
                    last_snapshot = now
                    current = snapshot_processes()
                    for pid, info in current.items():
                        if pid not in known:
                            name = (info.get("name") or "").lower()
                            if name in INTERESTING_NAMES:
                                detail = process_info(pid)
                                entry = {
                                    "pid": pid,
                                    "ppid": info.get("ppid"),
                                    "name": info.get("name"),
                                    "cmdline": info.get("cmdline", ""),
                                    "parents": detail.get("parents", []),
                                }
                                self.interesting_processes.append(entry)
                                self.emit("process_start", **entry)
                    for pid, info in known.items():
                        if pid not in current:
                            name = (info.get("name") or "").lower()
                            if name in INTERESTING_NAMES:
                                self.emit(
                                    "process_exit",
                                    pid=pid,
                                    name=info.get("name"),
                                    cmdline=info.get("cmdline", ""),
                                )
                    known = current

                time.sleep(0.05)
        finally:
            self._drain_windows()
            self.stop_hook()
            self.emit(
                "summary",
                console_windows=self.console_windows,
                interesting_processes=self.interesting_processes,
                total_windows_seen=len(self.seen_windows),
            )
            if self.remove_shortcut:
                try:
                    Path(self.remove_shortcut).unlink(missing_ok=True)
                    self.emit("removed_shortcut", path=self.remove_shortcut)
                except OSError:
                    pass
            self.log.close()

    def _drain_windows(self) -> None:
        while True:
            try:
                _event, hwnd, _when = self.events.get_nowait()
            except queue.Empty:
                return
            if hwnd in self.seen_windows:
                continue
            self.seen_windows.add(hwnd)
            window = window_info(hwnd)
            proc = process_info(window["pid"])
            console = _console_like(window, proc)
            record = {
                "kind": "window_show",
                "window": window,
                "process": proc,
                "console_like": console,
            }
            if console:
                self.console_windows.append(
                    {
                        "class": window["class"],
                        "title": window["title"],
                        "pid": window["pid"],
                        "process": proc.get("name", ""),
                        "cmdline": proc.get("cmdline", ""),
                    }
                )
            self.log.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="milliseconds"),
                "uptime": round(time.time() - self.started, 3),
                **record,
            }, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--log", default="")
    parser.add_argument("--remove-shortcut", default="")
    args = parser.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = (
        Path(args.log)
        if args.log
        else LOG_DIR / f"boot-watch-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    )
    watcher = Watcher(args.duration, log_path, args.remove_shortcut)
    try:
        watcher.run()
    except Exception:
        try:
            watcher.emit("error", traceback=traceback.format_exc())
        except Exception:
            pass
        if args.remove_shortcut:
            try:
                Path(args.remove_shortcut).unlink(missing_ok=True)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
