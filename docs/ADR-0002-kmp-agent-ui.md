# ADR-0002: KMP clients use AG-UI 1.0 and LAN pairing

**Status:** accepted 2026-11-25; gates the KMP scaffold
**Date:** 2026-11-25
**Owners:** GRID maintainers

## Context

GRID is adding a Kotlin Multiplatform desktop client and an Android companion.
The desktop is the canonical host; Android is a companion with an encrypted
cache and an offline command queue. Both need streaming chat, live tool
activity, approvals, report/artifact viewing, and reconnects without losing a
thread.

The current resident control surface (`grid_resident.py`) exposes `/health`,
`/status`, `/handoff`, `/pause` and `/resume` as one-shot JSON. It has no event
stream, no chat API, no token scopes and no artifact API.

A review of GitHub weekly and monthly trending on 2026-11-25 shows the agent
ecosystem standardizing on three layers:

- **MCP** for tools and context (GRID already has a client and a read-only
  server);
- **SKILL.md / Agent Skills** for capabilities (GRID already loads four);
- **AG-UI** for the agent-to-user event stream (GRID has nothing).

The trending list also surfaced agent control planes and browser tooling that
match GRID's direction: `pingdotgg/t3code` (desktop + phone control of local
agents, MIT), `ChromeDevTools/chrome-devtools-mcp` (Apache-2.0, browser
inspection), `vercel-labs/agent-browser` (Apache-2.0, local browser automation),
and `cloudflare/security-audit-skill` (MIT, machine-readable findings).

## Decision

### 1. AG-UI 1.0 is the client protocol

The Python core exposes an AG-UI 1.0 endpoint over HTTP + SSE:

```text
POST /api/v1/agent       RunAgentInput -> SSE stream of AG-UI events
POST /api/v1/agent/resume
GET  /api/v1/threads
GET  /api/v1/threads/<id>
GET  /api/v1/rea/reports
GET  /api/v1/rea/reports/<id>
GET  /api/v1/health
```

Event families we emit first:

- `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`;
- `STEP_STARTED`, `STEP_FINISHED` for planner/tool phases;
- `TEXT_MESSAGE_START/CONTENT/END` for streamed replies;
- `TOOL_CALL_START/ARGS/END/RESULT` for every tool, including REA;
- `ACTIVITY_SNAPSHOT`/`ACTIVITY_DELTA` for REA phases (browser, scroll,
  network, analyze, report);
- `STATE_SNAPSHOT`/`STATE_DELTA` for thread and CLI state;
- `CUSTOM` for GRID-specific artifacts such as `refs/rea/<target>/report.md`.

Approvals use AG-UI's human-in-the-loop interrupt: the run ends with an
interrupt outcome, the desktop/phone answers, and the run resumes with the
decision. This replaces ad-hoc approval strings.

Implementation rules:

- Prefer the official Python `ag-ui-protocol` SDK. If it does not fit the
  existing `process()` loop, emit spec-compliant dictionaries from a thin
  adapter and validate them against the AG-UI 1.0 JSON Schema.
- The transport is SSE first. WebSocket is a later addition, not a rewrite.
- The endpoint binds to loopback by default. LAN exposure is a separate,
  explicit setting.

### 2. Kotlin uses the AG-UI client SDK

The shared KMP module depends on `com.agui:kotlin-client` (MIT, KMP, API 26+,
JVM/Android/iOS/macOS) and wraps it behind a GRID-owned `AgentClient`
interface:

```kotlin
interface AgentClient {
    fun run(input: RunInput): Flow<AgentEvent>
    fun resume(threadId: String, decision: Approval): Flow<AgentEvent>
    fun stop(threadId: String)
}
```

The wrapper is mandatory. The Kotlin SDK is community-maintained and still
0.2.x; if it lags, we can implement the sealed event model and Ktor SSE without
changing the UI layer. Contract fixtures generated from the Python side are
replayed in Kotlin tests.

### 3. Pairing and access follow the T3 Code model, not a cloud relay

