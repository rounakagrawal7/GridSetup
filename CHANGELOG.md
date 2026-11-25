# Changelog

## v3.2 - authorized reverse-engineering (in progress)

- New `rea` tool: passive teardown of a web target you own or are explicitly
  authorized to test. Captures DOM and screenshot (via REA), network requests,
  API endpoint strings, third-party origins, stack fingerprints, security
  headers, cookies and redacted secret patterns.
- Authorization gate before any request: `rea authorized <url>`, the
  `security.authorized_targets` allowlist (`/rea authorize`, `/rea revoke`,
  `/rea list`), or private/lab hosts. Public targets without authorization are
  refused.
- Optional `rea-agents` backend: use an installed `rea` CLI or
  `security.rea.command`; setting `security.rea.allow_npx` to `true` permits a
  pinned `npx` download. A native BeautifulSoup/requests fallback runs when Node
  or a Chrome-family browser is missing.
- The REA backend scrolls the page before capture (PageDown steps, then back
  to the top) so lazy-loaded bundles and network calls are included.
  `security.rea.scroll_steps` controls the depth (default 4, `0` disables).
- Reports land in `refs/rea/<host>-<timestamp>/`: `report.md`, `manifest.json`,
  `network.json`, `headers.json`, `page.html`, plus `rea.json` and
  `screenshot.png` from the REA backend. Secrets are truncated in the report.
- `rea` is classified dangerous, so it always asks. The registry grows to 81
  tools; 25 new tests cover authorization, parsing, redaction, routing and the
  local teardown path (137 tests total, 51 routing evals).
- New `--api` host: a loopback AG-UI 1.0 endpoint over HTTP+SSE with bearer
  auth, thread storage, live tool/activity events, approval requests and REA
  report endpoints. The API resolves the live `__main__` tools so events and
  request-scoped policies work in the real process (157 tests total).
- First Kotlin Multiplatform client under `clients/`: a shared `GridAgentClient`
  over the AG-UI Kotlin SDK, a Compose Desktop shell with a live tool timeline,
  approval cards and REA artifact cards, and a JVM contract test that replays
  the Python SSE frames.
- Desktop UX pass: tool-only runs show one output card instead of a duplicate
  assistant bubble; assistant replies show elapsed time and token usage; the
  sidebar has a session token meter; the chat has a visible scrollbar; the
  active model is shown and can be switched from the UI.
- API additions: `GET/POST /api/v1/model` and a `CUSTOM grid.stats` event with
  duration, token counts, model and tool-call count.
- Desktop slash-command palette: typing `/` shows a scrollable list of app
  commands, terminal-style commands, and every registered GRID tool with
  descriptions; arrow keys (including numpad) select, Tab completes with the
  cursor at the end, and Enter executes local commands without sending them to
  the LLM.
- `POST /api/v1/command` runs terminal-style commands against the live host, so
  `/memory`, `/life`, `/plan`, `/ref`, `/jobs`, `/pb`, `/persona`, `/social`,
  `/comms`, `/ctf`, `/game`, `/gcal`, `/gsheet`, `/save` and `/export` work
  directly from the desktop composer and render their output in chat.
- Desktop run activity: while the model works, the chat shows an animated
  **Thinking…** row with elapsed time; tool-using runs replace it with a live
  summary of commands, edits, thoughts, reads and tools.
- `/exit` saves host conversation memory (and syncs PocketBase when connected)
  before closing the desktop window.
- `/shutdown` adds a confirmation dialog, then saves, stops the API host and
  suppresses resident auto-restart before closing the desktop.
- Copy icons on every user message, assistant reply, server-command note and
  tool output; clicking copies the full text and briefly shows a checkmark.
  The header is now titled **Command Center**.
- First-run desktop setup: choose Ollama, LM Studio, OpenRouter or OpenAI,
  load models, write `config.json` and start the local host from the desktop.
  The sidebar shows the active provider and opens a **Change provider** dialog;
  its model field is a dropdown that auto-loads the provider's available models.
  `GET/POST /api/v1/provider` and `POST /api/v1/provider/models` back it.
