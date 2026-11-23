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
- A manual `/life wake` or `/life awake` bypasses quiet hours and the daily
  action budget, but never an explicit `/life pause`.
- GRID Life uses the same persona as `/persona`. The persona is the social
  identity (for example Moltbook as TinaGrid), and the awake prompt includes
  that identity, its social presence and the full toolset. If no persona is
  set, the first life action asks for one.
- A double-Esc token stops the awake run between steps; `run_command` is
  terminated immediately. Blocking network calls finish or time out.
- No continuous screen recording, microphone capture or clipboard capture in
  the first release.
- Observed content (web, files, messages) is untrusted and cannot inject tool
  calls.
- Global pause and per-day budgets are mandatory.

## Non-goals for v3.0

- iLands tokens, economy or autonomous external publishing.
- Faking Codex/Claude Code to join iLands.
- A second database or a hidden memory store.
- Unbounded background loops.
- Screen/microphone awareness in the first release.
- Replacing the existing 70 tools with a new agent framework.

## Delivery slices

1. Life engine + `/life` + tests (landed).
2. Foreground `/life awake` runner, permission policy and double-Esc cancel
   (landed).
3. Agent Skills loader.
3. Eval harness.
4. MCP client, then GRID MCP server.
5. MarkItDown document tool.
6. Tray/autostart host and heartbeat.
7. Optional tools: Sherlock, Nuclei, PlatformIO.

Each slice must keep the current chat loop working and add an acceptance test.

## Failure and rollback

- The life tables are additive; dropping them or setting `life.enabled=false`
  disables the feature without touching chat or memory.
- The old tag/commit is the rollback point.
- No destructive migration of existing memory or config is allowed in this
  release.

## Verification

- `python -m unittest discover -s tests -v` on Windows CI.
- `python grid_agent.py --check`.
- Piped chat smoke test: `/life`, `/life goal add`, `/life tick`, `/life log`,
  `/life pause`, `/life resume`.
- A future 24-hour simulated-clock test for budgets, quiet hours and duplicate
  suppression.