`pingdotgg/t3code` validates the desktop-host + phone-companion architecture.
We adopt the concepts, not the code (its stack is TypeScript/Rust and its
branding is trademarked):

- one-time pairing link/QR with a short code and a 10-minute expiry;
- each device gets its own revocable session, not a shared password;
- tokens are scoped: `chat`, `read`, `approve`, `files`, `terminal`, `rea`;
- an idle device session expires (proposed: 30 days);
- routes are tried in order: loopback, LAN, then an optional private overlay
  such as Tailscale; no GRID-operated relay;
- Android stores the device token in the Android Keystore; cleartext LAN HTTP
  is allowed only with an explicit warning, otherwise TLS with a user-installed
  CA;
- the desktop shows connected devices and can revoke them;
- read-only devices can watch a thread and reports but cannot approve or run
  dangerous tools.

Permission modes map to the existing policy:

| GRID mode | Client label | Behavior |
|---|---|---|
| `read_only` | Watch | read tools only |
| `ask` | Supervised | every dangerous/external action waits for approval |
| `auto` | Auto | local writes and external reads run; dangerous tools still ask |
| explicit allow | Full access | only for a trusted device, still audited |

### 4. Reports become machine-readable artifacts

Borrow the verification pattern from `cloudflare/security-audit-skill` (MIT):

- add `findings.json` beside `report.md`, with `confirmed`,
  `needs_validation` and `rejected` records;
- each record carries `id`, `title`, `category`, `severity`, `confidence`,
  and `evidence` paths into the existing artifacts (`screenshot.png`,
  `network.json`, `page.html`, `rea.json`);
- add `coverage-ledger.json` recording what was checked and what was not, so
  "not found" is never confused with "not checked";
- the desktop renders findings as cards, not just Markdown.

### 5. Optional browser tooling stays optional

`chrome-devtools-mcp` and `agent-browser` are useful but not part of the KMP
foundation:

- Chrome DevTools MCP can be added through the existing `mcp_servers` config
  for performance traces and deep network/console inspection. Start it with
  `--no-usage-statistics --no-performance-crux` to preserve local-first
  behavior.
- agent-browser is a candidate interactive fallback for logged-in browsing and
  scroll-heavy pages. Do not add a second browser stack until the desktop
  client works with REA.

## Consequences

- No custom event schema to maintain; future clients can reuse AG-UI.
- The live timeline from the JARVIS/REA video becomes standard event rendering
  instead of bespoke strings.
- Approval and resume become first-class, which Android needs.
- New dependency risk: `ag-ui-protocol` and `com.agui:kotlin-client` 0.2.x.
  Mitigated by the adapter and contract fixtures.
- Pairing, token scopes and revocation must exist before Android ships.
- We must keep the AG-UI endpoint off the public internet.

## Rejected alternatives

- **Custom SSE/JSON**: reinvents a standardized protocol and has no client
  ecosystem.
- **WebSocket-only**: SSE is simpler for one-way streams; WebSocket can be
  added later for voice/interactive tools.
- **Fork or embed T3 Code**: wrong stack, large surface, trademark restrictions.
- **Cloud relay / account service**: violates the local-first requirement.
- **Embedding claude-mem**: its useful ideas are progressive disclosure and
  `<private>` tags; its hosted observer, cloud sync and token are out of scope.
- **Making trend-star count a selection criterion**: several trending repos are
  skills or hype with no security review. Licenses, maintenance and fit decide.

## Delivery slices

1. **Protocol adapter (Python):** `/api/v1/agent` with AG-UI events, bearer
   token, thread registry, REA progress events, contract fixtures.
2. **Shared KMP module:** `AgentClient` wrapper, event models, reconnect and
   replay tests.
3. **Compose Desktop:** chat, live timeline, tool cards, approval modal, REA
   artifact card and report viewer.
4. **Artifacts:** `findings.json` + `coverage-ledger.json` for REA; vault
   endpoints.
5. **Pairing:** one-time code, scoped sessions, device list/revoke, LAN/Tailscale
   route order.
6. **Android companion:** encrypted cache, offline queue, read reports, approve
   or deny, voice notes.
