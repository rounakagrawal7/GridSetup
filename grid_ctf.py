"""
GRID CTF Module — Local Capture-The-Flag sandbox for autonomous play.

Generates isolated, vulnerable challenges on the local machine (SQL injection,
Python jail, base64 file forensics, ROT13 cipher, localhost banner grab). GRID
solves them with its own tools (run_command, run_code, db_query, nc_connect)
with no network egress. Everything lives under ./ctf_range/.

Sub-commands (prefix with the `ctf` tool or use /ctf):
  ctf help                 — reference
  ctf list                 — list challenges + solved status
  ctf start [id]           — spawn a challenge (default: next unsolved)
  ctf status               — show the active challenge description
  ctf hint [id]            — reveal a hint for the active challenge
  ctf submit <flag>        — verify a GRID_CTF{...} flag
  ctf score                — progress + scoreboard file
  ctf reset [id]           — reset one challenge or the whole range
"""

import base64
import glob
import json
import os
import random
import re
import shutil
import socket
import sqlite3
import string
import subprocess
import sys
from datetime import datetime

CTF_DIR = "ctf_range"
CTF_SCORE_FILE = os.path.join(CTF_DIR, "ctf_score.json")
CTF_ACTIVE_FILE = os.path.join(CTF_DIR, "active_challenge.json")


def _ensure_dir():
    os.makedirs(CTF_DIR, exist_ok=True)


def _load_score() -> dict:
    _ensure_dir()
    try:
        with open(CTF_SCORE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _save_score(score: dict):
    _ensure_dir()
    with open(CTF_SCORE_FILE, "w", encoding="utf-8") as f:
        json.dump(score, f, indent=2, ensure_ascii=False)


def _random_flag() -> str:
    chars = string.ascii_letters + string.digits
    return "GRID_CTF{" + "".join(random.choices(chars, k=12)) + "}"


# ═══ challenge generators ═════════════════════════════════════════
# Each returns a status/description string for the operator + GRID.

def ch_sql_injection(ctf_dir: str, flag: str) -> str:
    """Flag sits as admin's password; bypass the login query."""
    db_path = os.path.join(ctf_dir, "ch_sql_injection.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INT, user TEXT, pass TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'admin', ?)", (flag,))
    conn.execute("INSERT INTO users VALUES (2, 'guest', 'welcome123')")
    conn.commit()
    conn.close()
    return (
        f"CHALLENGE: SQLite Login Bypass\n"
        f"Database created at {db_path}\n"
        f"Vulnerable query:   SELECT pass FROM users WHERE user = '{'{input}'}'\n\n"
        f"Objective: bypass the check to leak admin's password (that IS the flag).\n"
        f"Use run_command / run_code / db_query to poke the query or the file."
    )


def ch_python_jail(ctf_dir: str, flag: str) -> str:
    """Flag lives in an env var; the 'jail' simulates a filtered eval."""
    local_var = "GRID_SECRET_FLAG"
    os.environ[local_var] = flag
    ctx_path = os.path.join(ctf_dir, "jail_context.txt")
    with open(ctx_path, "w", encoding="utf-8") as f:
        f.write("A python eval neighbourhood filters banned words such as: os, system, subprocess.\n")
        f.write("Maybe there is an environment variable worth reading?\n")
    return (
        f"CHALLENGE: Python Jail (env-var flag)\n"
        f"Challenge context written to {ctx_path}\n"
        f"An environment variable GRID_SECRET_FLAG has been set on this machine.\n\n"
        f"Objective: read the variable. A banned-word filter is simulated — but you can "
        f"just look it up. Find the GRID_CTF{{...}} value."
    )


def ch_hidden_base64(ctf_dir: str, flag: str) -> str:
    """A base64-encoded text file; the flag hides among prose lines."""
    import base64 as b64
    prose = (
        "Welcome to the envelope. This passage exists to make you work.  "
        "There is a flag hiding inside, quite visible once poured.  "
    )
    payload = (prose + flag + "\n").encode()
    encoded = b64.b64encode(payload).decode()
    target = os.path.join(ctf_dir, "notes.b64")
    with open(target, "w", encoding="utf-8") as f:
        f.write(encoded)
    return (
        f"CHALLENGE: The Hidden Envelope\n"
        f"A base64-encoded file has been placed at {target}\n\n"
        f"Objective: decode the file. Inside the plain text there is one line that "
        f"starts with GRID_CTF{{...}}. Submit that token."
    )


def ch_rot13(ctf_dir: str, flag: str) -> str:
    """Flag encrypted with ROT13; filename discloses the cipher."""
    rot = flag.translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
    ))
    target = os.path.join(ctf_dir, "rot13_hint.enc")
    with open(target, "w", encoding="utf-8") as f:
        f.write(rot + "\n")
    return (
        f"CHALLENGE: ROT13 Cipher\n"
        f"An encrypted flag is at {target}\n"
        f"The filename hints the rotation: ROT13.\n\n"
        f"Objective: decrypt (letters shifted by 13) and submit the GRID_CTF{{...}} value."
    )


