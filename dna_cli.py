#!/usr/bin/env python3
"""Small CLI for the local DNA bus.

Examples:
  python dna_cli.py rooms
  python dna_cli.py create --title "GRID x OpenCode"
  python dna_cli.py send --room dna-abc123 --from opencode --content "hello"
  python dna_cli.py read --room dna-abc123 --after 0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / "run" / "api_token"
CONFIG_FILE = ROOT / "config.json"


def _base_url(override: str = "") -> str:
    if override:
        return override.rstrip("/")
    host = "127.0.0.1"
    port = 8771
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        api = cfg.get("api") or {}
        host = str(api.get("host") or host)
        port = int(api.get("port") or port)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    if host in ("0.0.0.0", "::", "::0"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _token(override: str = "") -> str:
    if override:
        return override.strip()
    if os.environ.get("GRID_API_TOKEN"):
        return os.environ["GRID_API_TOKEN"].strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


def _request(
    method: str,
    path: str,
    base_url: str,
    token: str,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not token:
        raise SystemExit(f"API token not found at {TOKEN_FILE}")
    response = requests.request(
        method,
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=15,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "error": response.text[:500]}
    if response.status_code >= 400 or not payload.get("ok", True):
        raise SystemExit(
            f"DNA request failed ({response.status_code}): "
            f"{payload.get('error', 'unknown error')}"
        )
    return payload


def _print_message(message: Dict[str, Any]) -> None:
    print(
        f"[{message.get('id')}] {message.get('sender')} / "
        f"{message.get('kind')} · {message.get('timestamp')}"
    )
    content = str(message.get("content") or "")
    for line in content.splitlines() or [""]:
        print(f"  {line}")
    meta = message.get("meta") or {}
    if meta:
        print(f"  meta: {json.dumps(meta, ensure_ascii=False)}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="GRID DNA bus CLI")
    parser.add_argument("--base-url", default="", help="override API base URL")
    parser.add_argument("--token", default="", help="override API token")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("rooms", help="list DNA rooms")

    create = sub.add_parser("create", help="create a room")
    create.add_argument("--title", default="GRID x OpenCode")

    read = sub.add_parser("read", help="read room messages")
    read.add_argument("--room", required=True)
    read.add_argument("--after", type=int, default=0)

    send = sub.add_parser("send", help="send a message")
    send.add_argument("--room", required=True)
    send.add_argument(
        "--from",
        dest="sender",
        default="opencode",
        choices=["user", "grid", "opencode", "system"],
    )
    send.add_argument(
        "--kind",
        default="chat",
        choices=[
            "chat",
            "question",
            "answer",
            "proposal",
            "verification",
            "approval",
            "status",
        ],
    )
    send.add_argument("--content", default="", help="message text; stdin if omitted")
    send.add_argument("--meta", default="", help="JSON object")

    ask = sub.add_parser("ask", help="ask GRID to reply into the room")
    ask.add_argument("--room", required=True)
    ask.add_argument("--prompt", default="", help="message text; stdin if omitted")

    status = sub.add_parser("status", help="set room status")
    status.add_argument("--room", required=True)
    status.add_argument("--status", required=True)
    status.add_argument("--generation", type=int, default=None)

    args = parser.parse_args()
    base_url = _base_url(args.base_url)
    token = _token(args.token)

    if args.command == "rooms":
        payload = _request("GET", "/api/v1/dna/rooms", base_url, token)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for room in payload.get("rooms", []):
                print(
                    f"{room.get('id')}  {room.get('status'):<10} "
                    f"gen {room.get('generation')}  "
                    f"{room.get('message_count')} msg  {room.get('title')}"
                )
        return 0

    if args.command == "create":
        payload = _request(
            "POST",
            "/api/v1/dna/rooms",
            base_url,
            token,
            {"title": args.title},
        )
        room = payload["room"]
        print(json.dumps(room, indent=2) if args.json else room["id"])
        return 0

    if args.command == "read":
        payload = _request(
            "GET",
            f"/api/v1/dna/rooms/{args.room}?after={max(0, args.after)}",
            base_url,
            token,
        )
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            room = payload.get("room") or {}
            print(
                f"{room.get('title')} · {room.get('status')} · "
                f"generation {room.get('generation')}"
            )
            print()
            for message in payload.get("messages", []):
                _print_message(message)
        return 0

    if args.command == "send":
        content = args.content
        if not content:
            content = sys.stdin.read()
        meta = {}
        if args.meta:
            try:
                meta = json.loads(args.meta)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"--meta must be JSON: {exc}")
        payload = _request(
            "POST",
            f"/api/v1/dna/rooms/{args.room}/messages",
            base_url,
            token,
            {
                "sender": args.sender,
                "kind": args.kind,
                "content": content,
                "meta": meta if isinstance(meta, dict) else {},
            },
        )
        message = payload["message"]
        print(
            f"sent #{message.get('id')} {message.get('sender')}/"
            f"{message.get('kind')} to {args.room}"
        )
        return 0

    if args.command == "ask":
        prompt = args.prompt
        if not prompt:
            prompt = sys.stdin.read()
        payload = _request(
            "POST",
            f"/api/v1/dna/rooms/{args.room}/ask",
            base_url,
            token,
            {"prompt": prompt},
        )
        print(payload.get("status", "thinking"))
        return 0

    if args.command == "status":
        body: Dict[str, Any] = {"status": args.status}
        if args.generation is not None:
            body["generation"] = args.generation
        payload = _request(
            "POST",
            f"/api/v1/dna/rooms/{args.room}/status",
            base_url,
            token,
            body,
        )
        room = payload["room"]
        print(
            f"{room.get('id')} -> {room.get('status')} "
            f"(generation {room.get('generation')})"
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
