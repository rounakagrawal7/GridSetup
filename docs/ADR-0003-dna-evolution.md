# ADR-0003: DNA — supervised evolution between GRID and OpenCode

- Status: Accepted — Level 1 bus/room implemented; Level 2 proposals next
- Date: 2026-11-27
- Owners: Rounak, GRID, OpenCode
- Scope: Level 1 (visible room) and Level 2 (skill adoption). Level 3 (core-code evolution) is explicitly out of scope.

## Context

Herdr-style orchestration shows that agents become more useful when they can see each other's state and hand work to each other. GRID already has a local host, threads, tool events, approvals, memory, desktop and Android clients. It does not yet have a governed way for another agent to help it grow.

The goal is not unrestricted self-modification. The goal is a visible collaboration loop with a human selector: GRID observes a gap, asks OpenCode for help, OpenCode proposes a change, tests run, the user approves, and only then does GRID inherit it.

## Vocabulary

- **DNA** — the shared genome/contract: code, prompts, tools, skills, config schema and memory schema. Not user memory contents or secrets.
- **Evolution** — the loop: observe → ask → propose → test → approve → adopt → record.
- **Selector** — the human who approves or rejects a mutation.
- **Editor** — OpenCode, which proposes answers, skills or (later) patches.
- **Learner/operator** — GRID, which detects gaps, tests proposals and adopts approved capabilities.

## Decisions

### 1. Transport: local DNA Bus

A loopback HTTP/JSON bus with a JSONL audit log. v0 clients poll every 1.5 s; SSE is a later enhancement.

- `POST /api/v1/dna/rooms` creates a room.
- `POST /api/v1/dna/rooms/<id>/messages` appends a message.
- `POST /api/v1/dna/rooms/<id>/ask` asks GRID to reply into the room; the host runs it in the background, so leaving the room does not cancel it.
- A user message containing `@opencode` or “OpenCode” wakes a headless `opencode run --agent dna --archived --format json`; the host posts the returned text as `opencode`. The `dna` agent is defined in `.opencode/agents/dna.md` with a no-tools Level 1 prompt. `dna.opencode_model` optionally selects the model; provider errors (e.g. free-limit 429) are surfaced into the room. The bridge is off with `"dna": {"wake": false}` and is limited to one wake per 15 s and 10 per room per hour.
- `POST /api/v1/dna/rooms/<id>/propose` stages a Level 2 package with the `dna-builder` agent; `POST /api/v1/dna/proposals/<id>/approve|reject` decides it.
- `GET /api/v1/dna/rooms` lists rooms.
- `GET /api/v1/dna/rooms/<id>?after=<n>` returns room metadata and new messages.
- `POST /api/v1/dna/rooms/<id>/status` updates status/generation.
- A small `dna_cli.py` lets any agent send/read messages from a shell.
- Messages are persisted under `refs/dna/rooms/<id>/` (`room.json`, `messages.jsonl`).
- The bus cannot invoke GRID tools. It only carries chat, proposals, verification and approval events.

MCP may be added later as an adapter. Headless agent spawning per turn is rejected for v0 because it is slow and stateless.

### 2. Room UI: dedicated DNA workspace

Desktop gets a dedicated DNA workspace, not a normal chat thread.

- Left: live conversation between user, GRID and OpenCode.
- Right (later): evolution timeline with proposals, tests, diffs and approvals.
- Header: status chip, generation badge, token/turn budget and Stop.
- Underlying conversation is persisted as a `dna-*` thread and labeled separately from normal history.
- Android later: notifications plus approve/reject; full room after desktop.

### 3. Skill contract: procedure or tool

Two kinds of proposals:

| Kind | Files | Risk |
|---|---|---|
| `procedure` | `skills/<name>/SKILL.md`, `manifest.json`, `tests/` | instructions only |
| `tool` | the above plus `skills/<name>.py` | executable code |

`manifest.json` must include name, version, kind, description, inputs, outputs, permissions, dependencies, author/session, proposal ID and SHA256 hashes.

`tool` rules for v0:

- `def run(input: str) -> str`
- Python stdlib only
- no network, subprocess, filesystem writes, `eval`/`exec`, `ctypes`, `importlib` or pickle
- deterministic, handles bad input, max 2 s runtime and 64 KB output
- at least one happy-path and one error-path test
- static AST scan plus tests in a temporary copy

Core-code changes are Level 3 and never part of a skill proposal.

### 4. Approval UX: Proposal Review

A dedicated review screen, not the generic approval card:

- summary and rationale
- files/diff
- test results
- permissions/risk
- example input and output
- Approve / Reject / Request changes

Approval events still feed the existing notification/queue system. Android later gets a summary plus Approve/Reject.

### 5. Generation record: genome manifest

Every adoption writes `refs/dna/generations/<n>/genome.json`:

- generation and parent generation
- git commit SHA
- hashes of skills, system prompt, config schema, tool registry count and memory schema
- skill versions/hashes
- proposal ID, approver, timestamp, rationale
- test summary
- rollback pointer

The genome excludes user memory contents, credentials and runtime data.

## Verification contract

After a skill is applied, GRID runs `dna verify` and sends the result to OpenCode:

- expected vs actual paths
- SHA256 per file
- `SKILL.md` parses and name matches the folder
- `manifest.json` is valid
- executable skills import and expose `run()`
- tests pass
- skill appears in `skill_search` and the registry/index
- `git status --porcelain` changes only allowed skill paths

A failed verification rolls back the adoption. Only a passing verification increments the generation.

## Guardrails

- The human selector approves; OpenCode never merges.
- Never edit the live running copy; stage, test, then apply.
- No autonomous merges.
- Budget and turn limits; `/dna stop` kills the loop.
- Audit every message, proposal, test, approval and rollback.
- The DNA bus does not inherit GRID's dangerous tool permissions.
- Separate DNA credentials are planned; v0 uses the local API token.

## Implementation status (v0)

- `grid_dna.py` store, `/api/v1/dna/*` endpoints, `dna_cli.py` and a desktop **DNA Room** workspace are implemented.
- Level 1 conversation works: user/GRID/OpenCode messages, room persistence, polling, a header **⧉** copy-all, and host-side **Ask GRID** that survives leaving the room. GRID asks use a plain-chat prompt (no tools/approvals).
- Wake-on-message works: a user message mentioning `@opencode`/OpenCode runs a headless OpenCode turn and posts the reply; cooldown/budget and `dna.wake` are enforced.
- Level 2 skill adoption works: the `dna-builder` agent writes only under `refs/dna/staging/<proposal-id>/`; GRID validates frontmatter/manifest, static-scans tool code, runs tests, posts a PROPOSAL card, and applies/verifies approved skills under `skills/`. Generation records are written to `refs/dna/generations/<n>/genome.json`.
- `POST /api/v1/dna/rooms/<id>/propose` creates a staged proposal; `POST /api/v1/dna/proposals/<id>/approve|reject` decides it.
- SSE, a separate DNA credential, Android room UI, the richer diff/review panel and Level 3 core evolution are pending.

## MVP acceptance

1. `/dna` opens the workspace and room.
2. User, GRID and OpenCode messages appear live.
3. OpenCode can send a message via `dna_cli.py`.
4. GRID can reply into the room.
5. Room state and transcript persist across restarts.
6. No core files are modified by the room.

Level 2 acceptance:

1. OpenCode builds a package under `refs/dna/staging/` only.
2. GRID validates and tests it; invalid packages are rejected.
3. The user approves or rejects from the proposal card or CLI.
4. Approved skills are applied under `skills/`, verified, and assigned a generation record.
5. No core files are touched; Level 3 remains separate.
