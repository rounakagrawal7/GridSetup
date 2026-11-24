#!/usr/bin/env python3
"""Build grid_persona.md from previous chats plus a few environment facts.

This only writes the user-profile file; it does not touch DuckDB, so it can
run while the resident is alive. It pauses the resident to free the model.
"""

from __future__ import annotations

import getpass
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from grid_agent import MEMORY_FILE, Memory, Recaller, choose_backend, load_config  # noqa: E402


def seeds() -> list[str]:
    config = load_config()
    offset = datetime.now().astimezone().utcoffset()
    utc = f"UTC{offset}" if offset is not None else "unknown UTC offset"
    model = config.get("model") or "unknown"
    backend = config.get("backend_type") or "unknown"
    persona = (config.get("grid_persona") or "").strip()
    facts = [
        f"Windows account name: {getpass.getuser()}",
        f"System time zone: {utc}",
        f"Building and testing GRID, a local-first autonomous agent, in {REPO}",
        "Wants GRID to run always-on, including after reboot, and to keep "
        "working autonomously",
        "Wants GRID to remember them across chats and use previous conversations",
        "Prefers tabular output for data and results when it fits",
        f"Uses the local {backend} backend with {model}",
    ]
    if persona:
        facts.append(f"Uses the {persona} persona for GRID and Moltbook")
    return facts


def main() -> int:
    memory = Memory(str(REPO / MEMORY_FILE))
    print(f"Loaded {len(memory.history) // 2} previous turn(s).", flush=True)
    backend = choose_backend(non_interactive=True)
    recaller = Recaller(backend, None, memory)

    paused = False
    try:
        import grid_resident

        if grid_resident.is_resident_alive():
            grid_resident.request_pause(True)
            paused = True
            print("Resident paused for the profile build.", flush=True)
    except Exception:
        pass

    try:
        added = recaller.backfill_profile(batch_size=20, progress=print)
        print(f"Backfill added {added} fact(s).", flush=True)
        for seed in seeds():
            print(f"  {recaller.remember(seed)}", flush=True)
        print("\n=== USER PROFILE ===\n", flush=True)
        print(recaller.profile_text(), flush=True)
    finally:
        if paused:
            try:
                import grid_resident

                grid_resident.request_pause(False)
                print("Resident resumed.", flush=True)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
