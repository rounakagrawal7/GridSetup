# Changelog

## v3.0 - GRID Life (in progress)

- Added `grid_life.py`: persistent identity, goals, commitments, relationships,
  heartbeat, budgets, quiet hours, reflections, pending messages and an iLog,
  stored in the existing DuckDB.
- Added `/life` commands for status, tick, iLog, goals, commitments, pause,
  resume and identity. Pending messages are shown when you enter Chat.
- Added a standalone `python grid_life.py status|tick|log` CLI for when GRID
  is closed.
- Added 13 fixed-clock unit tests for the life loop; CI runs them.
- Renamed the app and setup banners to GRID v3.
- The open-source stack (Agent Skills, MCP, MarkItDown, evals, optional tools)
  is the next v3 slice.

## v2.0.1 - clean run

- Added `--check`: a non-interactive setup check for Python, required imports,
  `config.json`, Ollama, the selected model, DuckDB and the tool registry.
- Added `--no-input`: start from `config.json` without the backend/model wizard.
- Added `--no-banner`: skip the five-second Matrix banner.
- Added `--install-missing`: optional-package install is now opt-in. Missing
  optional packages are reported and their tools stay disabled.
- Added `run.ps1` and a “Clean start” README section with a venv workflow.
- `config.example.json` is now an Ollama-ready template; a fresh clone copies it
  to `config.json` before running `--check`.
- `install.py` now reads `requirements.txt` instead of keeping a second package
  list, and seeds `config.json` from the example (including `backend_type`).
- Added `pyserial` and `youtube-transcript-api` to `requirements.txt` and
  required `youtube-transcript-api>=1.0`, matching the API the code calls.
- `--check` now verifies all core imports from `requirements.txt`, so a partial
  pip install fails before launch.
- Questions like “what is my system info?” now run `system_info` directly
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
- Web searches strip filler from queries like “search online about X”, and
  auto-detected tool results no longer print a duplicate `[Tool: ...]` header.
- Windows redirected output is forced to UTF-8, so Unicode headers no longer
  crash when output is piped or logged.
- The app starts Ollama itself when it is not running, then reaches the menu.
- Ollama now uses `num_ctx=16384`, so the 70-tool schema is not truncated and
  natural-language tool calls work on `gemma4:e2b`.
- `system_info` now uses PowerShell CIM instead of the removed `wmic`, so it
  reports memory, disk and the LAN IP without a partial-error line.
- Moved PocketBase’s upstream license and changelog to
  `third_party/pocketbase/`. The repository now has its own MIT license and a
  third-party notices file.
- Added a CI gate: syntax check, config validation and an import/tool-registry
  check on Windows.
- README: corrected the tool count (70+), capability-group count, local-first
  wording and broken/missing references.

## v2.0 — layered memory and field tools

- Added the four-tier memory engine: persona, scenarios, atoms, transcript and
  offloaded refs, with distillation every five turns.
- Added the local CTF sandbox and the GRAD open-world / MiniGrid game bridge.
- Added the autonomous Moltbook social agent and trend reporting.
- Added the 70-tool registry, including OSINT, network, radio, satellite,
  microcontroller, vision, Google, data and automation tools.

## v1.0 — initial release

- Local-first CLI agent with Ollama, LM Studio and OpenRouter backends.
- Tool registry, planner, streaming, config, export and persistent memory.
