"""Optional local context compression for GRID v3.

Headroom is never required. When enabled and installed, it compresses only the
non-system conversation messages; the system prompt and tool schema stay
byte-for-byte intact.
"""

from __future__ import annotations

from typing import Any, Dict, List


def compress_messages(
    messages: List[Dict[str, Any]],
    model: str,
    enabled: bool = False,
) -> List[Dict[str, Any]]:
    if not enabled or not messages:
        return messages
    try:
        from headroom import compress
    except ImportError:
        return messages

    system = [message for message in messages if message.get("role") == "system"]
    rest = [message for message in messages if message.get("role") != "system"]
    if not rest:
        return messages
    try:
        result = compress(rest, model=model)
        compressed = getattr(result, "messages", None) or result
        if not isinstance(compressed, list) or not compressed:
            return messages
        return system + compressed
    except Exception:
        return messages
