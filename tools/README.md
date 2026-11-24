# GRID developer tools

These are optional Windows helpers for testing and memory maintenance. They are
not required to run GRID.

| File | Purpose |
|---|---|
| `backfill_profile.py` | Build `grid_persona.md` from previous chats plus a few environment facts. Pauses the resident while it runs. |
| `pilot_session.py` | Drive a real GRID chat inside a ConPTY and write raw/clean/event logs. |
| `run_pilot.ps1` | Visible Windows Terminal launcher for `pilot_session.py`. |
| `boot_watch.py` | One-reboot visible-window and process logger for diagnosing startup popups. |

Install the optional dependencies for the pilot and boot watcher:

```powershell
.\.venv\Scripts\python.exe -m pip install psutil pywinpty
```

Examples:

```powershell
# Rebuild the user profile from previous conversations
.\.venv\Scripts\python.exe tools\backfill_profile.py

# Drive a scripted 15-message chat session (visible)
Start-Process wt.exe -ArgumentList @('powershell','-NoExit','-File', (Resolve-Path .\tools\run_pilot.ps1))

# One-reboot window/process logger
.\.venv\Scripts\python.exe tools\boot_watch.py --duration 300
```

Logs are written under `logs/`, which is gitignored.