def ch_port_banner(ctf_dir: str, flag: str) -> str:
    """A one-shot local TCP service on random high port sends flag as a banner."""
    port = random.randint(30000, 39999)
    script = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "s.bind(('127.0.0.1', %d))\n"
        "s.listen(1)\n"
        "c, _ = s.accept()\n"
        "c.sendall(b'%s\\n')\n"
        "c.close()\n"
    ) % (port, flag)
    script_path = os.path.join(ctf_dir, "port_service.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    subprocess.Popen(
        [sys.executable, script_path],
        cwd=os.path.abspath(ctf_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return (
        f"CHALLENGE: Port Banner Grab\n"
        f"A local TCP service is listening on 127.0.0.1:{port} (spawner: {script_path})\n\n"
        f"Objective: connect to it (or simply read the script) to capture the banner, which "
        f"is the flag. Use nc_connect, nc_banner_grab, or read_file."
    )


CHALLENGES = [
    {"id": "sql_injection", "title": "SQLite Login Bypass", "difficulty": 1, "start": ch_sql_injection},
    {"id": "python_env", "title": "Python Jail (env var)", "difficulty": 1, "start": ch_python_jail},
    {"id": "hidden_base64", "title": "Base64 Hidden Envelope", "difficulty": 1, "start": ch_hidden_base64},
    {"id": "cipher_rot13", "title": "ROT13 Cipher", "difficulty": 1, "start": ch_rot13},
    {"id": "port_banner", "title": "Localhost Banner Grab", "difficulty": 2, "start": ch_port_banner},
]

_HINTS = {
    "sql_injection": "Close the quote and make the WHERE always true, e.g.  ' OR '1'='1  so it returns every row — or query the DB file directly since you own the machine.",
    "python_env": "The flag was just exported. Read it the plain way: look at your process environment, e.g. via a shell one-liner, or python's os.environ.",
    "hidden_base64": "Decode the file with base64. The flag is a separate line starting GRID_CTF{.",
    "cipher_rot13": "ROT13 is a Caesar shift of 13 on A-Z/a-z. Shift it back (or apply twice).",
    "port_banner": "That one just sends the flag the moment you connect. A quick nc to the port, or reading the spawner script, will reveal it.",
}


def _challenge_def(ch_id: str):
    for ch in CHALLENGES:
        if ch["id"] == ch_id:
            return ch
    return None


def _next_unsolved() -> str:
    score = _load_score()
    for ch in CHALLENGES:
        if not score.get(ch["id"]):
            return ch["id"]
    return ""


def _active_save(data: dict):
    _ensure_dir()
    with open(CTF_ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _active_load() -> dict:
    _ensure_dir()
    try:
        with open(CTF_ACTIVE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def ctf_start(ch_id: str = "") -> str:
    ch_id = (ch_id or "").strip().lower()
    if not ch_id:
        ch_id = _next_unsolved()
        if not ch_id:
            return "All local challenges solved. Run 'ctf reset' to replay the range."
    ch = _challenge_def(ch_id)
    if not ch:
        ids = ", ".join(c["id"] for c in CHALLENGES)
        return f"Unknown challenge '{ch_id}'. Try: {ids}"
    score = _load_score()
    if score.get(ch_id):
        return f"'{ch_id}' already solved. Use 'ctf reset {ch_id}' to replay."
    flag = _random_flag()
    try:
        description = ch["start"](CTF_DIR, flag)
    except Exception as e:
        return f"Failed to spawn '{ch_id}': {e}"
    _active_save({"ch_id": ch_id, "flag": flag, "desc": description,
                  "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return (
        f"[CTF] Started: {ch['title']} (difficulty {ch['difficulty']})\n"
        f"Find a GRID_CTF{{...}} token, then: ctf submit <flag>.\n\n" + description
    )


def ctf_status() -> str:
    act = _active_load()
    if not act:
        return "No active challenge. Start one with 'ctf start'."
    ch = _challenge_def(act.get("ch_id"))
    title = ch["title"] if ch else act.get("ch_id")
    return f"Active: {title} (started {act.get('started')})\n\n{act.get('desc')}"


def ctf_hint(ch_id: str = "") -> str:
    ch_id = (ch_id or "").strip().lower()
    if not ch_id:
        act = _active_load()
        ch_id = act.get("ch_id") or ""
    hint = _HINTS.get(ch_id)
    if not hint:
        ch = _challenge_def(ch_id)
        if ch:
            return f"No hint stored for '{ch_id}' yet."
        return "Specify a challenge id (ctf list) or an active challenge."
    return f"Hint for {ch_id}:\n  {hint}"


def ctf_submit(flag: str) -> str:
    flag = (flag or "").strip()
    if not flag:
        return "Usage: ctf submit <flag>"
    if not re.search(r"^GRID_CTF\{[^{}]+\}$", flag):
        return "That does not look like GRID_CTF{...} format."
    act = _active_load()
    if not act:
        return "No active challenge to submit against. Run 'ctf start'."
    if flag == act.get("flag"):
        score = _load_score()
        score[act["ch_id"]] = {"solved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        _save_score(score)
        _active_save({})
        return f"Correct! Challenge '{act['ch_id']}' solved and logged."
    return "Wrong flag. Keep digging."


def ctf_score() -> str:
    score = _load_score()
    solved = [cid for cid in score if cid not in () and score[cid]]
    lines = [f"CTF progress: {len(solved)}/{len(CHALLENGES)}"]
    for ch in CHALLENGES:
        mark = "[x]" if score.get(ch["id"]) else "[ ]"
        lines.append(f"  {mark}  {ch['id']:<18} {ch['title']}")
    board = "\n".join(lines) + "\n"
    try:
        path = os.path.join(CTF_DIR, "ctf_scoreboard.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(board)
        board += f"\nScoreboard written to {path}"
    except OSError:
        pass
    return board


def ctf_reset(ch_id: str = "") -> str:
    ch_id = (ch_id or "").strip().lower()
    if ch_id:
        score = _load_score()
        score.pop(ch_id, None)
        _save_score(score)
        if _active_load().get("ch_id") == ch_id:
            _active_save({})
        for pat in ("ch_sql_injection.db", "jail_context.txt", "hidden.b64", "rot13_hint.enc", "port_service.py"):
            p = os.path.join(CTF_DIR, pat)
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        return f"Challenge '{ch_id}' reset."
    # full reset
    if os.path.exists(CTF_DIR):
        shutil.rmtree(CTF_DIR, ignore_errors=True)
    _ensure_dir()
    _save_score({})
    _active_save({})
    return "CTF range fully reset (artifacts + scores removed)."


def ctf_help() -> str:
    rows = "\n".join(
        f"  {ch['id']:<20} {ch['title']:<26} (difficulty {ch['difficulty']})"
        for ch in CHALLENGES
    )
    return (
        "GRID CTF SANDBOX — local, no network egress. All artifacts under ./ctf_range/\n\n"
        f"Challenges:\n{rows}\n\n"
        "Commands:\n"
        "  ctf start [id]            spawn a challenge (default: next unsolved)\n"
        "  ctf status                show active challenge\n"
        "  ctf hint [id]             get a hint\n"
        "  ctf submit <flag>         verify a GRID_CTF{...} flag\n"
        "  ctf score                 show progress + write scoreboard file\n"
        "  ctf reset [id]            reset one challenge or the whole range\n"
        "  ctf list                  list challenges + solved status\n"
        "  ctf help                  this help"
    )


def ctf_list() -> str:
    score = _load_score()
    lines = ["CTF challenges:"]
    for ch in CHALLENGES:
        mark = "[x]" if score.get(ch["id"]) else "[ ]"
        lines.append(f"  {mark}  {ch['id']:<20} {ch['title']}")
    if not any(score.get(c["id"]) for c in CHALLENGES):
        lines.append("\n  Nothing solved yet. Start with 'ctf start'.")
    return "\n".join(lines)


def ctf_main(input_str: str = "") -> str:
    """GRID CTF dispatcher — each sub-command returns a status string."""
    parts = (input_str or "").strip().split(maxsplit=1)
    cmd = parts[0].lower() if parts else "help"
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("help", "-h", "?"):
        return ctf_help()
    if cmd in ("start", "spawn", "play"):
        return ctf_start(arg)
    if cmd in ("status", "ctx", "show"):
        return ctf_status()
    if cmd in ("hint",):
        return ctf_hint(arg)
    if cmd in ("submit", "flag", "check"):
        return ctf_submit(arg)
    if cmd in ("score", "leaderboard"):
        return ctf_score()
    if cmd in ("reset", "clear"):
        return ctf_reset(arg)
    if cmd == "list":
        return ctf_list()
    return ctf_help()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GRID local CTF engine")
    parser.add_argument("args", nargs="*")
    opts = parser.parse_args()
    print(ctf_main(" ".join(opts.args)))