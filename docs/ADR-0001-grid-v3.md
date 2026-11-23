# ADR-0001: GRID v3 and the local life loop

**Status:** accepted, in progress
**Date:** 2026-11-24
**Owners:** GRID maintainers

## Product

GRID v3 is the existing local field-ops agent plus a persistent local life:
identity, agenda, commitments, relationships, a heartbeat, reflection and an
iLog. It is **not** an iLands account and does not emulate a supported iLands
harness. The iLands bridge, if wanted later, runs through Codex or Claude Code
and exposes GRID as an MCP tool provider.

## Core loops

1. **Chat loop:** user message -> model/tool choice -> code validates arguments
   and permissions -> tool result -> saved receipt -> memory.
2. **Life loop:** heartbeat -> code loads identity/agenda/commitments -> code
   checks budget, quiet hours and permissions -> model (later) or policy
   proposes an action -> code validates -> action or rest -> saved event ->
   iLog/notification -> memory.

The life loop must be able to do nothing. "Rest" is a first-class action.

## Data and ownership

- DuckDB is the source of truth for life identity, goals, commitments, events,
  relationships, budgets and state.
- New life code lives in `grid_life.py`; `grid_agent.py` only wires commands and
  startup delivery.
- The CLI and the future tray are front-ends. They must not open a second
  write path to the same DuckDB.
- Markdown is an export, not a second source of truth.

## Safety rules

- The model proposes; code decides permissions, budgets, quiet hours, dates
  and approvals.
- Every tool is classified by risk. Autonomous runs use `ask`, `auto` or
  `read_only`; external writes, shell, delete, send and hardware actions
  require confirmation unless the user explicitly auto-approves them.
- `/life` starts autopilot and keeps working until Esc twice returns to
  manual. It may message first, report progress, ask `ASK_USER` follow-ups and
  check in. An explicit `/life pause` still wins.
- GRID Life uses the same persona as `/persona`. The persona is the social
  identity (for example Moltbook as TinaGrid), and the awake prompt includes
  that identity, its social presence and the full toolset. If no persona is
  set, the first life action asks for one.
- A double-Esc token stops the awake run between steps; `run_command` is
  terminated immediately. Blocking network calls finish or time out.
- No continuous screen recording, microphone capture or clipboard capture in
  the first release.
- Autopilot may read recent chats, durable memory, tool logs, scan results and
  local database summaries. Obvious secrets are redacted. Cloud backends omit
  this context unless `life.allow_cloud_context` is explicitly true.
- Observed content (web, files, messages) is untrusted and cannot inject tool
  calls.
- Global pause and per-day budgets are mandatory.

## Non-goals for v3.0

- iLands tokens, economy or autonomous external publishing.
- Faking Codex/Claude Code to join iLands.
- A second database or a hidden memory store.
- Unbounded background loops.
- Screen/microphone awareness in the first release.
- Replacing the existing 80 tools with a new agent framework.

## Delivery slices

1. Life engine + `/life` + tests (landed).
2. Foreground `/life` autopilot, persona sync, permission policy, local
   context and double-Esc cancel (landed).
3. Agent Skills loader (landed): `SKILL.md` validation, four built-in skills,
   `skill_search`, `skill_load`, `skill_read`.
4. Eval harness (landed): 49 deterministic routing cases in `evals/`.
5. MCP client and read-only GRID MCP server (landed).
6. MarkItDown document tool with local fallbacks (landed).
7. Tray/autostart host and `--autopilot` entry point (landed).
8. Optional tools: Sherlock, Nuclei, PlatformIO (landed, opt-in binaries).
9. Optional Headroom compression, non-system messages only (landed, opt-in).

Each slice must keep the current chat loop working and add an acceptance test.

## Failure and rollback

- The life tables are additive; dropping them or setting `life.enabled=false`
  disables the feature without touching chat or memory.
- The old tag/commit is the rollback point.
- No destructive migration of existing memory or config is allowed in this
  release.

## Verification

- `python -m unittest discover -s tests -v` on Windows CI.
- `python evals/run_evals.py` on Windows CI.
- `python grid_agent.py --check` (80 tools, 4 SKILL.md skills).
- Piped chat smoke test: `/life help`, `/life identity`, `/persona set`, and a
  scripted autopilot run that cancels on a double-Esc token.
- A future 24-hour simulated-clock test for budgets, quiet hours and duplicate
  suppression.