7. **Later:** local TTS readout, native-app teardown (`rea analyze`),
   build-from-blueprint with hidden-browser preview.

## Verification

- Python contract tests validate emitted events against the AG-UI 1.0 schema.
- Kotlin replay tests consume recorded event streams and assert timeline state.
- A desktop smoke test runs a chat turn, a REA teardown, an approval and a
  reconnect.
- Pairing tests cover code expiry, bad token, revoked device and scope denial.
- `--check` and the existing 137 tests stay green.

## Implementation note (2026-11-25)

Landed:

- `--api` AG-UI 1.0 host over HTTP+SSE with bearer auth, thread storage, live
  tool events, approval requests and REA report endpoints;
- shared KMP `GridAgentClient`/`GridEvent` wrapper with an SSE contract test;
- Compose Desktop shell with chat, timeline, tool cards, REA artifacts and
  approvals;
- Android companion with encrypted Keystore token storage, host setup screen,
  chat, tool cards, REA artifact paths and approvals;
- Android-KMP library plugin (`com.android.kotlin.multiplatform.library`) and a
  debug APK build on compileSdk 36;
- desktop model switcher, session token meter and per-reply duration/tokens;
  tool-only runs render one output card; slash-command palette with
  arrow-key selection, cursor-at-end completion, every app/tool command, and
  local `/help`, `/new`, `/clear`, `/model`, `/tokens`, `/rea`, `/tools`,
  `/tool` handling;
- `POST /api/v1/command` dispatches terminal-style host commands from the
  desktop (`/memory`, `/life`, `/plan`, `/ref`, `/jobs`, `/pb`, `/persona`,
  `/social`, `/comms`, `/ctf`, `/game`, `/gcal`, `/gsheet`, `/save`, `/export`).
- Live run activity in the desktop: animated **Thinking…** with elapsed time,
  then a compact `+commands · edits · thoughts · reads · tools` summary for
  tool-using runs; `/exit` saves host memory and closes the window.
- `/shutdown` saves memory, stops the API host via `POST /api/v1/shutdown`,
  suppresses resident auto-restart and closes the desktop.
- Copy buttons on user messages, assistant replies, notes and tool outputs use
  the system clipboard and show a short checkmark confirmation.
- Desktop first-run setup and provider switching: `GET/POST /api/v1/provider`
  plus `POST /api/v1/provider/models`, with Ollama, LM Studio, OpenRouter and
  OpenAI. The desktop can write `config.json` and start the local host.
- Thread replay: `/api/v1/agent` appends each turn to the thread store, and the
  desktop sidebar lists persisted threads and reloads their messages and tool
  cards. Clicking history during a run stops the run first; the composer also
  has a Stop button. `POST /api/v1/threads/clear` clears saved threads only.
- Server-driven UI: `grid_ui.py` defines a locked catalog and macros; the API
  emits `CUSTOM grid.ui` for tool results and REA findings; Compose renders the
  tree natively with text fallback. `/api/v1/ui/catalog` and `/ui/action`
  expose the catalog and action channel.

Still open:

- `findings.json` and `coverage-ledger.json` for REA;
- pairing codes, scoped device sessions and revocation (manual token entry is
  the current bootstrap);
- desktop thread replay from `/api/v1/threads`;
- local TTS, native-app teardown and build-from-blueprint.

## References

- AG-UI protocol and SDKs: https://github.com/ag-ui-protocol/ag-ui
- AG-UI Kotlin SDK: https://github.com/ag-ui-protocol/ag-ui/tree/main/sdks/community/kotlin
- T3 Code remote access: https://github.com/pingdotgg/t3code/blob/main/docs/user/remote-access.md
- T3 Code permission modes: https://github.com/pingdotgg/t3code/blob/main/docs/user/permission-modes.md
- Cloudflare security-audit skill: https://github.com/cloudflare/security-audit-skill
- Chrome DevTools MCP: https://github.com/ChromeDevTools/chrome-devtools-mcp
- agent-browser: https://github.com/vercel-labs/agent-browser
