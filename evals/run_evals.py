"""Deterministic routing evals for GRID v3.

These run without a model: they verify that natural-language phrases reach the
intended tool before the LLM is involved. Real-model evals come next.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grid_agent import GridOrchestrator  # noqa: E402


def main() -> int:
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    orchestrator = GridOrchestrator.__new__(GridOrchestrator)
    failures = 0
    for case in cases:
        query = case["query"]
        expected_tool = case["tool"]
        expected_input = case.get("input", "")
        result = orchestrator._auto_detect_tool(query, "")
        tool, tool_input = result if result else (None, "")
        ok = tool == expected_tool
        if ok and expected_input:
            ok = expected_input.lower() in (tool_input or "").lower()
        if ok:
            print(f"PASS  {query!r:48} -> {tool}")
        else:
            failures += 1
            print(
                f"FAIL  {query!r:48} -> {tool} {tool_input!r} "
                f"(wanted {expected_tool} {expected_input!r})"
            )
    print()
    print(f"{len(cases) - failures}/{len(cases)} routing cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
