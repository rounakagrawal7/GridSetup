"""Deterministic word and character counts for GRID.

The module exposes one entry point, ``run(input)``, which accepts text and
returns a JSON object of counts. Standard library only; no I/O or network.
"""

import json
import re

# A word starts with a letter or digit, may contain internal apostrophes or
# hyphens, and ends with a letter or digit. Underscores are separators.
_WORD_RE = re.compile(r"[^\W_]+(?:['\u2019-][^\W_]+)*", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)


def _analyze(text):
    words = _WORD_RE.findall(text)
    return {
        "characters": len(text),
        "characters_no_whitespace": len(_WHITESPACE_RE.sub("", text)),
        "lines": len(text.splitlines()),
        "unique_words": len({word.casefold() for word in words}),
        "words": len(words),
    }


def run(input: str) -> str:
    """Return counts for ``input`` as a JSON object string.

    The result has integer fields ``characters``, ``characters_no_whitespace``,
    ``lines``, ``unique_words`` and ``words``. ``unique_words`` compares words
    case-insensitively. An empty string yields all zeros.

    Raises:
        TypeError: if ``input`` is not a string.
    """
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    return json.dumps(_analyze(input), ensure_ascii=False, sort_keys=True)