- Native OpenAI backend support alongside Ollama, LM Studio and OpenRouter.
- Forced `kotlinx-datetime` 0.6.2 on the desktop runtime because the AG-UI SDK
  still calls `Clock.System`, while Compose Material3 1.9 resolves 0.7.x.
- Android companion: `androidApp` uses the Android-KMP library plugin in
  `shared`, Compose Material3, an encrypted Android Keystore token store, chat
  timeline, tool cards, REA artifact paths, and approval buttons. The debug APK
  builds with AGP 9.3.1 and compileSdk 36.

## v3.1 - always alive

- `/life` no longer stops when the daily throttle is reached. The action budget
  is now optional and defaults to unlimited (`max_actions_per_day: 0`), so
  internal work and reflection never end the agent's day.
- Idle replies are conversation, not task execution. The model answers in its
  own voice without tools and appends `GOAL:` only when the human actually
  asked for work.
- Pressing Enter in autopilot lets GRID give itself one small goal, capped by
  `max_self_goals_per_day` (default 24).
- Autopilot runs the normal heartbeat (`work_goals=False`), so briefs,
  commitments and reflections still surface during long sessions.
- New always-on resident: `python grid_agent.py --no-input --resident` owns
  DuckDB, runs headless on a slow rhythm, sleeps through quiet hours and exposes
  a loopback control surface on `127.0.0.1:8770` (`/health`, `/status`,
  `/handoff`, `/pause`, `/resume`).
- The interactive app asks a live resident to hand over the database before it
  opens, and `life.resident_autostart` relaunches the resident on exit.
- `install_autostart.ps1` now installs both the tray and the resident at login;
  logs go to `logs/resident-YYYYMMDD.log`.
- Resident denies every non-read tool unless permissions explicitly allow it.
- New durable user profile in `grid_persona.md`, injected before technical memory
  on every turn. `/memory add <fact>`, `/memory profile`, `/memory forget`,
  `/memory build-profile`, and chat shortcuts `remember that ...` / `forget that ...`
  manage it. The model can also emit `REMEMBER:` lines, which the harness stores
  and hides from the reply.
- Profile extraction ignores system specs, tool results, one-off tasks, test
  prompts and PII, and refuses credentials/secrets. `tools/backfill_profile.py`
  mines previous chats for durable user facts.
- GRID now starts Ollama with a hidden console and the resident waits a
  configurable startup grace period before its first model call. This prevents
  Ollama's `llama-server`/GPU-discovery subprocesses from flashing terminal
  windows during Windows login.
- 112 tests cover the life loop, profile memory, auto-detect parsing, resident
  handoff, autopilot pacing and the existing tool registry; 49 routing evals.

## v3.0 - GRID Life

- `/life` is autonomous autopilot: one command, Esc twice returns to manual.
  GRID greets, reports each cycle, asks `ASK_USER` follow-ups and checks in
  every few cycles. One-shot tasks complete after one successful cycle, then
  GRID stays awake and asks what is next. Ongoing goals stay active. Only
  Esc twice returns to manual.
- GRID Life adopts the `/persona` identity. `/persona set TinaGrid` makes
  `/life` TinaGrid, knows `Moltbook as TinaGrid`, and gives the model the full
  80-tool registry. With no persona, `/life` asks; with no goals, it asks what
  to work on.
- Autopilot reads recent chats, durable memory, tool logs, scan results and
  local DB summaries; secrets are redacted. Cloud backends omit this context
  unless `life.allow_cloud_context` is true.
- Agent Skills (`SKILL.md`): validated frontmatter, progressive loading,
  `skill_search`, `skill_load`, `skill_read`, and four built-in MIT skills.
- MCP client (`mcp_servers`, `mcp_tools`, `mcp_call`) and a read-only GRID MCP
  server for Claude Code, Codex, Cursor and other clients.
- OpenCode setup: `opencode.example.jsonc`, `install_opencode_mcp.ps1`, and
  README instructions. Verified `opencode mcp list` shows `grid connected`.
- `document_read` with optional MarkItDown for PDF/DOCX/XLSX/PPTX, plus local
  fallbacks for text, HTML, JSON, CSV, Excel and DOCX.
