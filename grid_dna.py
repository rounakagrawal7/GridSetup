"""DNA bus: local rooms where GRID, OpenCode and the user can talk.

The bus is deliberately message-only. It never executes GRID tools; the caller
that reads a proposal decides what to do with it.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
DNA_DIR = BASE_DIR / "refs" / "dna"
ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STATUS_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
SENDERS = {"user", "grid", "opencode", "system"}
KINDS = {
    "chat",
    "question",
    "answer",
    "proposal",
    "verification",
    "approval",
    "status",
}
MAX_CONTENT = 64_000
MAX_META = 32_000
MAX_TITLE = 120


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DnaError(ValueError):
    pass


class DnaNotFound(DnaError):
    pass


class DnaStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DNA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── paths ─────────────────────────────────────────────────

    def _room_dir(self, room_id: str) -> Path:
        if not ROOM_RE.fullmatch(str(room_id or "")):
            raise DnaError("invalid room id")
        return self.root / "rooms" / room_id

    def _room_file(self, room_id: str) -> Path:
        return self._room_dir(room_id) / "room.json"

    def _messages_file(self, room_id: str) -> Path:
        return self._room_dir(room_id) / "messages.jsonl"

    # ── room persistence ──────────────────────────────────────

    def _write_room(self, room: Dict[str, Any]) -> None:
        path = self._room_file(room["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(room, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)

    def _read_room(self, room_id: str) -> Dict[str, Any]:
        path = self._room_file(room_id)
        if not path.exists():
            raise DnaNotFound("room not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DnaError(f"cannot read room: {exc}") from exc
        if not isinstance(data, dict):
            raise DnaError("invalid room file")
        return data

    def create_room(self, title: str = "DNA room") -> Dict[str, Any]:
        title = str(title or "DNA room").strip()[:MAX_TITLE] or "DNA room"
        with self._lock:
            for _ in range(8):
                room_id = "dna-" + uuid.uuid4().hex[:12]
                if not self._room_dir(room_id).exists():
                    break
            else:
                raise DnaError("could not allocate a room id")
            now = _now()
            room = {
                "id": room_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "status": "idle",
                "generation": 0,
                "message_count": 0,
                "last_message": "",
            }
            self._room_dir(room_id).mkdir(parents=True, exist_ok=True)
            self._messages_file(room_id).touch()
            self._write_room(room)
            return room

    def list_rooms(self) -> List[Dict[str, Any]]:
        rooms_dir = self.root / "rooms"
        if not rooms_dir.exists():
            return []
        rooms = []
        for path in rooms_dir.glob("*/room.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("id"):
                rooms.append(data)
        rooms.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        return rooms

    # ── messages ──────────────────────────────────────────────

    def _read_messages(
        self,
        room_id: str,
        after: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        path = self._messages_file(room_id)
        if not path.exists():
            return []
        messages = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                try:
                    message_id = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if message_id > after:
                    messages.append(item)
        except OSError:
            return []
        return messages[-limit:]

    def get_room(
        self,
        room_id: str,
        after: int = 0,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        with self._lock:
            room = self._read_room(room_id)
            messages = self._read_messages(room_id, after)
            return room, messages

    def add_message(
        self,
        room_id: str,
        sender: str,
        kind: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sender = str(sender or "").strip().lower()
        kind = str(kind or "").strip().lower()
        if sender not in SENDERS:
            raise DnaError(f"sender must be one of {sorted(SENDERS)}")
        if kind not in KINDS:
            raise DnaError(f"kind must be one of {sorted(KINDS)}")
        content = str(content or "").strip()
        if not content:
            raise DnaError("content is required")
        if len(content) > MAX_CONTENT:
            raise DnaError("content is too large")
        meta = meta if isinstance(meta, dict) else {}
        try:
            meta_json = json.dumps(meta, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise DnaError(f"meta must be JSON-serializable: {exc}") from exc
        if len(meta_json) > MAX_META:
            raise DnaError("meta is too large")

        with self._lock:
            room = self._read_room(room_id)
            message_id = int(room.get("message_count") or 0) + 1
            message = {
                "id": message_id,
                "timestamp": _now(),
                "sender": sender,
                "kind": kind,
                "content": content,
                "meta": meta,
            }
            with self._messages_file(room_id).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")
            room["message_count"] = message_id
            room["updated_at"] = message["timestamp"]
            room["last_message"] = content[:160]
            if kind == "proposal":
                room["status"] = "proposed"
            elif kind == "verification":
                room["status"] = "verified" if meta.get("ok") else "failed"
            elif kind == "approval":
                room["status"] = "approved" if meta.get("approved") else "rejected"
            elif kind == "status":
                value = str(meta.get("status") or content).strip()
                if STATUS_RE.fullmatch(value):
                    room["status"] = value
            if isinstance(meta.get("generation"), int):
                room["generation"] = max(0, int(meta["generation"]))
            self._write_room(room)
            return message

    def set_status(
        self,
        room_id: str,
        status: str,
        generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        status = str(status or "").strip().lower()
        if not STATUS_RE.fullmatch(status):
            raise DnaError("invalid status")
        with self._lock:
            room = self._read_room(room_id)
            room["status"] = status
            room["updated_at"] = _now()
            if generation is not None:
                try:
                    room["generation"] = max(0, int(generation))
                except (TypeError, ValueError) as exc:
                    raise DnaError("generation must be an integer") from exc
            self._write_room(room)
            return room