- Optional `sherlock_scan`, `nuclei_scan` (requires `authorized`) and
  `pio_build` wrappers.
- Optional Headroom compression applies only to non-system messages.
- Tray host (`grid_tray.py`) plus login autostart scripts; `--autopilot` starts
  without the menu.
- Permission policy covers all 80 tools with `ask`, `auto` and `read_only`
  modes, session approvals and `auto_approve` for external actions.
- Double-Esc cancellation works across streaming, tool steps and `run_command`.
- 76 tests and 49 routing eval cases cover the life loop, persona sync,
  permissions, cancellation, autopilot, local context, skills, MCP, documents,
  optional tools and tray.
- Remaining non-goals: real-model acceptance evals and optional L2/L3 desktop
  senses (screen OCR, microphone).

## v2.0.1 - clean run

- Added `--check`: a non-interactive setup check for Python, required imports,
  `config.json`, Ollama, the selected model, DuckDB and the tool registry.
- Added `--no-input`: start from `config.json` without the backend/model wizard.
- Added `--no-banner`: skip the five-second Matrix banner.
- Added `--install-missing`: optional-package install is now opt-in. Missing
  optional packages are reported and their tools stay disabled.
- Added `run.ps1` and a â€œClean startâ€ README section with a venv workflow.
- `config.example.json` is now an Ollama-ready template; a fresh clone copies it
  to `config.json` before running `--check`.
- `install.py` now reads `requirements.txt` instead of keeping a second package
  list, and seeds `config.json` from the example (including `backend_type`).
- Added `pyserial` and `youtube-transcript-api` to `requirements.txt` and
  required `youtube-transcript-api>=1.0`, matching the API the code calls.
- `--check` now verifies all core imports from `requirements.txt`, so a partial
  pip install fails before launch.
- Questions like â€œwhat is my system info?â€ now run `system_info` directly
  instead of relying on the model.
- The system prompt tells the model never to present a remembered answer as a
  fresh tool result, which prevents stale memory from masking live data.
- User manual: aligned the capability-group count to 16 and removed two
  duplicated capability bullets.
- CI now fails if the registry drops below 70 tools.
- Chat input uses `prompt_toolkit`: Tab completes `/` commands and their
  subcommands, Up/Down browses history, and matching history is suggested
  inline. Piped input keeps the plain prompt.
- `/persona` with no argument now shows the current identity instead of a
  usage line.
- Unknown `/` commands print a clear error instead of being sent to the model.
- `/tools` stays open for multiple toggles and explains unknown tool names.
- Web searches strip filler from queries like â€œsearch online about Xâ€, and
  auto-detected tool results no longer print a duplicate `[Tool: ...]` header.
- Windows redirected output is forced to UTF-8, so Unicode headers no longer
  crash when output is piped or logged.
- The app starts Ollama itself when it is not running, then reaches the menu.
- Ollama now uses `num_ctx=16384`, so the 70-tool schema is not truncated and
  natural-language tool calls work on `gemma4:e2b`.
- `system_info` now uses PowerShell CIM instead of the removed `wmic`, so it
  reports memory, disk and the LAN IP without a partial-error line.
- Moved PocketBaseâ€™s upstream license and changelog to
  `third_party/pocketbase/`. The repository now has its own MIT license and a
  third-party notices file.
- Added a CI gate: syntax check, config validation and an import/tool-registry
  check on Windows.
- README: corrected the tool count (70+), capability-group count, local-first
  wording and broken/missing references.

## v2.0 â€” layered memory and field tools

- Added the four-tier memory engine: persona, scenarios, atoms, transcript and
  offloaded refs, with distillation every five turns.
- Added the local CTF sandbox and the GRAD open-world / MiniGrid game bridge.
- Added the autonomous Moltbook social agent and trend reporting.
- Added the 70-tool registry, including OSINT, network, radio, satellite,
  microcontroller, vision, Google, data and automation tools.

## v1.0 â€” initial release

- Local-first CLI agent with Ollama, LM Studio and OpenRouter backends.
- Tool registry, planner, streaming, config, export and persistent memory.

